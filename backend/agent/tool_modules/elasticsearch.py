"""Elasticsearch 直连工具（HTTP 直接打 _cat / _cluster / _search / _mapping）。"""
from __future__ import annotations

from langchain_core.tools import tool

from ._shared import _es_base_url


@tool
async def es_list_indices(pattern: str = "*") -> str:
    """列出 Elasticsearch 索引。pattern=索引名模式（支持通配符，默认 * 列全部）。
    返回索引名、文档数、存储大小、健康状态等。"""
    import httpx
    base = _es_base_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{base}/_cat/indices/{pattern}",
                params={"format": "json", "s": "index", "h": "index,health,status,docs.count,store.size,pri,rep"},
            )
            resp.raise_for_status()
            data = resp.json()
        if not data:
            return f"ES 未找到匹配 '{pattern}' 的索引"
        lines = [f"**Elasticsearch 索引列表（共 {len(data)} 个）**\n"]
        lines.append(f"{'索引名':<40} {'健康':>6} {'状态':>6} {'文档数':>10} {'大小':>8} {'主分片':>6} {'副本':>4}")
        lines.append("-" * 85)
        for idx in data:
            lines.append(
                f"{idx.get('index',''):<40} "
                f"{idx.get('health','?'):>6} "
                f"{idx.get('status','?'):>6} "
                f"{idx.get('docs.count','0'):>10} "
                f"{idx.get('store.size','?'):>8} "
                f"{idx.get('pri','?'):>6} "
                f"{idx.get('rep','?'):>4}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"查询 ES 索引失败：{e}"


@tool
async def es_cluster_health() -> str:
    """获取 Elasticsearch 集群健康状态，包括节点数、分片数、未分配分片等关键指标。"""
    import httpx
    base = _es_base_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            h = (await client.get(f"{base}/_cluster/health", params={"format": "json"})).json()
            s = (await client.get(f"{base}/_cluster/stats", params={"format": "json"})).json()
        status_icon = {"green": "[正常]", "yellow": "[警告]", "red": "[异常]"}.get(h.get("status", ""), "[未知]")
        lines = [
            f"**ES 集群健康 {status_icon}**",
            f"集群名称  : {h.get('cluster_name')}",
            f"状态      : {h.get('status')}",
            f"节点总数  : {h.get('number_of_nodes')}  数据节点: {h.get('number_of_data_nodes')}",
            f"分片      : 活跃主分片 {h.get('active_primary_shards')} / 活跃总分片 {h.get('active_shards')}",
            f"未分配分片: {h.get('unassigned_shards')}",
            f"初始化中  : {h.get('initializing_shards')}",
            f"索引数    : {s.get('indices', {}).get('count', '?')}",
            f"文档总数  : {s.get('indices', {}).get('docs', {}).get('count', '?')}",
            f"存储总量  : {s.get('indices', {}).get('store', {}).get('size_in_bytes', 0) // 1024 // 1024} MB",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"查询 ES 集群状态失败：{e}"


@tool
async def es_search(index: str, query: str = "", size: int = 10, fields: str = "") -> str:
    """在 Elasticsearch 中搜索文档。
    index=索引名（必填），query=查询关键词（空则返回最新文档），
    size=返回条数（默认10，最大50），fields=指定返回字段（逗号分隔，空则返回全部）。"""
    import httpx
    base = _es_base_url()
    size = min(size, 50)
    body: dict = {"size": size, "sort": [{"@timestamp": {"order": "desc"}}]}
    if query:
        body["query"] = {"query_string": {"query": query}}
    else:
        body["query"] = {"match_all": {}}
    if fields:
        body["_source"] = [f.strip() for f in fields.split(",")]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{base}/{index}/_search", json=body)
            resp.raise_for_status()
            data = resp.json()
        hits = data.get("hits", {})
        total = hits.get("total", {})
        total_count = total.get("value", 0) if isinstance(total, dict) else total
        docs = hits.get("hits", [])
        lines = [f"**ES [{index}] 搜索结果**  总命中: {total_count} 条，返回 {len(docs)} 条\n"]
        for doc in docs:
            src = doc.get("_source", {})
            ts = src.get("@timestamp", src.get("timestamp", ""))
            msg = str(src)[:300]
            lines.append(f"[{ts}] {msg}")
        return "\n".join(lines)
    except Exception as e:
        return f"ES 搜索失败：{e}"


@tool
async def es_get_index_mapping(index: str) -> str:
    """获取 Elasticsearch 索引的字段映射（mapping），了解索引结构和字段类型。
    index=索引名（必填）。"""
    import httpx
    base = _es_base_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base}/{index}/_mapping")
            resp.raise_for_status()
            data = resp.json()
        props = {}
        for idx_data in data.values():
            props.update(idx_data.get("mappings", {}).get("properties", {}))
        if not props:
            return f"索引 [{index}] 无 mapping 信息"
        lines = [f"**索引 [{index}] 字段映射（共 {len(props)} 个字段）**\n"]
        for field, info in list(props.items())[:50]:
            ftype = info.get("type", "object")
            lines.append(f"  {field}: {ftype}")
        if len(props) > 50:
            lines.append(f"  ... 共 {len(props)} 个字段，仅展示前 50 个")
        return "\n".join(lines)
    except Exception as e:
        return f"获取 ES mapping 失败：{e}"


__all__ = ["es_list_indices", "es_cluster_health", "es_search", "es_get_index_mapping"]
