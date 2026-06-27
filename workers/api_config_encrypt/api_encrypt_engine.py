"""API 配置透明加解密引擎

使用 cryptography.fernet (Fernet) 对称加密，自动管理密钥生成与存储。
密钥文件: config/.api_key_store（二进制，Windows 下自动隐藏）
配置文件: config/api_config.json（加密后为不可读的 base64 字符串）

所有调用方无需感知加密的存在：
  - decrypted_load() 自动检测并解密密文
  - encrypted_save() 自动加密后写入
  - 向后兼容：如果文件仍是明文 JSON，自动识别
"""

import os
import json

from cryptography.fernet import Fernet, InvalidToken

# ── 监视钩子 ──────────────────────────────────────────────────────────
try:
    from workers.debug_console.debug_monitor_manager import (
        DebugMonitorManager, MONITOR_TAGS
    )
    _TAG_FUNC = MONITOR_TAGS.get("function_watch", "FUNC")
    _TAG_API = MONITOR_TAGS.get("api_watch", "API")
    _TAG_VAR = MONITOR_TAGS.get("variable_watch", "VAR")
except Exception:
    DebugMonitorManager = None
    MONITOR_TAGS = {}
    _TAG_FUNC = "FUNC"
    _TAG_API = "API"
    _TAG_VAR = "VAR"


def _get_monitor():
    """惰性获取 DebugMonitorManager 单例。"""
    if DebugMonitorManager is None:
        return None
    try:
        mgr = DebugMonitorManager.instance()
        return mgr
    except Exception:
        return None


def _emit_func(func_name: str, detail: str = ""):
    """发射 function_watch 监视日志。"""
    mgr = _get_monitor()
    if mgr and mgr.is_monitor_enabled("function_watch"):
        try:
            log_mgr = getattr(mgr, "_log_mgr", None)
            if log_mgr:
                msg = f"{func_name}()" + (f" → {detail}" if detail else "")
                log_mgr.info(f"[{_TAG_FUNC}] {msg}")
        except Exception:
            pass


def _emit_api(detail: str):
    """发射 api_watch 监视日志。"""
    mgr = _get_monitor()
    if mgr and mgr.is_monitor_enabled("api_watch"):
        try:
            log_mgr = getattr(mgr, "_log_mgr", None)
            if log_mgr:
                log_mgr.info(f"[{_TAG_API}] APIEncrypt: {detail}")
        except Exception:
            pass


def _emit_var(var_name: str, value_desc: str):
    """发射 variable_watch 监视日志。"""
    mgr = _get_monitor()
    if mgr and mgr.is_monitor_enabled("variable_watch"):
        try:
            log_mgr = getattr(mgr, "_log_mgr", None)
            if log_mgr:
                log_mgr.info(f"[{_TAG_VAR}] APIEncrypt.{var_name} = {value_desc}")
        except Exception:
            pass


class APIEncryptEngine:
    """API 配置文件透明加解密引擎。

    使用方式:
        engine = APIEncryptEngine(config_dir="e:/StarDebate/config")

        # 保存（自动加密）
        engine.encrypted_save({"api_key": "sk-xxx", ...})

        # 读取（自动解密，无需关心明文/密文）
        config = engine.decrypted_load()  # -> {"api_key": "sk-xxx", ...}
    """

    # ── 文件名常量 ───────────────────────────────────────────────────
    KEY_FILENAME = ".api_key_store"      # 密钥文件（无扩展名）
    CONFIG_FILENAME = "api_config.json"  # 配置文件

    def __init__(self, config_dir: str):
        """初始化引擎。

        Args:
            config_dir: config 目录的绝对路径
        """
        self._config_dir = config_dir
        self._key_path = os.path.join(config_dir, self.KEY_FILENAME)
        self._config_path = os.path.join(config_dir, self.CONFIG_FILENAME)
        self._cipher: Fernet | None = None  # 延迟加载
        _emit_func("__init__", f"config_dir={config_dir}")
        _emit_var("_config_dir", config_dir)

    # ═════════════════════════════════════════════════════════════
    #  密钥管理
    # ═════════════════════════════════════════════════════════════

    def _ensure_key(self) -> Fernet | None:
        """确保密钥存在并返回 Fernet 实例。

        首次调用时:
          如果 .api_key_store 已存在 → 读取并初始化 Fernet
          如果 .api_key_store 不存在 → 自动生成新密钥并存入
        """
        _emit_func("_ensure_key", "entry")
        if self._cipher is not None:
            _emit_func("_ensure_key", "cipher cached")
            return self._cipher

        # ── 已有密钥文件 → 直接读取 ──
        if os.path.isfile(self._key_path):
            try:
                with open(self._key_path, "rb") as f:
                    key = f.read()
                self._cipher = Fernet(key)
                _emit_func("_ensure_key", "loaded existing key")
                _emit_var("_cipher", "Fernet(loaded)")
                return self._cipher
            except Exception:
                _emit_api("key_load_failed")
                return None

        # ── 密钥不存在 → 自动生成 ──
        try:
            key = Fernet.generate_key()
            with open(self._key_path, "wb") as f:
                f.write(key)

            # Windows: 隐藏密钥文件（FILE_ATTRIBUTE_HIDDEN = 2）
            if os.name == "nt":
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(
                        self._key_path, 2
                    )
                except Exception:
                    pass

            self._cipher = Fernet(key)
            _emit_func("_ensure_key", "generated new key")
            _emit_api("key_generated")
            _emit_var("_cipher", "Fernet(new)")
            return self._cipher
        except (OSError, IOError, Exception):
            _emit_api("key_generate_failed")
            return None

    # ═════════════════════════════════════════════════════════════
    #  解密读取
    # ═════════════════════════════════════════════════════════════

    def decrypted_load(self) -> dict:
        """读取 api_config.json，自动检测并解密。

        逻辑:
          1. 文件不存在 → 返回默认值
          2. 尝试 JSON 解析 → 成功则直接返回（明文旧文件，向后兼容）
          3. JSON 解析失败 → 尝试 Fernet 解密 → 返回解密结果
          4. 解密失败 → 返回默认值

        Returns:
            dict: API 配置字典，失败时返回默认值
        """
        _emit_func("decrypted_load", "entry")
        defaults = {
            "api_url": "",
            "api_key": "",
            "model": "deepseek-v4-flash",
        }

        if not os.path.isfile(self._config_path):
            _emit_func("decrypted_load", "file not found → defaults")
            return defaults

        try:
            with open(self._config_path, "rb") as f:
                raw = f.read()

            if not raw:
                _emit_func("decrypted_load", "empty file → defaults")
                return defaults

            # ── 尝试 JSON 解析（未加密的旧文件）──
            try:
                config = json.loads(raw.decode("utf-8"))
                if isinstance(config, dict):
                    _emit_func("decrypted_load", "plaintext JSON (legacy)")
                    _emit_var("api_config_format", "plaintext")
                    return config
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            # ── 非 JSON 文件 → Fernet 解密 ──
            cipher = self._ensure_key()
            if cipher is None:
                _emit_func("decrypted_load", "no cipher available → defaults")
                return defaults

            try:
                decrypted = cipher.decrypt(raw)
                config = json.loads(decrypted.decode("utf-8"))
                _emit_func("decrypted_load", "decrypted Fernet")
                _emit_api("config_decrypted")
                _emit_var("api_config_format", "encrypted_fernet")
                return config if isinstance(config, dict) else defaults
            except InvalidToken:
                _emit_func("decrypted_load", "InvalidToken → defaults")
                _emit_api("decrypt_failed_invalid_token")
                return defaults

        except (OSError, IOError):
            _emit_func("decrypted_load", "IO error → defaults")
            return defaults

    # ═════════════════════════════════════════════════════════════
    #  加密写入
    # ═════════════════════════════════════════════════════════════

    def encrypted_save(self, config: dict) -> bool:
        """加密保存 API 配置到 api_config.json。

        自动：
          1. 序列化为 JSON
          2. 使用 Fernet 加密
          3. 以二进制写入文件
          4. 若密钥不存在则自动生成

        Args:
            config: API 配置字典 (含 api_url, api_key, model 等)

        Returns:
            bool: 保存成功返回 True
        """
        _emit_func("encrypted_save", "entry")
        # 不记录 config 完整内容（含 API Key），只记录关键字段存在性
        has_key = bool(config.get("api_key"))
        has_url = bool(config.get("api_url"))
        model = config.get("model", "?")
        _emit_var("config.hints", f"key={'yes' if has_key else 'no'}, url={'yes' if has_url else 'no'}, model={model}")

        cipher = self._ensure_key()
        if cipher is None:
            _emit_func("encrypted_save", "no cipher → failed")
            return False

        try:
            raw_json = json.dumps(config, ensure_ascii=False, indent=2)
            encrypted = cipher.encrypt(raw_json.encode("utf-8"))
            os.makedirs(self._config_dir, exist_ok=True)
            with open(self._config_path, "wb") as f:
                f.write(encrypted)
            _emit_func("encrypted_save", "success")
            _emit_api("config_saved_encrypted")
            return True
        except (OSError, IOError, Exception):
            import traceback
            traceback.print_exc()
            _emit_func("encrypted_save", "exception → failed")
            _emit_api("save_failed")
            return False

    # ═════════════════════════════════════════════════════════════
    #  状态查询
    # ═════════════════════════════════════════════════════════════

    @property
    def is_encrypted_file(self) -> bool:
        """检查当前磁盘上的配置文件是否为加密状态。"""
        _emit_func("is_encrypted_file", "entry")
        if not os.path.isfile(self._config_path):
            return False
        try:
            with open(self._config_path, "rb") as f:
                raw = f.read()
            if not raw:
                return False
            try:
                json.loads(raw.decode("utf-8"))
                return False  # 合法 JSON → 未加密
            except (json.JSONDecodeError, UnicodeDecodeError):
                return True   # 非 JSON → 已加密
        except (OSError, IOError):
            return False

    @property
    def has_key_file(self) -> bool:
        """检查密钥文件 .api_key_store 是否存在。"""
        return os.path.isfile(self._key_path)

    def migrate_to_encrypted(self, config: dict | None = None) -> bool:
        """强制将配置文件从明文迁移到加密状态。

        如果配置已是明文 JSON，读取后用 encrypted_save 覆盖。
        已在代码流程中自动执行，此方法供手动触发。

        Args:
            config: 可选，指定要写入的配置。为 None 时从当前文件读取。

        Returns:
            bool: 迁移成功返回 True
        """
        _emit_func("migrate_to_encrypted", "entry")
        if config is None:
            config = self.decrypted_load()  # 自动兼容明文/密文
        result = self.encrypted_save(config)
        _emit_func("migrate_to_encrypted", f"→ {'ok' if result else 'failed'}")
        _emit_api("migration_" + ("ok" if result else "failed"))
        return result
