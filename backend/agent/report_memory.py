"""Milvus 报告向量库 — 存储运维日报/巡检日报/慢日志报告，支持语义检索"""
import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

COLLECTION   = "aiops_reports"
SCHEMA_VER   = "v2"          # 修改触发自动重建集合
_DEFAULT_DIM = 1536


def _trunc_bytes(s: str, max_bytes: int) -> str:
    """按 UTF-8 字节数安全截断字符串，避免超出 Milvus VARCHAR max_length"""
    encoded = s.encode("utf-8")
    if len(encoded) <= max_bytes:
        return s
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


class ReportMemory:
    """
    Collection schema:
      id           INT64   auto_id, primary
      embedding    FLOAT_VECTOR(dim)
      report_id    VARCHAR(64)   文件名（无 .json），用于去重和跳转
      report_type  VARCHAR(16)   daily / inspect / slowlog
      title        VARCHAR(200)
      date_str     VARCHAR(10)   YYYY-MM-DD
      health_score INT64
      top_issues   VARCHAR(512)  主要问题（服务名/异常项，逗号分隔）
      ai_summary   VARCHAR(8192) ai_analysis 前 2000 字
      created_at   INT64         unix 时间戳
    """

    def __init__(self):
        self._client   = None
        self._embedder = None
        self._dim: int = int(os.getenv("EMBEDDING_DIM", str(_DEFAULT_DIM)))
        self._unavailable = False   # 连接失败后置 True，后续跳过不再重试

    # ── 懒初始化 ──────────────────────────────────────────────────
    def _init_client(self):
        if self._unavailable:
            raise RuntimeError("Milvus 不可用（已跳过）")
        if self._client is not None:
            return
        from pymilvus import DataType, MilvusClient

        host = os.getenv("MILVUS_HOST", "192.168.9.227")
        port = os.getenv("MILVUS_PORT", "19530")
        uri  = f"http://{host}:{port}"
        try:
            self._client = MilvusClient(uri=uri, timeout=5.0)
            logger.info("[report_memory] 连接 Milvus %s", uri)
        except Exception as e:
            self._unavailable = True
            logger.warning("[report_memory] 连接失败，向量库功能已禁用，仅使用本地存储: %s", e)
            raise

        # 检测 schema 版本和向量维度，不匹配自动重建
        if self._client.has_collection(COLLECTION):
            desc         = self._client.describe_collection(COLLECTION)
            fields       = {f["name"]: f for f in desc["fields"]}
            existing_dim = fields.get("embedding", {}).get("params", {}).get("dim", 0)
            max_length   = fields.get("ai_summary", {}).get("params", {}).get("max_length", 0)
            if existing_dim != self._dim or max_length < 65535:
                logger.warning(
                    "[report_memory] schema 不匹配（dim: %d → %d），自动重建集合…",
                    existing_dim, self._dim,
                )
                self._client.drop_collection(COLLECTION)

        if not self._client.has_collection(COLLECTION):
            self._create_collection()

    def _create_collection(self):
        from pymilvus import DataType
        schema = self._client.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field("id",          DataType.INT64,        is_primary=True)
        schema.add_field("embedding",   DataType.FLOAT_VECTOR, dim=self._dim)
        schema.add_field("report_id",   DataType.VARCHAR,      max_length=64)
        schema.add_field("report_type", DataType.VARCHAR,      max_length=16)
        schema.add_field("title",       DataType.VARCHAR,      max_length=200)
        schema.add_field("date_str",    DataType.VARCHAR,      max_length=10)
        schema.add_field("health_score",DataType.INT64)
        schema.add_field("top_issues",  DataType.VARCHAR,      max_length=512)
        schema.add_field("ai_summary",  DataType.VARCHAR,      max_length=65535)
        schema.add_field("created_at",  DataType.INT64)

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
        logger.info("[report_memory] 已创建集合 %s dim=%d", COLLECTION, self._dim)

    def _init_embedder(self):
        if self._embedder is not None:
            return
        from langchain_openai import OpenAIEmbeddings

        provider = os.getenv("EMBEDDING_PROVIDER", "").lower()
        model    = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

        if provider == "openai":
            api_key  = os.getenv("EMBEDDING_API_KEY", "") or ""
            base_url = None
        elif provider == "local":
            base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv("AI_BASE_URL", "")
            api_key  = os.getenv("EMBEDDING_API_KEY") or os.getenv("AI_API_KEY", "EMPTY") or "EMPTY"
        else:
            base_url = os.getenv("EMBEDDING_BASE_URL") or None
            if base_url:
                api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("AI_API_KEY", "EMPTY") or "EMPTY"
            else:
                api_key = os.getenv("EMBEDDING_API_KEY", "") or ""

        kwargs: dict = {"model": model, "api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._embedder = OpenAIEmbeddings(**kwargs)

    def _embed(self, text: str) -> list[float]:
        self._init_embedder()
        return self._embedder.embed_query(text)

    # ── 工具方法 ──────────────────────────────────────────────────
    @staticmethod
    def _report_to_row(report: dict) -> dict | None:
        """把日报 dict 转为 Milvus 行（不含 embedding）。返回 None 表示跳过。"""
        ai_analysis = report.get("ai_analysis", "")
        if not ai_analysis:
            return None  # 无 AI 分析内容则跳过

        report_type = report.get("type", "daily")
        title       = report.get("title", "")
        created_at  = report.get("created_at", "")
        date_str    = created_at[:10] if created_at else ""
        report_id   = report.get("id", "")

        # 主要问题摘要
        if report_type == "daily":
            top_issues = ", ".join(
                e["service"] for e in report.get("top10_errors", [])[:5]
            )
        elif report_type == "inspect":
            top_issues = ", ".join(
                i["item"] for i in report.get("top_issues", [])[:5]
            )
        elif report_type == "slowlog":
            top_issues = ", ".join(
                r["host_ip"] for r in report.get("host_results", [])[:5]
            )
        else:
            top_issues = ""

        return {
            "report_id":   _trunc_bytes(report_id, 64),
            "report_type": report_type,
            "title":       _trunc_bytes(title, 200),
            "date_str":    date_str,
            "health_score":int(report.get("health_score", 0)),
            "top_issues":  _trunc_bytes(top_issues, 512),
            "ai_summary":  _trunc_bytes(ai_analysis, 60000),
            "created_at":  int(time.mktime(
                __import__("datetime").datetime.fromisoformat(
                    created_at.replace("Z", "+00:00")
                ).timetuple()
            ) if created_at else time.time()),
        }

    @staticmethod
    def _build_embed_text(row: dict) -> str:
        """构造 embed 文本，结合标题、类型、问题摘要、AI分析片段"""
        type_label = {"daily": "运维日报", "inspect": "巡检日报", "slowlog": "慢日志报告"}.get(
            row["report_type"], row["report_type"]
        )
        parts = [
            f"{type_label} {row['date_str']} 健康评分:{row['health_score']}",
        ]
        if row["top_issues"]:
            parts.append(f"主要问题: {row['top_issues']}")
        parts.append(row["ai_summary"][:600])
        return "\n".join(parts)

    def _exists_sync(self, report_id: str) -> bool:
        """检查 report_id 是否已入库（避免重复写入）"""
        try:
            results = self._client.query(
                collection_name=COLLECTION,
                filter=f'report_id == "{report_id}"',
                output_fields=["report_id"],
                limit=1,
            )
            return len(results) > 0
        except Exception:
            return False

    def _save_sync(self, report: dict):
        self._init_client()
        row = self._report_to_row(report)
        if row is None:
            return
        # 去重：已存在则跳过
        if self._exists_sync(row["report_id"]):
            logger.debug("[report_memory] 已存在，跳过: %s", row["report_id"])
            return
        embed_text = self._build_embed_text(row)
        row["embedding"] = self._embed(embed_text)
        self._client.insert(COLLECTION, [row])
        logger.info("[report_memory] 已入库: %s (%s)", row["report_id"], row["report_type"])

    def _search_sync(self, query: str, top_k: int = 5,
                     report_type: str = "") -> list[dict]:
        self._init_client()
        vec = self._embed(query)
        filter_expr = f'report_type == "{report_type}"' if report_type else None
        results = self._client.search(
            collection_name=COLLECTION,
            data=[vec],
            limit=top_k,
            filter=filter_expr,
            output_fields=[
                "report_id", "report_type", "title", "date_str",
                "health_score", "top_issues", "ai_summary", "created_at",
            ],
        )
        hits = []
        for r in results[0]:
            hits.append({
                "score":       round(r["distance"], 3),
                "report_id":   r["entity"]["report_id"],
                "report_type": r["entity"]["report_type"],
                "title":       r["entity"]["title"],
                "date_str":    r["entity"]["date_str"],
                "health_score":r["entity"]["health_score"],
                "top_issues":  r["entity"].get("top_issues", ""),
                "ai_summary":  r["entity"].get("ai_summary", ""),
                "created_at":  r["entity"]["created_at"],
            })
        return hits

    def _batch_import_sync(self, reports_dir: str) -> tuple[int, int]:
        """从 reports_dir 批量导入，返回 (成功数, 跳过数)"""
        import glob, json
        self._init_client()
        files = sorted(glob.glob(os.path.join(reports_dir, "*.json")))
        ok = skipped = 0
        for fpath in files:
            try:
                with open(fpath, encoding="utf-8") as fp:
                    report = json.load(fp)
                if not report.get("ai_analysis"):
                    skipped += 1
                    continue
                row = self._report_to_row(report)
                if row is None:
                    skipped += 1
                    continue
                if self._exists_sync(row["report_id"]):
                    skipped += 1
                    continue
                embed_text = self._build_embed_text(row)
                row["embedding"] = self._embed(embed_text)
                self._client.insert(COLLECTION, [row])
                ok += 1
                logger.info("[report_memory] 批量导入: %s", row["report_id"])
            except Exception as exc:
                logger.warning("[report_memory] 导入失败 %s: %s", fpath, exc)
                skipped += 1
        return ok, skipped

    # ── 异步公共接口 ──────────────────────────────────────────────
    async def save(self, report: dict) -> None:
        if self._unavailable:
            return
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._save_sync, report),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            self._unavailable = True
            logger.warning("[report_memory] save 超时，向量库已标记不可用")
        except Exception as exc:
            logger.warning("[report_memory] save 失败（不影响使用）: %s", exc)

    async def search(self, query: str, top_k: int = 5,
                     report_type: str = "") -> list[dict]:
        if self._unavailable:
            return []
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._search_sync, query, top_k, report_type),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            self._unavailable = True
            logger.warning("[report_memory] search 超时，向量库已标记不可用")
            return []
        except Exception as exc:
            logger.warning("[report_memory] search 失败，返回空结果: %s", exc)
            return []

    async def batch_import(self, reports_dir: str) -> tuple[int, int]:
        if self._unavailable:
            logger.info("[report_memory] 向量库不可用，跳过批量导入")
            return 0, 0
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._batch_import_sync, reports_dir),
                timeout=300.0,
            )
        except asyncio.TimeoutError:
            self._unavailable = True
            logger.warning("[report_memory] 批量导入超时，向量库已标记不可用")
            return 0, 0
        except Exception as exc:
            logger.warning("[report_memory] 批量导入失败: %s", exc)
            return 0, 0

    @property
    def available(self) -> bool:
        return not self._unavailable


# 全局单例
_report_memory: Optional[ReportMemory] = None


def get_report_memory() -> ReportMemory:
    global _report_memory
    if _report_memory is None:
        _report_memory = ReportMemory()
    return _report_memory
