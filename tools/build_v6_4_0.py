"""StarDebate v6.4.0 安装包构建脚本 — Web AI 网页版 + 链式补丁更新器"""
import os, shutil, subprocess, sys, json

ROOT = r"e:\StarDebate"
VER = "6.4.0"
PRE = os.path.join(ROOT, "PRE_Packaged", "v6_4_0")
OUT = os.path.join(ROOT, "Packaged", "v6_4_0")

def _find_python_with_pyinstaller():
    try:
        subprocess.run([sys.executable, "-c", "import PyInstaller"],
                       capture_output=True, check=True)
        return sys.executable
    except Exception:
        pass
    candidates = []
    for p in candidates:
        if os.path.exists(p):
            try:
                subprocess.run([p, "-c", "import PyInstaller"],
                               capture_output=True, check=True)
                return p
            except Exception:
                continue
    raise RuntimeError("找不到带 PyInstaller 的 Python")

BUILD_PYTHON = _find_python_with_pyinstaller()
print(f"[INFO] Build Python: {BUILD_PYTHON}")

EXCLUDE_DIRS = {
    "__pycache__", ".git", ".codebuddy", ".codegraph", ".reasonix",
    "node_modules", "PyQt-SiliconUI-main", "HarmonyApp",
    "plugins", "extensions",
    "backups", "web", "exercise_sessions",
    "temp", "exe_log", "generated-images",
    "updata_packages", "_update_staging",
    "docs", "tools", "临时文件",
    "PRE_Packaged", "Packaged",
}

COPY_DIRS = {
    "components", "workers", "config", "icon", "style",
    "custom_formats", "plugin_manager",
}

FACTORY_CONFIG = {
    "version": "6.4.0",
    "last_project": "",
    "theme": "notion_dark",
    "simplify_tree_names": True,
    "auto_check_github_update": True,
    "last_viewed_intro_version": "",
    "developer_mode": False,
    "disabled_features": [],
    "auto_save_on_switch": True,
    "show_nav_labels": False,
}

BOOT_PY = r'''"""StarDebate ★ 辩之星 — 极简 PyInstaller 引导器

此文件是唯一被编译进 EXE 的 Python 代码。
启动后将 sys.path 指向 exe 同级目录（与源码版布局一致），然后导入真正的 StarDebate 主程序。
"""
import os
import sys
import multiprocessing

if sys.platform == "win32":
    try:
        import ctypes
        _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if _hwnd:
            ctypes.windll.user32.ShowWindow(_hwnd, 0)
    except Exception:
        pass

if __name__ == "__main__":
    multiprocessing.freeze_support()
    exe_dir = os.path.dirname(sys.executable)
    sys.path.insert(0, exe_dir)
    os.chdir(exe_dir)
    mod = __import__("StarDebate")
    mod.main_loop()
'''

BUILD_SPEC = '''# -*- mode: python ; coding: utf-8 -*-
"""StarDebate v6.4.0 PyInstaller 打包配置"""
block_cipher = None
datas_items = []

HIDDEN_IMPORTS = [
    'PyQt5.QtSvg',
    'PyQt5.QtNetwork',
    'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtWebEngineCore',
    'json', 'sqlite3',
    'requests', 'urllib3', 'charset_normalizer', 'certifi', 'idna',
    'time', 're', 'hashlib', 'shutil', 'zipfile', 'logging', 'traceback',
    'copy', 'importlib', 'importlib.util', 'importlib.machinery',
    'ctypes', 'typing', 'base64', 'io', 'enum', 'math',
    'html', 'html.parser', 'urllib', 'urllib.request', 'urllib.parse',
    'ssl', 'threading', 'concurrent', 'concurrent.futures',
    'functools', 'itertools', 'collections', 'uuid', 'socket', 'struct',
    'textwrap', 'sip', 'platform',
    'multiprocessing', 'multiprocessing.queues',
    'multiprocessing.synchronize', 'multiprocessing.managers',
    'xml', 'xml.parsers.expat',
    'cryptography', 'cryptography.fernet',
    'cryptography.hazmat', 'cryptography.hazmat.primitives',
    'cryptography.hazmat.primitives.kdf.pbkdf2',
    'cryptography.hazmat.backends',
    'cryptography.hazmat.backends.default_backend',
    'imghdr',
    # siui / PyQt-SiliconUI
    'numpy', 'typing_extensions', 'dateutil',
    # v6.4.0: Web AI 网页版 (Playwright 延迟导入，需显式声明)
    'playwright',
    'playwright.sync_api',
    'playwright._impl',
    'playwright._impl._api_structures',
    'playwright._impl._connection',
    'playwright._impl._errors',
    'playwright._impl._helper',
    'playwright._impl._greenlets',
    'playwright._impl._locator',
    'playwright._impl._network',
    'playwright._impl._api_types',
    'playwright.async_api',
]

EXCLUDES = [
    'StarDebate', 'StarDebate_app', 'star_debate_log',
    'workers', 'workers.*', 'components', 'components.*',
    'debug_console', 'debug_console.*',
    'PyQt5.QtBluetooth', 'PyQt5.QtDBus', 'PyQt5.QtHelp',
    'PyQt5.QtLocation', 'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets',
    'PyQt5.QtNfc', 'PyQt5.QtOpenGL', 'PyQt5.QtPositioning',
    'PyQt5.QtPrintSupport', 'PyQt5.QtQuick', 'PyQt5.QtQuickWidgets',
    'PyQt5.QtRemoteObjects', 'PyQt5.QtSensors', 'PyQt5.QtSerialPort',
    'PyQt5.QtSql', 'PyQt5.QtTest', 'PyQt5.QtWebChannel',
    'PyQt5.QtWebSockets', 'PyQt5.QtXml', 'PyQt5.QtXmlPatterns',
]

a = Analysis(
    ['boot.py'], pathex=[], binaries=[], datas=datas_items,
    hiddenimports=HIDDEN_IMPORTS, hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=EXCLUDES, noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
          name='StarDebate', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=True, upx_exclude=[], runtime_tmpdir=None,
          console=False, disable_windowed_traceback=False,
          argv_emulation=False, target_arch=None,
          codesign_identity=None, entitlements_file=None,
          icon='StarDebate.ico')
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
               strip=False, upx=True, upx_exclude=[], name='StarDebate')
'''


def copy_snapshot():
    if os.path.exists(PRE):
        shutil.rmtree(PRE)
    os.makedirs(PRE, exist_ok=True)
    count = 0
    for item in sorted(os.listdir(ROOT)):
        s = os.path.join(ROOT, item)
        d = os.path.join(PRE, item)
        if item.startswith(".") or item in EXCLUDE_DIRS:
            continue
        if item.endswith((".zip", ".sep")):
            continue
        if os.path.isdir(s):
            if item not in COPY_DIRS:
                continue
            shutil.copytree(s, d, dirs_exist_ok=True,
                          ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            count += 1
            print(f"  [DIR]  {item}/")
        elif item.endswith(".py"):
            shutil.copy2(s, d)
            count += 1
            print(f"  [FILE] {item}")
    ico_src = os.path.join(ROOT, "StarDebate.ico")
    shutil.copy2(ico_src, os.path.join(PRE, "StarDebate.ico"))
    cfg_path = os.path.join(PRE, "config", "config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(FACTORY_CONFIG, f, ensure_ascii=False, indent=2)
    print(f"  [RESET] config/config.json -> factory defaults")
    with open(os.path.join(PRE, "boot.py"), "w", encoding="utf-8") as f:
        f.write(BOOT_PY)
    with open(os.path.join(PRE, "build.spec"), "w", encoding="utf-8") as f:
        f.write(BUILD_SPEC)
    print(f"  [GEN]  boot.py + build.spec")
    print(f"\nSnapshot: {count} items -> {PRE}")


def run_pyinstaller():
    for d in [os.path.join(OUT, "StarDebate"), os.path.join(OUT, "build")]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"  [CLEAN] {d}")
    print("PyInstaller building (3-8 min)...")
    spec = os.path.join(PRE, "build.spec")
    workpath = os.path.join(OUT, "build")
    result = subprocess.run(
        [BUILD_PYTHON, "-m", "PyInstaller", spec,
         "--distpath=" + OUT, "--workpath=" + workpath,
         "--noconfirm"],
        cwd=PRE, capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        print("ERROR: PyInstaller failed")
        tail = result.stderr[-3000:] if len(result.stderr) > 3000 else result.stderr
        print(tail)
        return False
    print("OK")
    return True


def deploy():
    os.makedirs(OUT, exist_ok=True)
    exe_src = os.path.join(OUT, "StarDebate", "StarDebate.exe")
    if os.path.exists(exe_src):
        shutil.copy2(exe_src, os.path.join(OUT, "StarDebate.exe"))
    for f in ["StarDebate.py", "StarDebate_app.py", "star_debate_log.py",
              "StarDebate.ico"]:
        src = os.path.join(PRE, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(OUT, f))
    for d in COPY_DIRS:
        src = os.path.join(PRE, d)
        dst = os.path.join(OUT, d)
        if os.path.exists(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst, dirs_exist_ok=True)
    print("Deploy OK")


def write_iss():
    prev_iss = None
    for v in ["v6_3_2", "v6_3_0", "v6_2_10"]:
        p = os.path.join(ROOT, "Packaged", v, "StarDebate_Setup.iss")
        if os.path.exists(p):
            prev_iss = p
            break
    if not prev_iss:
        print("WARN: No previous ISS found, skipping ISS generation")
        return None
    with open(prev_iss, "r", encoding="utf-8") as f:
        content = f.read()
    import re
    m = re.search(r'#define MyAppVersion "([^"]+)"', content)
    if m:
        content = content.replace(m.group(1), VER)
    # 确保 extensions/ 和 plugins/ 被 ISS 排除
    for kw in ['Source: "extensions', 'Source: "plugins\\*"']:
        if kw in content:
            idx = content.find(kw)
            line_start = content.rfind("\n", 0, idx) + 1
            line_end = content.find("\n", idx)
            if line_end == -1: line_end = len(content)
            content = content[:line_start] + content[line_end:]
    dst = os.path.join(OUT, "StarDebate_Setup.iss")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(content)
    return dst


def main():
    print(f"=== StarDebate v{VER} Build ===\n")
    print("[1/4] Snapshot...")
    copy_snapshot()
    print(f"\n[2/4] Output dir: {OUT}\n")
    print("[3/4] PyInstaller...")
    if not run_pyinstaller():
        return
    print("\n[4/4] Deploy + ISS...")
    deploy()
    iss_path = write_iss()
    build_dir = os.path.join(OUT, "build")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    size_mb = 0
    try:
        size_mb = sum(os.path.getsize(os.path.join(dp, f))
                      for dp, _, fs in os.walk(OUT) for f in fs) // (1024 * 1024)
    except Exception:
        pass
    print(f"\n=== Build Complete ===")
    print(f"  Output: {OUT}")
    print(f"  Size: ~{size_mb} MB")
    if iss_path:
        print(f"\nNext: Compile with Inno Setup 6:")
        print(f'  iscc "{iss_path}"')


if __name__ == "__main__":
    main()
