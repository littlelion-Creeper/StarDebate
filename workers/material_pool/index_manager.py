"""
index_manager.py — 索引持久化 + 增量更新 + 缓存管理
===================================================
管理资料池的文件索引、倒排索引和搜索结果缓存。

索引目录结构 (data_pool/.pool_index/):
  index.json            ← 文件元数据索引
  inverted_index.json   ← 倒排索引（关键词 → 文件）
  cache/                ← 搜索结果缓存
  text_cache/           ← 文件解析后的文本缓存

对外 API:
| 方法 | 说明 |
|------|------|
| load_index(pool_path) → dict | 加载全部索引 |
| save_index(pool_path) | 保存全部索引到磁盘 |
| rebuild_all(pool_path, file_list, parser) → dict | 完全重建索引 |
| incremental_update(pool_path, changed_files, parser) → dict | 增量更新 |
| clear_cache(pool_path) | 清除搜索结果缓存 |
"""

import os
import json as json_module
import hashlib
import time
import shutil


class IndexManager:
    """资料池索引管理器"""

    INDEX_DIR = ".pool_index"
    INDEX_FILE = "index.json"
    INVERTED_FILE = "inverted_index.json"
    CACHE_DIR = "cache"
    TEXT_CACHE_DIR = "text_cache"
    MAX_CACHE_ENTRIES = 50

    # ── 加载 / 保存索引 ────────────────────────────────────

    @staticmethod
    def _get_index_dir(pool_path: str) -> str:
        return os.path.join(pool_path, IndexManager.INDEX_DIR)

    @staticmethod
    def load_index(pool_path: str) -> dict:
        """加载完整索引，返回 {index_dict, inverted_dict}"""
        idx_dir = IndexManager._get_index_dir(pool_path)
        index = {}
        inverted = {}

        index_path = os.path.join(idx_dir, IndexManager.INDEX_FILE)
        if os.path.isfile(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    index = json_module.load(f)
            except (json_module.JSONDecodeError, OSError):
                index = {}

        inverted_path = os.path.join(idx_dir, IndexManager.INVERTED_FILE)
        if os.path.isfile(inverted_path):
            try:
                with open(inverted_path, "r", encoding="utf-8") as f:
                    inverted = json_module.load(f)
            except (json_module.JSONDecodeError, OSError):
                inverted = {}

        return {"files": index, "inverted": inverted}

    @staticmethod
    def save_index(pool_path: str, data: dict):
        """保存索引 {files, inverted} 到磁盘"""
        idx_dir = IndexManager._get_index_dir(pool_path)
        os.makedirs(idx_dir, exist_ok=True)

        index_path = os.path.join(idx_dir, IndexManager.INDEX_FILE)
        try:
            with open(index_path, "w", encoding="utf-8") as f:
                json_module.dump(data.get("files", {}), f, ensure_ascii=False)
        except OSError:
            pass

        inverted_path = os.path.join(idx_dir, IndexManager.INVERTED_FILE)
        try:
            with open(inverted_path, "w", encoding="utf-8") as f:
                json_module.dump(data.get("inverted", {}), f, ensure_ascii=False)
        except OSError:
            pass

    # ── 重建索引 ────────────────────────────────────────────

    @staticmethod
    def rebuild_all(pool_path: str, file_paths: list[str],
                    parser) -> dict:
        """完全重建索引: 扫描所有文件、解析文本、建倒排索引

        Args:
            pool_path: data_pool 目录路径
            file_paths: 文件绝对路径列表
            parser: FileParser 实例或模块

        Returns:
            {files: dict, inverted: dict, counts: {total, indexed, failed}}
        """
        files_index = {}
        inverted_index = {}
        counts = {"total": len(file_paths), "indexed": 0, "failed": 0}
        text_cache_dir = os.path.join(pool_path, IndexManager.INDEX_DIR,
                                       IndexManager.TEXT_CACHE_DIR)
        os.makedirs(text_cache_dir, exist_ok=True)

        for fpath in file_paths:
            if not os.path.isfile(fpath):
                continue
            if not parser.is_supported(fpath):
                continue

            fname = os.path.basename(fpath)
            rel_path = os.path.relpath(fpath, pool_path)

            try:
                # 文件元数据
                stat = os.stat(fpath)
                meta = {
                    "name": fname,
                    "rel_path": rel_path,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "type": os.path.splitext(fname)[1].lower(),
                }

                # 解析文本
                result = parser.parse(fpath)
                if result["success"]:
                    text = result["text"]
                    title = result["title"]
                    meta["total_chars"] = result["total_chars"]
                    meta["title"] = title
                    meta["text_cached"] = True

                    # 缓存文本
                    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
                    text_cache_path = os.path.join(text_cache_dir, f"{text_hash}.txt")
                    try:
                        with open(text_cache_path, "w", encoding="utf-8") as f:
                            f.write(text)
                    except OSError:
                        pass

                    # 构建倒排索引
                    tokens = IndexManager._tokenize(text)
                    for token in tokens:
                        if token not in inverted_index:
                            inverted_index[token] = []
                        inverted_index[token].append(rel_path)

                    meta["hash"] = text_hash
                    meta["error"] = None
                    counts["indexed"] += 1
                else:
                    meta["text_cached"] = False
                    meta["title"] = fname
                    meta["error"] = result.get("error")
                    counts["failed"] += 1

                files_index[rel_path] = meta

            except Exception:
                files_index[rel_path] = {
                    "name": fname, "rel_path": rel_path,
                    "error": "解析异常", "text_cached": False,
                    "title": fname,
                }
                counts["failed"] += 1

        # 去重 + 存入索引
        result = {
            "version": 1,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "files": files_index,
            "inverted": inverted_index,
            "counts": counts,
        }
        IndexManager.save_index(pool_path, result)
        return result

    # ── 增量更新 ────────────────────────────────────────────

    @staticmethod
    def incremental_update(pool_path: str, changed_files: list[str],
                           parser) -> dict:
        """增量更新: 只对变更的文件重新索引

        Args:
            pool_path: data_pool 目录路径
            changed_files: 变更的文件路径列表
            parser: FileParser 实例

        Returns:
            {added: int, updated: int, removed: int, failed: int}
        """
        existing = IndexManager.load_index(pool_path)
        files_index = existing.get("files", {})
        inverted_index = existing.get("inverted", {})
        stats = {"added": 0, "updated": 0, "removed": 0, "failed": 0}

        for fpath in changed_files:
            rel_path = os.path.relpath(fpath, pool_path)

            # 文件被删除 → 从索引移除
            if not os.path.isfile(fpath):
                if rel_path in files_index:
                    old_tokens = IndexManager._get_tokens_for(
                        inverted_index, rel_path)
                    for token in old_tokens:
                        if token in inverted_index:
                            inverted_index[token] = [
                                f for f in inverted_index[token]
                                if f != rel_path
                            ]
                    del files_index[rel_path]
                    stats["removed"] += 1
                continue

            if not parser.is_supported(fpath):
                continue

            fname = os.path.basename(fpath)
            stat = os.stat(fpath)
            meta = {
                "name": fname, "rel_path": rel_path,
                "size": stat.st_size, "mtime": stat.st_mtime,
                "type": os.path.splitext(fname)[1].lower(),
            }

            result = parser.parse(fpath)
            if result["success"]:
                text = result["text"]
                meta["total_chars"] = result["total_chars"]
                meta["title"] = result["title"]
                meta["text_cached"] = True

                # 更新倒排索引
                if rel_path in files_index:
                    old_tokens = IndexManager._get_tokens_for(inverted_index, rel_path)
                    for token in old_tokens:
                        if token in inverted_index:
                            inverted_index[token] = [
                                f for f in inverted_index[token] if f != rel_path
                            ]
                    stats["updated"] += 1
                else:
                    stats["added"] += 1

                # 添加新 tokens
                new_tokens = IndexManager._tokenize(text)
                for token in new_tokens:
                    if token not in inverted_index:
                        inverted_index[token] = []
                    if rel_path not in inverted_index[token]:
                        inverted_index[token].append(rel_path)

                meta["error"] = None
            else:
                meta["text_cached"] = False
                meta["title"] = fname
                meta["error"] = result.get("error")
                stats["failed"] += 1

            files_index[rel_path] = meta

        result = {"files": files_index, "inverted": inverted_index,
                  "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        IndexManager.save_index(pool_path, result)
        result["stats"] = stats
        return result

    # ── 缓存管理 ────────────────────────────────────────────

    @staticmethod
    def clear_cache(pool_path: str):
        """清除搜索结果缓存"""
        cache_dir = os.path.join(pool_path, IndexManager.INDEX_DIR,
                                  IndexManager.CACHE_DIR)
        if os.path.isdir(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)
            os.makedirs(cache_dir, exist_ok=True)

    @staticmethod
    def cache_search_result(pool_path: str, query: str, results: list):
        """缓存搜索结果"""
        cache_dir = os.path.join(pool_path, IndexManager.INDEX_DIR,
                                  IndexManager.CACHE_DIR)
        os.makedirs(cache_dir, exist_ok=True)

        query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
        cache_path = os.path.join(cache_dir, f"{query_hash}.json")

        # LRU 淘汰
        try:
            cache_files = sorted(os.listdir(cache_dir),
                                 key=lambda f: os.path.getmtime(
                                     os.path.join(cache_dir, f)))
            while len(cache_files) >= IndexManager.MAX_CACHE_ENTRIES:
                old = cache_files.pop(0)
                try:
                    os.remove(os.path.join(cache_dir, old))
                except OSError:
                    pass
        except OSError:
            pass

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json_module.dump({
                    "query": query, "time": time.time(),
                    "results": results,
                }, f, ensure_ascii=False)
        except OSError:
            pass

    @staticmethod
    def get_cached_result(pool_path: str, query: str) -> list | None:
        """获取缓存的搜索结果"""
        cache_dir = os.path.join(pool_path, IndexManager.INDEX_DIR,
                                  IndexManager.CACHE_DIR)
        query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
        cache_path = os.path.join(cache_dir, f"{query_hash}.json")

        if not os.path.isfile(cache_path):
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json_module.load(f)
            # 缓存有效期 24 小时
            if time.time() - data.get("time", 0) > 86400:
                return None
            return data.get("results", [])
        except Exception:
            return None

    # ── 工具方法 ────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """中文分词 + 英文 token 化"""
        tokens = []
        try:
            import jieba
            words = jieba.cut_for_search(text)
            for w in words:
                w = w.strip()
                if len(w) >= 2:
                    tokens.append(w)
        except ImportError:
            # 回退: 字符级 n-gram + 空格分词
            # 英文词
            for w in text.lower().split():
                w_stripped = "".join(c for c in w if c.isalpha())
                if len(w_stripped) >= 2:
                    tokens.append(w_stripped)
            # 中文 2-gram
            chars = "".join(c for c in text if "\u4e00" <= c <= "\u9fff")
            for i in range(len(chars) - 1):
                tokens.append(chars[i:i + 2])

        # 去重
        return list(set(tokens))

    @staticmethod
    def _get_tokens_for(inverted: dict, rel_path: str) -> list[str]:
        """获取指定文件的所有 tokens"""
        tokens = []
        for token, files in inverted.items():
            if rel_path in files:
                tokens.append(token)
        return tokens
