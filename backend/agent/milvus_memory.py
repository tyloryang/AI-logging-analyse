"""Milvus 长期记忆 — 结构化存储和语义检索历史运维事件"""
import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

COLLECTION = "aiops_incidents"
SCHEMA_VERSION = "v2"          # 修改此值触发自动重建集合
_DEFAULT_DIM = 1536


class MilvusMemory:
    """
    Collection schema (v2):
      id                INT64   auto_id, primary
      embedding         FLOAT_VECTOR(dim)   — 由结构化文本生成
      mode              VARCHAR(16)          rca / inspect / chat
      user_query        VARCHAR(1024)        用户原始问题
      affected_services VARCHAR(512)         涉及的服务或主机（逗号分隔）
      root_cause        VARCHAR(1024)        根因一句话
      resolution        VARCHAR(1024)        处置建议一句话
      full_summary      VARCHAR(8192)        完整报告原文
      schema_ver        VARCHAR(8)           schema 版本，用于自动迁移
      created_at        INT64                unix 时间戳
    """

    def __init__(self):
        self._client = None
        self._embedder = None
        self._dim: int = int(os.getenv("EMBEDDING_DIM", str(_DEFAULT_DIM)))

    # ── Milvus 客户端懒初始化 ─────────────────────────────────────
    def _init_client(self):
        if self._client is not None:
            return
        from pymilvus import DataType, MilvusClient

        host = os.getenv("MILVUS_HOST", "192.168.9.227")
        port = os.getenv("MILVUS_PORT", "19530")
        uri  = f"http://{host}:{port}"
        self._client = MilvusClient(uri=uri)
        logger.info("[milvus] 连接 %s", uri)

        # 检测 schema 版本，旧版自动重建
        if self._client.has_collection(COLLECTION):
            fields = {f["name"] for f in self._client.describe_collection(COLLECTION)["fields"]}
            if "root_cause" not in fields:
                logger.warning("[milvus] 检测到旧版 schema，自动重建集合（原有数据将清空）…")
                self._client.drop_collection(COLLECTION)

        if not self._client.has_collection(COLLECTION):
            schema = self._client.create_schema(auto_id=True, enable_dynamic_field=False)
            schema.add_field("id",                DataType.INT64,        is_primary=True)
            schema.add_field("embedding",         DataType.FLOAT_VECTOR, dim=self._dim)
            schema.add_field("mode",              DataType.VARCHAR,      max_length=16)
            schema.add_field("user_query",        DataType.VARCHAR,      max_length=1024)
            schema.add_field("affected_services", DataType.VARCHAR,      max_length=512)
            schema.add_field("root_cause",        DataType.VARCHAR,      max_length=1024)
            schema.add_field("resolution",        DataType.VARCHAR,      max_length=1024)
            schema.add_field("full_summary",      DataType.VARCHAR,      max_length=8192)
            schema.add_field("schema_ver",        DataType.VARCHAR,      max_length=8)
            schema.add_field("created_at",        DataType.INT64)

            index_params = self._client.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                metric_type="COSINE",
                index_type="HNSW",
                params={"M": 16, "efConstruction": 64},
            )
            self._client.create_collection(
                COLLECTION, schema=schema, index_params=index_params
            )
            logger.info("[milvus] 已创建集合 %s dim=%d schema=%s",
                        COLLECTION, self._dim, SCHEMA_VERSION)

    # ── Embedder 懒初始化 ─────────────────────────────────────────
    def _init_embedder(self):
        if self._embedder is not None:
            return
        from langchain_openai import OpenAIEmbeddings

        provider  = os.getenv("EMBEDDING_PROVIDER", "").lower()
        model     = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

        if provider == "openai":
            api_key  = os.getenv("EMBEDDING_API_KEY", "") or ""
            base_url = None
        elif provider == "local":
            base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv("AI_BASE_URL", "")
            api_key  = os.getenv("EMBEDDING_API_KEY") or os.getenv("AI_API_KEY", "EMPTY") or "EMPTY"
        else:
            # 自动判断：有 EMBEDDING_BASE_URL 走 local，否则走 openai
            base_url = os.getenv("EMBEDDING_BASE_URL") or None
            if base_url:
                api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("AI_API_KEY", "EMPTY") or "EMPTY"
            else:
                api_key = os.getenv("EMBEDDING_API_KEY", "") or ""

        kwargs: dict = {"model": model, "api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._embedder = OpenAIEmbeddings(**kwargs)
        logger.info("[milvus] embedder provider=%s model=%s base_url=%s",
                    provider or "auto", model, base_url or "openai官方")

    # ── 同步核心方法 ──────────────────────────────────────────────
    def _embed(self, text: str) -> list[float]:
        self._init_embedder()
        return self._embedder.embed_query(text)

    @staticmethod
    def _build_embed_text(user_query: str, affected_services: str,
                          root_cause: str, resolution: str,
                          full_summary: str) -> str:
        """
        构造 embed 文本：优先使用结构化字段（检索精度高），
        无结构化数据时降级为 query + summary 摘要。
        """
        if root_cause:
            parts = [f"问题：{user_query}"]
            if affected_services:
                parts.append(f"涉及：{affected_services}")
            parts.append(f"根因：{root_cause}")
            if resolution:
                parts.append(f"处置：{resolution}")
            return "\n".join(parts)
        # 降级
        return f"{user_query}\n{full_summary[:400]}"

    def _save_sync(self, mode: str, user_query: str, full_summary: str,
                   affected_services: str, root_cause: str, resolution: str):
        self._init_client()
        embed_text = self._build_embed_text(
            user_query, affected_services, root_cause, resolution, full_summary
        )
        vec = self._embed(embed_text)
        self._client.insert(COLLECTION, [{
            "embedding":         vec,
            "mode":              mode[:16],
            "user_query":        user_query[:1024],
            "affected_services": affected_services[:512],
            "root_cause":        root_cause[:1024],
            "resolution":        resolution[:1024],
            "full_summary":      full_summary[:8192],
            "schema_ver":        SCHEMA_VERSION,
            "created_at":        int(time.time()),
        }])
        logger.info("[milvus] 已保存 mode=%s affected=%s root_cause=%s…",
                    mode, affected_services[:40], root_cause[:40])

    def _search_sync(self, query: str, top_k: int = 3,
                     mode_filter: Optional[str] = None) -> list[dict]:
        self._init_client()
        vec = self._embed(query)
        filter_expr = f'mode == "{mode_filter}"' if mode_filter else None
        results = self._client.search(
            collection_name=COLLECTION,
            data=[vec],
            limit=top_k,
            filter=filter_expr,
            output_fields=["mode", "user_query", "affected_services",
                           "root_cause", "resolution", "full_summary", "created_at"],
        )
        hits = []
        for r in results[0]:
            hits.append({
                "score":             round(r["distance"], 3),
                "mode":              r["entity"]["mode"],
                "user_query":        r["entity"]["user_query"],
                "affected_services": r["entity"].get("affected_services", ""),
                "root_cause":        r["entity"].get("root_cause", ""),
                "resolution":        r["entity"].get("resolution", ""),
                "full_summary":      r["entity"].get("full_summary", ""),
                "created_at":        r["entity"]["created_at"],
            })
        return hits

    # ── 异步公共接口 ──────────────────────────────────────────────
    async def save(self, mode: str, user_query: str, full_summary: str,
                   affected_services: str = "", root_cause: str = "",
                   resolution: str = "") -> None:
        await asyncio.to_thread(
            self._save_sync, mode, user_query, full_summary,
            affected_services, root_cause, resolution
        )

    async def search(self, query: str, top_k: int = 3,
                     mode_filter: Optional[str] = None) -> list[dict]:
        return await asyncio.to_thread(self._search_sync, query, top_k, mode_filter)


# 全局单例
_memory: Optional[MilvusMemory] = None


def get_memory() -> MilvusMemory:
    global _memory
    if _memory is None:
        _memory = MilvusMemory()
    return _memory
