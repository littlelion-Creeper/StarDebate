"""DPAPI 密码加密模块 — 使用 Windows Data Protection API 安全存储密码。

Windows DPAPI (CryptProtectData / CryptUnprotectData):
  - 使用当前用户账户加密数据，绑定用户 SID
  - 只有当前 Windows 用户可解密
  - 即使复制文件到其他机器/其他用户也无效
  - 无需额外依赖（Windows 内置 API）

降级方案：如果不在 Windows 上，使用 base64 编码（明文存储，仅用于兼容）。
"""

import sys
import os
import json
import base64
from typing import Optional, Tuple

from workers.app_config.config_paths import get_config_path

# ── 监视钩子 ──────────────────────────────────────────────────────
_MONITOR_TAGS = {
    'variable_watch': 'VAR',
    'function_watch': 'FUNC',
    'api_watch': 'API',
}

def _monitor(mtype: str, message: str):
    import sys as _sys
    from datetime import datetime
    tag = _MONITOR_TAGS.get(mtype, 'MON')
    now = datetime.now()
    ts = now.strftime("%H:%M:%S") + f".{now.microsecond // 1000:03d}"
    try:
        _sys.stderr.write(f"[{ts}] [INFO] [{tag}] {message}\n")
        _sys.stderr.flush()
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════════
#  Windows DPAPI 实现（通过 ctypes 直接调用）
# ═════════════════════════════════════════════════════════════════════

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _crypt32 = ctypes.windll.crypt32

    # CRYPTPROTECT_UI_FORBIDDEN = 0x1 → 不弹出任何 UI
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    CRYPTPROTECT_LOCAL_MACHINE = 0x4

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),  # pDataIn
        wintypes.LPCWSTR,           # szDataDescr
        ctypes.POINTER(DATA_BLOB),  # pOptionalEntropy
        ctypes.c_void_p,            # pvReserved
        ctypes.c_void_p,            # pPromptStruct
        wintypes.DWORD,             # dwFlags
        ctypes.POINTER(DATA_BLOB),  # pDataOut
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL

    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),  # pDataIn
        ctypes.POINTER(wintypes.LPWSTR),  # ppszDataDescr
        ctypes.POINTER(DATA_BLOB),  # pOptionalEntropy
        ctypes.c_void_p,            # pvReserved
        ctypes.c_void_p,            # pPromptStruct
        wintypes.DWORD,             # dwFlags
        ctypes.POINTER(DATA_BLOB),  # pDataOut
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL

    def _dpapi_encrypt(plaintext: str) -> Optional[str]:
        """使用 Windows DPAPI 加密字符串，返回 base64 编码密文。
        
        失败返回 None。
        """
        try:
            plain_bytes = plaintext.encode("utf-8")
            data_in = DATA_BLOB()
            data_in.cbData = len(plain_bytes)
            data_in.pbData = ctypes.cast(
                ctypes.create_string_buffer(plain_bytes, len(plain_bytes)),
                ctypes.POINTER(ctypes.c_char),
            )

            data_out = DATA_BLOB()
            result = _crypt32.CryptProtectData(
                ctypes.byref(data_in),
                "StarDebate.stardebate.password",  # 描述字符串
                None,       # 无额外熵
                None,       # 保留
                None,       # 无 UI 提示
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(data_out),
            )

            if not result:
                return None

            encrypted = ctypes.string_at(data_out.pbData, data_out.cbData)
            # 释放输出内存
            if hasattr(ctypes.windll, 'kernel32'):
                ctypes.windll.kernel32.LocalFree(data_out.pbData)
            return base64.b64encode(encrypted).decode("ascii")

        except Exception:
            return None

    def _dpapi_decrypt(b64_ciphertext: str) -> Optional[str]:
        """使用 Windows DPAPI 解密 base64 密文，返回明文字符串。
        
        失败返回 None。
        """
        try:
            encrypted = base64.b64decode(b64_ciphertext.encode("ascii"))
            data_in = DATA_BLOB()
            data_in.cbData = len(encrypted)
            data_in.pbData = ctypes.cast(
                ctypes.create_string_buffer(encrypted, len(encrypted)),
                ctypes.POINTER(ctypes.c_char),
            )

            data_out = DATA_BLOB()
            desc = wintypes.LPWSTR()
            result = _crypt32.CryptUnprotectData(
                ctypes.byref(data_in),
                ctypes.byref(desc),
                None,
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(data_out),
            )

            if not result:
                return None

            decrypted = ctypes.string_at(data_out.pbData, data_out.cbData)
            if hasattr(ctypes.windll, 'kernel32'):
                ctypes.windll.kernel32.LocalFree(data_out.pbData)
            return decrypted.decode("utf-8")

        except Exception:
            return None

else:
    # ── 非 Windows 降级：base64 编码（明文存储，仅防窥探）─────────
    def _dpapi_encrypt(plaintext: str) -> Optional[str]:
        try:
            return base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
        except Exception:
            return None

    def _dpapi_decrypt(b64_ciphertext: str) -> Optional[str]:
        try:
            return base64.b64decode(b64_ciphertext.encode("ascii")).decode("utf-8")
        except Exception:
            return None


# ═════════════════════════════════════════════════════════════════════
#  公开 API
# ═════════════════════════════════════════════════════════════════════

def encrypt_password(password: str) -> Optional[str]:
    """加密密码，返回 base64 密文字符串。"""
    _monitor('function_watch', 'dpapi: encrypt_password')
    result = _dpapi_encrypt(password)
    _monitor('api_watch', f'dpapi: encrypt_password → {"ok" if result else "FAILED"}')
    return result


def decrypt_password(b64_ciphertext: str) -> Optional[str]:
    """解密 base64 密文，返回明文密码。"""
    _monitor('function_watch', 'dpapi: decrypt_password')
    result = _dpapi_decrypt(b64_ciphertext)
    _monitor('api_watch', f'dpapi: decrypt_password → {"ok" if result else "FAILED"}')
    return result


# ═════════════════════════════════════════════════════════════════════
#  索引文件管理（config/stardebate_index.json）
# ═════════════════════════════════════════════════════════════════════

def _get_index_path(project_root: str = None) -> str:
    """获取 stardebate_index.json 的路径。"""
    if project_root is None:
        return get_config_path("config/stardebate_index.json")
    return os.path.join(project_root, "config", "stardebate_index.json")


def load_index() -> dict:
    """加载 stardebate 文件索引。"""
    _monitor('function_watch', 'dpapi: load_index')
    path = _get_index_path()
    if not os.path.exists(path):
        _monitor('variable_watch', 'dpapi: load_index → index file not found')
        return {"files": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = len(data.get("files", []))
        _monitor('variable_watch', f'dpapi: load_index → {count} files loaded')
        return data
    except Exception:
        _monitor('api_watch', 'dpapi: load_index → parse error, returning empty')
        return {"files": []}


def save_index(index_data: dict):
    """保存 stardebate 文件索引。"""
    count = len(index_data.get("files", []))
    _monitor('variable_watch', f'dpapi: save_index → {count} files')
    path = _get_index_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)


def add_file_to_index(file_path: str, file_uuid: str, password: Optional[str] = None) -> bool:
    """将 .stardebate 文件信息添加到索引。"""
    import time
    _monitor('function_watch', f'dpapi: add_file_to_index → {os.path.basename(file_path)}')
    index = load_index()

    existing = next((f for f in index.get("files", []) if f.get("path") == file_path), None)
    if existing:
        if password is not None:
            enc = encrypt_password(password)
            if enc is None:
                _monitor('api_watch', 'dpapi: add_file_to_index → encrypt failed')
                return False
            existing["pwd_blob"] = enc
            existing["has_password"] = True
        else:
            existing["pwd_blob"] = ""
            existing["has_password"] = False
        existing["updated_at"] = int(time.time())
    else:
        entry = {
            "path": file_path,
            "uuid": file_uuid,
            "has_password": password is not None,
            "pwd_blob": "",
            "added_at": int(time.time()),
            "updated_at": int(time.time()),
        }
        if password is not None:
            enc = encrypt_password(password)
            if enc is None:
                _monitor('api_watch', 'dpapi: add_file_to_index → encrypt failed')
                return False
            entry["pwd_blob"] = enc
        index.setdefault("files", []).append(entry)
        _monitor('variable_watch', f'dpapi: add_file_to_index → new entry, total={len(index["files"])}')

    save_index(index)
    return True


def remove_file_from_index(file_path: str):
    """从索引中移除文件。"""
    _monitor('function_watch', f'dpapi: remove_file_from_index → {os.path.basename(file_path)}')
    index = load_index()
    old_count = len(index.get("files", []))
    index["files"] = [f for f in index.get("files", []) if f.get("path") != file_path]
    _monitor('variable_watch', f'dpapi: remove_file_from_index → {old_count}→{len(index["files"])} files')
    save_index(index)


def get_password_for_file(file_path: str) -> Optional[str]:
    """获取文件的解密密码。"""
    _monitor('function_watch', f'dpapi: get_password_for_file → {os.path.basename(file_path)}')
    index = load_index()
    entry = next((f for f in index.get("files", []) if f.get("path") == file_path), None)
    if entry is None:
        return None
    if not entry.get("has_password", False):
        _monitor('variable_watch', 'dpapi: get_password_for_file → no password set')
        return None
    pwd_blob = entry.get("pwd_blob", "")
    if not pwd_blob:
        return None
    result = decrypt_password(pwd_blob)
    _monitor('api_watch', f'dpapi: get_password_for_file → {"ok" if result else "decrypt FAILED"}')
    return result


def update_password_for_file(file_path: str, new_password: Optional[str]) -> bool:
    """更新文件的密码（或移除密码）。"""
    _monitor('function_watch', f'dpapi: update_password_for_file → {os.path.basename(file_path)}')
    index = load_index()
    entry = next((f for f in index.get("files", []) if f.get("path") == file_path), None)
    if entry is None:
        _monitor('api_watch', 'dpapi: update_password_for_file → entry not found')
        return False

    import time
    if new_password is not None:
        enc = encrypt_password(new_password)
        if enc is None:
            _monitor('api_watch', 'dpapi: update_password_for_file → encrypt failed')
            return False
        entry["pwd_blob"] = enc
        entry["has_password"] = True
        _monitor('variable_watch', 'dpapi: update_password_for_file → password updated')
    else:
        entry["pwd_blob"] = ""
        entry["has_password"] = False
        _monitor('variable_watch', 'dpapi: update_password_for_file → password removed')
    entry["updated_at"] = int(time.time())
    save_index(index)
    return True
