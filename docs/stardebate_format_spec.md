# .stardebate — StarDebate 辩论文件格式规范

> 版本 v1.0 | 2026-06-06 | StarDebate 项目

---

## §1 概述

`.stardebate` 是 **StarDebate ★ 辩之星** 的专属辩论数据文件格式。它将一个辩论项目的全部参数（基本信息、一辩稿、资料稿、AI 分析、辩论框架、模拟质询、便签、结构树、训练记录等）打包为单一加密文件。

### 核心特性

| 特性 | 说明 |
|------|------|
| **双层 AES-256-GCM 加密** | 第1层内置密钥 (仅 StarDebate 可读) + 第2层用户密码 (可选) |
| **乱码保护** | 其他软件打开显示为不可辨认的二进制数据 |
| **防篡改** | GCM 认证标签确保文件完整性 |
| **压缩存储** | zlib level 6 压缩 |
| **完整性校验** | 内嵌元数据 + 模块清单 |

---

## §2 文件基础结构

`.stardebate` 文件由 **文件头** + **加密载荷** 两部分组成，所有多字节整数使用 **大端序 (Big-Endian)**。

```
┌──────────────────────────────────────────────────────────────┐
│  .stardebate 文件结构 v1                                      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  [文件头: 36 字节 — 明文]                                     │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 偏移    长度    类型       字段       说明            │    │
│  │ 0       4       uint8[4]   magic      魔数标识       │    │
│  │ 4       2       uint16 BE  version    格式版本 (=1)   │    │
│  │ 6       2       uint16 BE  flags      标志位          │    │
│  │ 8       16      uint8[16]  pwd_salt   密码盐值        │    │
│  │ 24      12      uint8[12]  nonce      AES nonce       │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  [加密载荷: 变长 — AES-256-GCM 密文 + 16字节认证标签]         │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ 偏移 36..     变长     ciphertext   密文               │    │
│  │ 末尾 -16      16      auth_tag     GCM 认证标签       │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  总大小 = 36 + len(ciphertext) + 16 = 52 + len(ciphertext)   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 魔数

```
magic = "STDB" XOR 0x5A → b'\x19\x2e\x17\x21'
```

记事本/外部软件中显示为乱码 `░▒▓│`。

### 标志位 (flags)

```
bit0: has_password    — 是否启用第2层密码加密
bit1: is_compressed   — 数据是否 zlib 压缩 (始终为 1)
bit2-15: reserved     — 保留，必须为 0
```

### 密码盐值

- `has_password = 0` → 16 字节全 `0x00`
- `has_password = 1` → 16 字节随机值 (`os.urandom(16)`)

---

## §3 加密体系

### 3.1 双层加密架构

```
  原始 JSON 数据
       │
       ▼ zlib compress
  [压缩数据]
       │
       ├── 无密码 ──────────────────→ [内层明文]
       │
       └── 有密码 ──→ AES-256-GCM ──→ [内层密文]
                       (密码密钥)
       │
       ▼ 添加内部头部 + 元信息
  [内部完整数据]
       │
       ▼ AES-256-GCM (内置密钥)
  [最终密文]
```

### 3.2 密钥派生

| 密钥 | 算法 | 输入 | 迭代 | 输出 |
|------|------|------|------|------|
| 第1层 (内置) | PBKDF2-HMAC-SHA256 | 内置密钥材料 + 内置盐 | 100,000 | 32 字节 |
| 第2层 (密码) | PBKDF2-HMAC-SHA256 | 用户密码 + password_salt | 100,000 | 32 字节 |

> **注意**: 第1层内置密钥材料和盐值编译时嵌入 StarDebate 程序内，外部不可获取。这是保证"仅 StarDebate 可读"的核心机制。

### 3.3 加密算法

- **算法**: AES-256-GCM (Galois/Counter Mode)
- **Nonce**: 每层独立 12 字节随机值
- **认证标签**: 16 字节，自动附加在密文末尾
- **库依赖**: `cryptography` (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`)

---

## §4 内部数据结构

### 4.1 第1层解密后的内部结构

```
┌──────────────────────────────────────────────────────────────┐
│  内部数据 (第1层解密后)                                       │
├──────────────────────────────────────────────────────────────┤
│  偏移    长度    类型       字段                             │
│  0       2       uint16 BE  version (内部版本 = 1)           │
│  2       2       uint16 BE  flags                            │
│  4       8       uint64 BE  created    创建时间戳 (Unix)      │
│  12      16      str(16)    app_version 创建应用版本          │
│  28      36      str(36)    debate_uuid UUID                 │
│  64      4       uint32 BE  meta_len   元数据长度            │
│  68      N       JSON       meta       元数据 (UTF-8)        │
│  68+N    M       bytes      payload    模块数据              │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 元数据 JSON 示例

```json
{
    "app_version": "2.3.0",
    "debate_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "module_count": 10,
    "module_ids": ["basic", "speech_pro", ...],
    "size_basic": 512,
    "size_speech_pro": 2100
}
```

### 4.3 payload 处理

```
IF has_password == 0:
    payload = zlib.decompress(payload_bytes) → UTF-8 JSON

IF has_password == 1:
    payload = AES-256-GCM.decrypt(password_key, payload_bytes)
    payload = zlib.decompress(payload) → UTF-8 JSON
```

### 4.4 最终 JSON 结构

```json
{
    "basic": {
        "pro": "正方名称",
        "con": "反方名称",
        "pro_args": "正方论点",
        "con_args": "反方论点",
        "created": "20260606_203000",
        "format": { ... }
    },
    "speech_pro": { "content": "...", "keywords": [...] },
    "speech_con": { ... },
    "ref_doc_pro": { "rows": [...] },
    "framework": [ { "id": 1, "text": "...", "node_type": "..." } ],
    "cross_exam": { "rounds": [...] },
    "notes": [...],
    "structure": { "pro": [...], "con": [...] },
    "training": [ { "_filename": "train_xxx.json", ... } ]
}
```

---

## §5 数据模块清单

| module_id | 名称 | JSON 结构 |
|-----------|------|-----------|
| `basic` | 辩论基本信息 | `{pro, con, pro_args, con_args, created, format}` |
| `speech_pro` | 正方一辩稿 | `{content, keywords, custom_glossary, ...}` |
| `speech_con` | 反方一辩稿 | 同上 |
| `ref_doc_pro` | 正方资料稿 | `{rows: [[...], ...]}` |
| `ref_doc_con` | 反方资料稿 | 同上 |
| `analysis_pro` | 正方 AI 分析 | `{pro, analysis_text, ...}` |
| `analysis_con` | 反方 AI 分析 | 同上 |
| `framework` | 辩论框架 | `[{id, text, node_type, children}, ...]` |
| `cross_exam` | 模拟质询 | `{rounds: [{question, answer, ...}], ...}` |
| `accept_exam_pro` | 正方接质 | `{messages, scores, ...}` |
| `accept_exam_con` | 反方接质 | 同上 |
| `notes` | 便签数据 | `[{id, text, color, pinned}, ...]` |
| `structure` | 结构树 | `{pro: [...], con: [...]}` |
| `training` | 训练记录 | `[{_filename, ...}, ...]` |

---

## §6 导入验证流程

```
  读取文件
    │
    ├── 验证 magic = b'\x19\x2e\x17\x21'
    │     └── 失败 → "不是有效的 .stardebate 文件"
    │
    ├── 解析 header (version, flags, pwd_salt)
    │
    ├── 第1层解密 (内置密钥)
    │     └── GCM 认证失败 → "文件可能已损坏"
    │
    ├── IF has_password:
    │     ├── 弹出密码输入框
    │     ├── 第2层解密 (用户密码)
    │     │     └── GCM 认证失败 → "密码错误" (最多 5 次)
    │     └── 成功 → 继续
    │
    ├── zlib 解压
    ├── JSON 解析
    └── 分发到各功能区
```

---

## §7 安全性说明

### 7.1 安全保证

- **无密码文件**: 仅有 StarDebate 程序可以解密，外部软件无法读取
- **有密码文件**: 即使拥有 StarDebate 程序，也需要正确密码才能解密
- **防篡改**: AES-GCM 认证模式，任何字节修改都会导致解密失败
- **密码不可恢复**: 密码不存储在文件中，忘记密码则文件永久不可读

### 7.2 安全限制

> ⚠️ **重要**: 第1层密钥材料编译时嵌入 StarDebate 程序中。有经验的逆向工程师理论上可以提取内置密钥。如果您需要最高级别的安全性，请始终启用用户密码（第2层加密）。

---

## §8 库依赖与安装

```bash
pip install cryptography
```

Python 标准库依赖:
- `hashlib` — PBKDF2 密钥派生
- `zlib` — 数据压缩
- `json` — 数据序列化
- `struct` — 二进制打包
- `os` — 随机数生成

---

## §9 版本兼容性

| 文件版本 | StarDebate 版本 | 说明 |
|----------|-----------------|------|
| 1 | ≥ 2.3.0 | 初始版本，双层加密 |

未来版本号递增规则:
- 主版本号变更 → 不兼容旧版本
- 添加新字段 → 文件中 flag 新增位标识 → 旧版本忽略未知字段

---

## §10 开源许可

StarDebate 项目及其 `.stardebate` 文件格式采用 MIT 许可证。

版权所有 © 2026 StarDebate 贡献者。

特此免费授予任何获得本软件及相关文档文件副本的人不受限制地处理本软件的权利，包括但不限于使用、复制、修改、合并、发布、分发、再许可和/或销售本软件副本的权利，并允许获得本软件的人这样做，但须满足以下条件：

上述版权声明和本许可声明应包含在本软件的所有副本或主要部分中。

本软件按"原样"提供，不作任何明示或暗示的保证，包括但不限于对适销性、特定用途适用性和非侵权性的保证。

---

## 附录 A: Python 读取示例

```python
import json
from workers.stardebate_format import StardebateCompiler

compiler = StardebateCompiler()

# 读取文件
with open("辩论导出.stardebate", "rb") as f:
    data = f.read()

# 验证格式
if not compiler.verify_magic(data):
    print("不是有效的 .stardebate 文件")

# 检查是否需要密码
info = compiler.get_file_info(data)
if info["has_password"]:
    password = input("请输入密码: ")
    result = compiler.unpack(data, password=password)
else:
    result = compiler.unpack(data)

if result["success"]:
    modules = result["modules"]
    print(f"正方: {modules['basic']['pro']}")
    print(f"反方: {modules['basic']['con']}")
    print(f"包含 {len(modules)} 个数据模块")
```

## 附录 B: 导出示例

```python
from workers.stardebate_format import StardebateCompiler

compiler = StardebateCompiler()

modules = {
    "basic": {"pro": "正方", "con": "反方", "pro_args": "...", "con_args": "..."},
    "speech_pro": {"content": "一辩稿内容..."},
}

# 无密码导出
file_bytes = compiler.pack(modules, app_version="2.3.0")
with open("output.stardebate", "wb") as f:
    f.write(file_bytes)

# 有密码导出
file_bytes = compiler.pack(modules, password="my_secret", app_version="2.3.0")
with open("output_protected.stardebate", "wb") as f:
    f.write(file_bytes)
```

---

> 📬 **反馈与贡献**: 欢迎通过 GitHub Issues 提交问题或 Pull Request 贡献代码。
