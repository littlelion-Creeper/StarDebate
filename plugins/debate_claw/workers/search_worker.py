"""
DebateClaw 搜索工作线程
========================
封装 SerpAPI / Bing 搜索和 URL 抓取功能。
支持配置化搜索提供商，返回摘要结果。
"""

import json, os, re
import requests


# ── 配置加载 ──

def _load_search_config() -> dict:
    """加载搜索配置（从 ai_config.json）。"""
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "config", "ai_config.json")
    defaults = {
        "search_provider": "serpapi",
        "search_api_key": "",
        "search_engine": "google",
        "network_enabled": False,
    }
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            defaults.update({k: v for k, v in cfg.items()
                            if k in defaults and v is not None})
    except Exception:
        pass
    return defaults


def _summarize_text(text: str, max_len: int = 2000) -> str:
    """将文本截断/摘要到指定长度。"""
    if len(text) <= max_len:
        return text
    # 保留开头 + 截断标记
    return f"{text[:max_len]}\n\n[... 内容过长，已自动截断 ...]"


# ══════════════════════════════════════════
#  SerpAPI 搜索
# ══════════════════════════════════════════

def _serpapi_search(query: str, api_key: str, engine: str = "google") -> str:
    """调用 SerpAPI 执行搜索，返回摘要结果。

    Args:
        query: 搜索关键词
        api_key: SerpAPI Key
        engine: 搜索引擎 (google/bing/baidu)

    Returns:
        搜索结果的摘要文本
    """
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": api_key,
        "engine": engine,
        "num": 5,  # 返回前 5 条
        "hl": "zh-cn",
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    results = []
    organic = data.get("organic_results", [])
    for i, item in enumerate(organic[:5], 1):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        results.append(f"{i}. **{title}**\n   {snippet}\n   🔗 {link}")

    if not results:
        return f"未找到关于「{query}」的搜索结果"

    summary = (
        f"🔍 搜索「{query}」的结果（共 {len(organic)} 条）：\n\n"
        + "\n\n".join(results)
    )
    return _summarize_text(summary)


# ══════════════════════════════════════════
#  Bing Search API
# ══════════════════════════════════════════

def _bing_search(query: str, api_key: str) -> str:
    """调用 Azure/Bing Search API 执行搜索。

    Args:
        query: 搜索关键词
        api_key: Bing API Key

    Returns:
        搜索结果的摘要文本
    """
    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {
        "q": query,
        "count": 5,
        "setLang": "zh-Hans",
        "mkt": "zh-CN",
    }

    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    results = []
    web_pages = data.get("webPages", {}).get("value", [])
    for i, item in enumerate(web_pages[:5], 1):
        title = item.get("name", "")
        snippet = item.get("snippet", "")
        link = item.get("url", "")
        results.append(f"{i}. **{title}**\n   {snippet}\n   🔗 {link}")

    if not results:
        return f"未找到关于「{query}」的搜索结果"

    summary = (
        f"🔍 搜索「{query}」的结果（共 {len(web_pages)} 条）：\n\n"
        + "\n\n".join(results)
    )
    return _summarize_text(summary)


# ══════════════════════════════════════════
#  URL 抓取与内容摘要
# ══════════════════════════════════════════

def _fetch_url_content(url: str) -> str:
    """抓取 URL 内容并返回摘要。

    Args:
        url: 要抓取的 URL

    Returns:
        页面内容摘要
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        return (
            f"📄 已获取 {url}\n"
            f"类型: {content_type}\n"
            f"大小: {len(resp.content):,} 字节\n"
            f"[非 HTML 内容，无法提取文本]"
        )

    html = resp.text

    # 简单 HTML 标签去除（不依赖 BeautifulSoup）
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    if len(text) < 100:
        return (
            f"📄 已获取 {url}\n"
            f"大小: {len(html):,} 字符\n"
            f"[页面内容过少或为空]"
        )

    return (
        f"📄 网页内容：{url}\n"
        f"原始大小: {len(html):,} 字符\n\n"
        f"--- 提取文本 ---\n\n"
        + _summarize_text(text, max_len=3000)
    )


# ══════════════════════════════════════════
#  公共接口
# ══════════════════════════════════════════

def network_search(url_or_query: str) -> str:
    """联网搜索或抓取 URL（公共接口）。

    判断输入是 URL 还是查询词：
    - 含 http:// 或 https:// → 调用 URL 抓取
    - 其他 → 调用搜索引擎

    Args:
        url_or_query: URL 地址或搜索关键词

    Returns:
        搜索/抓取结果的摘要文本

    Raises:
        Exception: 搜索失败或 API 未配置
    """
    cfg = _load_search_config()

    if not cfg.get("network_enabled"):
        raise PermissionError(
            "网络权限未启用。\n"
            "请在 ai_config.json 中设置 \"network_enabled\": true 并配置搜索 API Key"
        )

    api_key = cfg.get("search_api_key", "")
    provider = cfg.get("search_provider", "serpapi")

    # 判断是 URL 还是查询词
    if url_or_query.startswith(("http://", "https://")):
        return _fetch_url_content(url_or_query)

    # 需要搜索
    if not api_key:
        raise PermissionError(
            "搜索 API Key 未配置。\n"
            "请在 ai_config.json 中设置 search_api_key 字段"
        )

    try:
        if provider == "serpapi":
            return _serpapi_search(url_or_query, api_key,
                                   cfg.get("search_engine", "google"))
        elif provider == "bing":
            return _bing_search(url_or_query, api_key)
        else:
            raise ValueError(f"不支持的搜索提供商: {provider}")
    except requests.exceptions.RequestException as ex:
        raise Exception(f"网络请求失败：{ex}")
    except Exception as ex:
        raise Exception(f"搜索执行失败：{ex}")


def search_files(query: str) -> str:
    """在项目目录和资料池中搜索关键词。

    Args:
        query: 搜索关键词（支持正则）

    Returns:
        匹配文件列表及上下文摘要
    """
    from workers.plugin_manager import get_api as _get_api

    api = _get_api()
    proot = api.get_current_project_path() if api else os.getcwd()
    results = []
    total_matches = 0

    # 搜索项目根目录
    if proot and os.path.isdir(proot):
        matches = _search_in_dir(proot, query, max_results=20)
        results.extend(matches)
        total_matches += len(matches)

    # 搜索资料池
    pool_dir = os.path.join(proot, "data_pool") if proot else ""
    if pool_dir and os.path.isdir(pool_dir):
        matches = _search_in_dir(pool_dir, query, max_results=10)
        results.extend(matches)
        total_matches += len(matches)

    if not results:
        return f"未找到包含「{query}」的文件"

    header = f"🔎 搜索「{query}」的结果（共匹配 {total_matches} 处）：\n\n"
    body = "\n".join(f"- **{r['file']}** (第{r['line']}行)\n  `{r['context'][:120]}`"
                      for r in results[:30])

    return _summarize_text(header + body, max_len=3000)


def _search_in_dir(directory: str, query: str, max_results: int = 20) -> list:
    """递归搜索目录中的文件内容。"""
    import fnmatch

    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    # 排除的目录
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv",
                 ".idea", ".vscode", "build", "dist"}

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for fname in files:
            # 排除非文本文件
            ext = os.path.splitext(fname)[1].lower()
            if ext not in {".txt", ".md", ".py", ".js", ".json", ".csv",
                          ".html", ".css", ".xml", ".yaml", ".yml",
                          ".docx", ".pdf"}:
                continue

            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for line_no, line in enumerate(f, 1):
                        if pattern.search(line):
                            rel = os.path.relpath(fpath, directory)
                            results.append({
                                "file": rel,
                                "line": line_no,
                                "context": line.strip(),
                            })
                            if len(results) >= max_results:
                                return results
            except (IOError, OSError):
                continue

    return results
