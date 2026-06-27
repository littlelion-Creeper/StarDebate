"""StardebateCompiler — .stardebate 文件格式核心编译器

双层加密架构:
  第1层: StarDebate 内置密钥 (PBKDF2 + AES-256-GCM) — 仅 StarDebate 可解密
  第2层: 用户密码 (PBKDF2 + AES-256-GCM, 可选) — 即使拿到 StarDebate 也需要密码

其他软件打开 .stardebate 文件时看到的是完全不可读的二进制乱码。

依赖: pip install cryptography
"""

import os
import json
import zlib
import hashlib
import struct
import time
import uuid
from typing import Optional

# ── 加密库 ──────────────────────────────────────────────────────────────
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
    AESGCM = None


# ══════════════════════════════════════════════════════════════════════════
#  常量
# ══════════════════════════════════════════════════════════════════════════

# XOR 混淆后的魔数 (STDB ^ 0x5A) — 外部软件看到乱码
STDB_MAGIC = bytes([0x53 ^ 0x5A, 0x54 ^ 0x5A, 0x44 ^ 0x5A, 0x42 ^ 0x5A])
# → b'\x19\x2e\x17\x21' — 记事本显示为: ░▒│ (不可读)

# 文件格式版本
STDB_VERSION: int = 1

# flags 位定义
FLAG_HAS_PASSWORD: int = 0x0001
FLAG_IS_COMPRESSED: int = 0x0002

# 内置密钥盐值 (编译时嵌入，外部不可知)
_BUILTIN_SALT: bytes = b'SD\xb7\xe3\x91k\xa4_N\xd2\xf8\xc5v\x03\x1a\x9e'

# PBKDF2 迭代次数
_PBKDF2_ITERS: int = 100000

# 内置密钥材料
_INTERNAL_KEY_MATERIAL: bytes = (
    b'StarDebate_2026_Internal_Encryption_Key'
    b'_Material_v1_Do_Not_Share_Outside_Application'
)

# 文件头固定大小
HEADER_SIZE: int = 36  # magic(4) + version(2) + flags(2) + pwd_salt(16) + nonce(12)

# ── 监视钩子 ──────────────────────────────────────────────────────────
_MONITOR_TAGS = {
    'variable_watch': 'VAR',
    'function_watch': 'FUNC',
    'plugin_watch': 'PLUGIN',
    'api_watch': 'API',
    'ai_watch': 'AI',
}


def _monitor(mtype: str, message: str):
    """写入监视日志到 stderr → 由 StderrToLogRedirector 自动重定向到日志文件。

    不依赖 LogManager / DebugMonitorManager 的内部实现，仅依赖启动时已安装的
    stderr 重定向器，确保监视信息始终落盘。
    """
    import sys
    from datetime import datetime

    tag = _MONITOR_TAGS.get(mtype, 'MON')
    now = datetime.now()
    ts = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"
    try:
        sys.stderr.write(f"[{ts}] [INFO] [{tag}] {message}\n")
        sys.stderr.flush()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
#  StardebateCompiler
# ══════════════════════════════════════════════════════════════════════════

class StardebateCompiler:
    """.stardebate 文件编译器 — 双层加密 / 解密 / 打包 / 解包。

    用法:
        compiler = StardebateCompiler()

        # 导出 (无密码)
        data = compiler.pack(modules_dict, password=None)

        # 导出 (有密码)
        data = compiler.pack(modules_dict, password="my_secret")

        # 导入 (自动检测是否有密码)
        info = compiler.get_file_info(data)           # 不解密获取元信息
        if info['has_password']:
            result = compiler.unpack(data, password="my_secret")
        else:
            result = compiler.unpack(data)
    """

    def __init__(self):
        if not _HAS_CRYPTO:
            raise ImportError(
                "加密库未安装。请运行: pip install cryptography\n"
                ".stardebate 文件格式需要 cryptography 库支持 AES-256-GCM 加密。"
            )
        self._builtin_key: Optional[bytes] = None

    # ── 密钥派生 ──────────────────────────────────────────────────────

    def _get_builtin_key(self) -> bytes:
        """获取/派生内置密钥 (缓存)"""
        if self._builtin_key is None:
            self._builtin_key = hashlib.pbkdf2_hmac(
                'sha256', _INTERNAL_KEY_MATERIAL, _BUILTIN_SALT,
                _PBKDF2_ITERS, dklen=32
            )
        return self._builtin_key

    @staticmethod
    def _derive_password_key(password: str, salt: bytes) -> bytes:
        """从用户密码派生第2层密钥"""
        return hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'), salt,
            _PBKDF2_ITERS, dklen=32
        )

    # ── AES-256-GCM 加密/解密 ─────────────────────────────────────────

    @staticmethod
    def _aes_encrypt(key: bytes, plaintext: bytes) -> bytes:
        """AES-256-GCM 加密，返回 nonce(12) + ciphertext + tag(16)"""
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ct  # ct 末尾 16 bytes 是 tag

    @staticmethod
    def _aes_decrypt(key: bytes, data: bytes) -> Optional[bytes]:
        """AES-256-GCM 解密，data = nonce(12) + ciphertext + tag(16)。
        认证失败返回 None。
        """
        if len(data) < 28:
            return None
        nonce = data[:12]
        ct = data[12:]
        aesgcm = AESGCM(key)
        try:
            return aesgcm.decrypt(nonce, ct, None)
        except Exception:
            return None

    # ── 文件头解析 ────────────────────────────────────────────────────

    @staticmethod
    def verify_magic(data: bytes) -> bool:
        """验证文件魔数"""
        return len(data) >= 4 and data[:4] == STDB_MAGIC

    @staticmethod
    def has_password(data: bytes) -> bool:
        """检测文件是否启用了第2层密码保护"""
        if len(data) < 8:
            return False
        flags = struct.unpack('>H', data[6:8])[0]
        return bool(flags & FLAG_HAS_PASSWORD)

    @staticmethod
    def get_file_info(data: bytes) -> dict:
        """不解密，仅从文件头读取基本信息。

        Returns:
            {"valid": bool, "version": int, "has_password": bool,
             "is_compressed": bool, "file_size": int}
        """
        info = {
            "valid": False, "version": 0, "has_password": False,
            "is_compressed": False, "file_size": len(data),
        }
        if not StardebateCompiler.verify_magic(data) or len(data) < HEADER_SIZE:
            return info
        info["valid"] = True
        info["version"] = struct.unpack('>H', data[4:6])[0]
        flags = struct.unpack('>H', data[6:8])[0]
        info["has_password"] = bool(flags & FLAG_HAS_PASSWORD)
        info["is_compressed"] = bool(flags & FLAG_IS_COMPRESSED)
        return info

    # ── 核心：打包 (导出) ─────────────────────────────────────────────

    def pack(self, modules: dict, password: Optional[str] = None,
             app_version: str = "1.0.0") -> bytes:
        """将模块数据字典打包为 .stardebate 加密格式。

        Args:
            modules: {"module_id": json_serializable_data, ...}
            password: 可选用户密码，None 则仅使用内置密钥
            app_version: 创建时的应用版本号

        Returns:
            加密后的 .stardebate 文件字节数据
        """
        _monitor('function_watch',
                 f'StardebateCompiler.pack(modules={len(modules)}, has_pwd={password is not None})')

        # ── 组装内层数据 ───────────────────────────────────────────
        inner_json = json.dumps(modules, ensure_ascii=False, separators=(',', ':'))
        inner_bytes = zlib.compress(inner_json.encode('utf-8'), level=6)

        # ── 第2层: 密码加密 (可选) ──────────────────────────────────
        flags = FLAG_IS_COMPRESSED
        password_salt = b'\x00' * 16

        if password:
            flags |= FLAG_HAS_PASSWORD
            password_salt = os.urandom(16)
            pwd_key = self._derive_password_key(password, password_salt)
            inner_bytes = self._aes_encrypt(pwd_key, inner_bytes)
            _monitor('function_watch',
                     f'StardebateCompiler: 第2层密码加密完成, size={len(inner_bytes)}')

        # ── 组装内部头部 ───────────────────────────────────────────
        debate_uuid = str(uuid.uuid4())
        internal_header = struct.pack(
            '>HHQ16s36s',
            STDB_VERSION,
            flags,
            int(time.time()),
            app_version.encode('utf-8').ljust(16, b'\x00')[:16],
            debate_uuid.encode('ascii')[:36],
        )
        # 元信息 JSON
        meta = {
            "app_version": app_version,
            "debate_uuid": debate_uuid,
            "module_count": len(modules),
            "module_ids": list(modules.keys()),
            **{f"size_{k}": len(json.dumps(v, ensure_ascii=False)) for k, v in modules.items()},
        }
        meta_json = json.dumps(meta, ensure_ascii=False, separators=(',', ':'))
        meta_bytes = meta_json.encode('utf-8')
        inner_data = internal_header + struct.pack('>I', len(meta_bytes)) + meta_bytes + inner_bytes

        # ── 第1层: 内置密钥加密 ────────────────────────────────────
        builtin_key = self._get_builtin_key()
        primary_encrypted = self._aes_encrypt(builtin_key, inner_data)

        # ── 组装文件 ───────────────────────────────────────────────
        file_data = (
            STDB_MAGIC
            + struct.pack('>HH', STDB_VERSION, flags)
            + password_salt
            + primary_encrypted
        )

        _monitor('api_watch',
                 f'StardebateCompiler.pack: 导出完成, '
                 f'plain_size={len(inner_bytes)}, '
                 f'encrypted_size={len(file_data)}, '
                 f'ratio={len(file_data) / max(1, len(inner_bytes)):.1f}x')

        return file_data

    # ── 核心：解包 (导入) ─────────────────────────────────────────────

    def unpack(self, data: bytes, password: Optional[str] = None) -> dict:
        """解密并解包 .stardebate 文件。

        Args:
            data: .stardebate 文件的原始字节
            password: 用户密码（如果文件有密码保护则必需）

        Returns:
            {"success": bool, "modules": dict or None, "meta": dict,
             "error": str or None}

        失败时返回 success=False 和 error 消息。
        """
        _monitor('function_watch',
                 f'StardebateCompiler.unpack(file_size={len(data)}, has_pwd_input={password is not None})')

        result = {"success": False, "modules": None, "meta": {}, "error": None}

        # ── 验证魔数 ───────────────────────────────────────────────
        if not self.verify_magic(data):
            result["error"] = "文件格式不正确: 不是有效的 .stardebate 文件"
            _monitor('api_watch', f'StardebateCompiler.unpack: {result["error"]}')
            return result

        if len(data) < HEADER_SIZE:
            result["error"] = "文件损坏: 数据长度不足"
            _monitor('api_watch', f'StardebateCompiler.unpack: {result["error"]}')
            return result

        # ── 解析文件头 ─────────────────────────────────────────────
        version = struct.unpack('>H', data[4:6])[0]
        flags = struct.unpack('>H', data[6:8])[0]
        password_salt = data[8:24]
        has_pwd = bool(flags & FLAG_HAS_PASSWORD)
        is_compressed = bool(flags & FLAG_IS_COMPRESSED)
        primary_ciphertext = data[24:]

        if len(primary_ciphertext) < 28:
            result["error"] = "文件损坏: 加密数据不完整"
            return result

        # ── 第1层解密: 内置密钥 ────────────────────────────────────
        builtin_key = self._get_builtin_key()
        inner_data = self._aes_decrypt(builtin_key, primary_ciphertext)

        if inner_data is None:
            result["error"] = "解密失败: 第1层认证未通过，文件可能已损坏"
            _monitor('api_watch', f'StardebateCompiler.unpack: {result["error"]}')
            return result

        _monitor('function_watch', 'StardebateCompiler: 第1层内置密钥解密成功')

        # ── 解析内部头部 ───────────────────────────────────────────
        inner_header_size = 2 + 2 + 8 + 16 + 36 + 4
        if len(inner_data) < inner_header_size:
            result["error"] = "文件损坏: 内部数据头不完整"
            return result

        offset = 0
        iv = struct.unpack('>H', inner_data[offset:offset + 2])[0]; offset += 2
        iflags = struct.unpack('>H', inner_data[offset:offset + 2])[0]; offset += 2
        created_ts = struct.unpack('>Q', inner_data[offset:offset + 8])[0]; offset += 8
        app_ver = inner_data[offset:offset + 16].decode('utf-8').rstrip('\x00'); offset += 16
        deb_uuid = inner_data[offset:offset + 36].decode('ascii'); offset += 36
        meta_len = struct.unpack('>I', inner_data[offset:offset + 4])[0]; offset += 4

        # ── 解析元信息 ─────────────────────────────────────────────
        if offset + meta_len > len(inner_data):
            result["error"] = "文件损坏: 元数据长度异常"
            return result
        meta_json_bytes = inner_data[offset:offset + meta_len]
        offset += meta_len

        try:
            meta = json.loads(meta_json_bytes.decode('utf-8'))
        except json.JSONDecodeError:
            meta = {}

        # ── 提取 payload (头+meta之后的部分) ─────────────────────────
        payload = inner_data[offset:]

        # ── 第2层解密: 密码 (如果启用, 仅解密 payload) ──────────────
        if has_pwd:
            if not password:
                result["error"] = "PASSWORD_REQUIRED"
                result["meta"] = {
                    "has_password": True, "version": version,
                    "created": created_ts, "app_version": app_ver,
                    "debate_uuid": deb_uuid,
                }
                _monitor('api_watch', 'StardebateCompiler.unpack: 需要密码')
                return result

            # 第2层解密 (仅解密 payload 部分)
            pwd_key = self._derive_password_key(password, password_salt)
            payload = self._aes_decrypt(pwd_key, payload)

            if payload is None:
                result["error"] = "密码错误: 第2层认证未通过"
                _monitor('api_watch', f'StardebateCompiler.unpack: {result["error"]}')
                return result

            _monitor('function_watch', 'StardebateCompiler: 第2层密码解密成功')
        if is_compressed:
            try:
                payload = zlib.decompress(payload)
            except zlib.error:
                result["error"] = "文件损坏: 数据解压失败"
                return result

        try:
            modules = json.loads(payload.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            result["error"] = f"数据解析失败: {str(e)}"
            return result

        result["success"] = True
        result["modules"] = modules
        result["meta"] = {
            "version": version,
            "created": created_ts,
            "app_version": app_ver,
            "debate_uuid": deb_uuid,
            "has_password": has_pwd,
            **meta,
        }

        _monitor('function_watch',
                 f'StardebateCompiler.unpack: 解密成功, '
                 f'modules={len(modules)}, '
                 f'app_version={app_ver}')

        return result


# ══════════════════════════════════════════════════════════════════════════
#  便捷函数
# ══════════════════════════════════════════════════════════════════════════

def collect_debate_data(mw, selected_modules: set) -> dict:
    """从主窗口收集各功能区的辩论数据。

    Args:
        mw: StarDebateWindow 实例
        selected_modules: 选中的模块ID集合

    Returns:
        {"module_id": json_data, ...}
    """
    import os as _os
    data = {}

    debate_path = mw.current_debate_path
    project_dir = _os.path.dirname(debate_path) if debate_path else None

    def _read_json(path: str) -> dict | None:
        if path and _os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _derive(suffix: str) -> str | None:
        """从辩论文件路径推导附属文件路径"""
        if not debate_path:
            return None
        base = _os.path.basename(debate_path)
        name_without_ext = base.replace('.json', '')
        derived = base.replace('.json', f'{suffix}.json')
        # 如果辩论文件格式是 debate_YYYYMMDD_HHMMSS.json
        candidate = _os.path.join(_os.path.dirname(debate_path), derived)
        if _os.path.isfile(candidate):
            return candidate
        # 尝试在项目根目录查找
        if project_dir:
            alt = _os.path.join(project_dir, derived)
            if _os.path.isfile(alt):
                return alt
        return None

    # ── 基本信息 ──
    if 'basic' in selected_modules and mw.current_debate_data:
        data['basic'] = mw.current_debate_data
        _monitor('variable_watch',
                 f'collect_debate_data: basic '
                 f'(pro={mw.current_debate_data.get("pro","")}, '
                 f'con={mw.current_debate_data.get("con","")})')

    # ── 一辩稿 ──
    for side, key, suffix in [('pro', 'speech_pro', '_正方一辩稿'),
                               ('con', 'speech_con', '_反方一辩稿')]:
        if key in selected_modules:
            # 尝试多个可能的文件名
            for sfx in [f'{suffix}', '_一辩稿']:
                path = _derive(sfx)
                if path:
                    d = _read_json(path)
                    if d:
                        data[key] = d
                        _monitor('variable_watch', f'collect_debate_data: {key} ({len(str(d))} chars)')
                        break

    # ── 资料稿 ──
    for side, key, suffix in [('pro', 'ref_doc_pro', '_正方资料稿'),
                               ('con', 'ref_doc_con', '_反方资料稿')]:
        if key in selected_modules:
            for sfx in [f'{suffix}', '_资料稿']:
                path = _derive(sfx)
                if path:
                    d = _read_json(path)
                    if d:
                        data[key] = d
                        _monitor('variable_watch', f'collect_debate_data: {key}')
                        break

    # ── AI 分析 ──
    for side, key in [('pro', 'analysis_pro'), ('con', 'analysis_con')]:
        if key in selected_modules:
            for sfx in [f'_{"正方一辩稿" if side == "pro" else "反方一辩稿"}_分析', '_一辩稿_分析']:
                path = _derive(sfx)
                if path:
                    d = _read_json(path)
                    if d:
                        data[key] = d
                        _monitor('variable_watch', f'collect_debate_data: {key}')
                        break

    # ── 辩论框架 ──
    if 'framework' in selected_modules:
        try:
            fw_data = mw._framework_mgr.data
            if fw_data:
                data['framework'] = fw_data
                _monitor('variable_watch',
                         f'collect_debate_data: framework ({len(fw_data)} nodes)')
        except Exception:
            pass

    # ── 模拟质询 ──
    if 'cross_exam' in selected_modules:
        for sfx in ['_质询模拟', '_CrossExamination']:
            path = _derive(sfx)
            if path:
                d = _read_json(path)
                if d:
                    data['cross_exam'] = d
                    _monitor('variable_watch', f'collect_debate_data: cross_exam')
                    break

    # ── 模拟接质 ──
    if 'accept_exam' in selected_modules:
        for side in ['正方', '反方']:
            for sfx in [f'_接质模拟_{side}', '_接质模拟']:
                path = _derive(sfx)
                if path:
                    d = _read_json(path)
                    if d:
                        key = f'accept_exam_{"pro" if side == "正方" else "con"}'
                        data[key] = d
                        _monitor('variable_watch', f'collect_debate_data: {key}')
                    break

    # ── 便签 ──
    if 'notes' in selected_modules and project_dir:
        path = _os.path.join(project_dir, 'sticky_notes.json')
        d = _read_json(path)
        if d:
            data['notes'] = d
            _monitor('variable_watch', f'collect_debate_data: notes')

    # ── 结构树 ──
    if 'structure' in selected_modules:
        try:
            struct_pro = mw._structure_mgr._get_data('pro') if hasattr(mw._structure_mgr, '_get_data') else None
            struct_con = mw._structure_mgr._get_data('con') if hasattr(mw._structure_mgr, '_get_data') else None
            if struct_pro or struct_con:
                data['structure'] = {'pro': struct_pro, 'con': struct_con}
                _monitor('variable_watch', 'collect_debate_data: structure')
        except Exception:
            pass

    # ── 训练记录 ──
    if 'training' in selected_modules and project_dir:
        import glob as _glob
        train_files = _glob.glob(_os.path.join(project_dir, 'train_*.json'))
        train_files += _glob.glob(_os.path.join(_os.path.dirname(project_dir), 'exercise_sessions', '*.json'))
        if train_files:
            training_data = []
            for tf in train_files[:20]:  # 最多 20 个文件
                d = _read_json(tf)
                if d:
                    d['_filename'] = _os.path.basename(tf)
                    training_data.append(d)
            if training_data:
                data['training'] = training_data
                _monitor('variable_watch',
                         f'collect_debate_data: training ({len(training_data)} files)')

    _monitor('function_watch',
             f'collect_debate_data: 收集完成, total_modules={len(data)}')

    return data


def restore_debate_data(mw, modules: dict, selected_modules: set, project_dir: str) -> bool:
    """将解密后的模块数据恢复到项目中。

    Args:
        mw: StarDebateWindow 实例
        modules: 解密后的模块数据
        selected_modules: 要恢复的模块ID集合
        project_dir: 目标项目目录

    Returns:
        是否成功
    """
    import os as _os

    def _write_json(path: str, data) -> bool:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    success_count = 0
    fail_count = 0

    # ── 基本信息 → 创建辩论 JSON ──
    if 'basic' in selected_modules and 'basic' in modules:
        basic = modules['basic']
        timestamp = basic.get('created', '') or time.strftime('%Y%m%d_%H%M%S')
        debate_file = _os.path.join(project_dir, f'debate_{timestamp}.json')
        if _write_json(debate_file, basic):
            mw.current_debate_path = debate_file
            mw.current_debate_data = basic
            mw._display_debate(debate_file, basic)
            success_count += 1
            _monitor('variable_watch', f'restore: basic → {debate_file}')
        else:
            fail_count += 1

    # ── 一辩稿 ──
    for side, key in [('pro', 'speech_pro'), ('con', 'speech_con')]:
        if key in selected_modules and key in modules:
            path = _os.path.join(project_dir, f'speech_{side}.json')
            if _write_json(path, modules[key]):
                success_count += 1
                _monitor('variable_watch', f'restore: {key} → {path}')
            else:
                fail_count += 1

    # ── 资料稿 ──
    for side, key in [('pro', 'ref_doc_pro'), ('con', 'ref_doc_con')]:
        if key in selected_modules and key in modules:
            path = _os.path.join(project_dir, f'ref_doc_{side}.json')
            if _write_json(path, modules[key]):
                success_count += 1
            else:
                fail_count += 1

    # ── AI 分析 ──
    for side, key in [('pro', 'analysis_pro'), ('con', 'analysis_con')]:
        if key in selected_modules and key in modules:
            path = _os.path.join(project_dir, f'analysis_{side}.json')
            if _write_json(path, modules[key]):
                success_count += 1
            else:
                fail_count += 1

    # ── 辩论框架 ──
    if 'framework' in selected_modules and 'framework' in modules:
        try:
            mw._framework_mgr._framework_nodes = modules['framework']
            success_count += 1
            _monitor('variable_watch', 'restore: framework → memory')
        except Exception:
            fail_count += 1

    # ── 模拟质询 ──
    if 'cross_exam' in selected_modules and 'cross_exam' in modules:
        path = _os.path.join(project_dir, 'cross_exam.json')
        if _write_json(path, modules['cross_exam']):
            success_count += 1
        else:
            fail_count += 1

    # ── 模拟接质 ──
    for side_key in ['accept_exam_pro', 'accept_exam_con']:
        if side_key in selected_modules and side_key in modules:
            side_label = '正方' if 'pro' in side_key else '反方'
            path = _os.path.join(project_dir, f'accept_exam_{side_label}.json')
            if _write_json(path, modules[side_key]):
                success_count += 1
            else:
                fail_count += 1

    # ── 便签 ──
    if 'notes' in selected_modules and 'notes' in modules:
        path = _os.path.join(project_dir, 'sticky_notes.json')
        if _write_json(path, modules['notes']):
            success_count += 1
        else:
            fail_count += 1

    # ── 结构树 ──
    if 'structure' in selected_modules and 'structure' in modules:
        try:
            sd = modules['structure']
            if hasattr(mw._structure_mgr, 'load_data'):
                if sd.get('pro'):
                    mw._structure_mgr._structure_data['pro'] = sd['pro']
                if sd.get('con'):
                    mw._structure_mgr._structure_data['con'] = sd['con']
            success_count += 1
        except Exception:
            fail_count += 1

    # ── 训练记录 ──
    if 'training' in selected_modules and 'training' in modules:
        train_list = modules['training']
        if isinstance(train_list, list):
            for td in train_list:
                if isinstance(td, dict):
                    fname = td.pop('_filename', f'train_{int(time.time())}.json')
                    path = _os.path.join(project_dir, fname)
                    _write_json(path, td)
            success_count += 1

    # ── 刷新项目树 ──
    try:
        mw._build_tree_from_path(project_dir)
    except Exception:
        pass

    _monitor('function_watch',
             f'restore_debate_data: 完成, success={success_count}, fail={fail_count}')

    return fail_count == 0
