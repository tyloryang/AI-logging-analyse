"""知识图谱查询工具：实体上下游关系 + 影响面遍历。"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
async def query_knowledge_graph(entity: str, depth: int = 1) -> str:
    """查询运维知识图谱中某个实体的上下游关系（依赖、拓扑、调度、影响面）。
    entity 可传服务名、Pod 名、主机名/IP、K8s 节点名等。
    depth=1 查直接邻居，depth=2 做两跳影响面遍历（谁会被它连累）。
    做根因分析、评估故障影响范围、追依赖链路时使用。"""
    try:
        import asyncio

        from services import knowledge_graph as kg

        result = await asyncio.to_thread(kg.neighbors, entity, depth)
        if not result.get("found"):
            hint = result.get("hint", "")
            return f"知识图谱中未找到实体「{entity}」。{hint}"

        center = result["center"]
        nodes = result.get("nodes", {})
        lines = [
            f"**知识图谱 / {center['name']}**"
            f"（类型={center['kind']}"
            + (f"，环境={center['env']}" if center.get("env") else "") + "）",
            f"邻居 {result['neighbor_count']} 个，关系 {len(result['relations'])} 条：",
        ]
        # 按关系类型归组
        by_rel: dict[str, list[str]] = {}
        for r in result["relations"]:
            other_id = r["to"] if r["direction"] == "→" else r["from"]
            info = nodes.get(other_id, {})
            label = f"{info.get('name', other_id)}[{info.get('kind', '?')}]"
            arrow = f"{r['rel']} {r['direction']}"
            by_rel.setdefault(arrow, []).append(label)
        for rel, targets in by_rel.items():
            uniq = list(dict.fromkeys(targets))[:12]
            lines.append(f"- {rel}：{', '.join(uniq)}")
        return "\n".join(lines)
    except Exception as e:
        return f"知识图谱查询失败：{e}"


@tool
async def rebuild_knowledge_graph() -> str:
    """重建运维知识图谱（从 CMDB + K8s + SkyWalking 拓扑全量采集）。
    当拓扑变化较大、图谱查询提示实体缺失时使用。"""
    try:
        from services import knowledge_graph as kg

        stats = await kg.build_graph()
        return (f"知识图谱重建完成：{stats.get('nodes', 0)} 个节点，"
                f"{stats.get('edges', 0)} 条关系。")
    except Exception as e:
        return f"知识图谱重建失败：{e}"


__all__ = ["query_knowledge_graph", "rebuild_knowledge_graph"]
