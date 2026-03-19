"""Milvus 长期记忆 — 嵌入存储和语义检索历史运维事件"""
import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

COLLECTION = "aiops_incidents"
_DEFAULT_DIM = 1536


class MilvusMemory:
    """
    封装 Milvus 集合的读写操作。
    Collection schema:
      id          INT64  (auto_id, primary)
      embedding   FLOAT_VECTOR(dim)
      mode        VARCHAR(16)      rca / inspect / chat
      user_query  VARCHAR(1024)    用户原始问题
      summary     VARCHAR(8192)    AI 分析结论
      created_at  INT64            unix 时间戳
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

        if not self._client.has_collection(COLLECTION):
            schema = self._client.create_schema(
                auto_id=True, enable_dynamic_field=False
            )
            schema.add_field("id",         DataType.INT64,        is_primary=True)
            schema.add_field("embedding",  DataType.FLOAT_VECTOR, dim=self._dim)
            schema.add_field("mode",       DataType.VARCHAR,      max_length=16)
            schema.add_field("user_query", DataType.VARCHAR,      max_length=1024)
            schema.add_field("summary",    DataType.VARCHAR,      max_length=8192)
            schema.add_field("created_at", DataType.INT64)

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
            logger.info("[milvus] 已创建集合 %s (dim=%d)", COLLECTION, self._dim)

    # ── Embedder 懒初始化 ─────────────────────────────────────────
    def _init_embedder(self):
        if self._embedder is not None:
            return
        from langchain_openai import OpenAIEmbeddings

        # 优先使用独立 embedding 配置，回退到主 LLM 的 base_url
        base_url = (
            os.getenv("EMBEDDING_BASE_URL")
            or os.getenv("AI_BASE_URL", "")
            or None
        )
        api_key = (
            os.getenv("EMBEDDING_API_KEY")
            or os.getenv("AI_API_KEY", "EMPTY")
            or "EMPTY"
        )
        model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

        kwargs: dict = {"model": model, "api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._embedder = OpenAIEmbeddings(**kwargs)
        logger.info("[milvus] embedder model=%s base_url=%s", model, base_url or "openai")

    # ── 同步核心方法（在 to_thread 中运行）────────────────────────
    def _embed(self, text: str) -> list[float]:
        self._init_embedder()
        return self._embedder.embed_query(text)

    def _save_sync(self, mode: str, user_query: str, summary: str):
        self._init_client()
        # 用"问题 + 结论摘要"共同 embed，提升检索相关性
        embed_text = f"{user_query}\n{summary[:400]}"
        vec = self._embed(embed_text)
        self._client.insert(COLLECTION, [{
            "embedding":  vec,
            "mode":       mode[:16],
            "user_query": user_query[:1024],
            "summary":    summary[:8192],
            "created_at": int(time.time()),
        }])
        logger.info("[milvus] 已保存事件 mode=%s query=%s...", mode, user_query[:40])

    def _search_sync(
        self,
        query: str,
        top_k: int = 3,
        mode_filter: Optional[str] = None,
    ) -> list[dict]:
        self._init_client()
        vec = self._embed(query)
        filter_expr = f'mode == "{mode_filter}"' if mode_filter else None
        results = self._client.search(
            collection_name=COLLECTION,
            data=[vec],
            limit=top_k,
            filter=filter_expr,
            output_fields=["mode", "user_query", "summary", "created_at"],
        )
        hits = []
        for r in results[0]:
            hits.append({
                "score":      round(r["distance"], 3),
                "mode":       r["entity"]["mode"],
                "user_query": r["entity"]["user_query"],
                "summary":    r["entity"]["summary"],
                "created_at": r["entity"]["created_at"],
            })
        return hits

    # ── 异步公共接口 ──────────────────────────────────────────────
    async def save(self, mode: str, user_query: str, summary: str) -> None:
        await asyncio.to_thread(self._save_sync, mode, user_query, summary)

    async def search(
        self,
        query: str,
        top_k: int = 3,
        mode_filter: Optional[str] = None,
    ) -> list[dict]:
        return await asyncio.to_thread(self._search_sync, query, top_k, mode_filter)


# 全局单例
_memory: Optional[MilvusMemory] = None


def get_memory() -> MilvusMemory:
    global _memory
    if _memory is None:
        _memory = MilvusMemory()
    return _memory
