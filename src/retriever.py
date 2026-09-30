"""
混合检索：向量搜索 + BM25 + 交叉引用补全
这是准确率的核心
"""

from models import RuleChunk, RuleCategory
from vector_store import VectorStore
from keyword_store import KeywordStore
from embedding_service import EmbeddingService
from term_mapper import DnDTermMapper
from config import get_settings
import db

settings = get_settings()


class HybridRetriever:
    def __init__(
        self,
        vector_store: VectorStore,
        keyword_store: KeywordStore,
        embedding_service: EmbeddingService,
    ):
        self.vector_store = vector_store
        self.keyword_store = keyword_store
        self.embedding_service = embedding_service
        self.term_mapper = DnDTermMapper()

    async def retrieve(
        self,
        query: str,
        campaign_id: str | None = None,
        top_k: int | None = None,
    ) -> list[RuleChunk]:
        top_k = top_k or settings.retrieval_top_k

        # ===== 1. 查询预处理 =====
        normalized_query = self.term_mapper.normalize_query(query)
        search_keywords = self.term_mapper.get_search_keywords(query)

        print(f"[Retriever] 原始查询: {query}")
        print(f"[Retriever] 标准化查询: {normalized_query}")
        print(f"[Retriever] 提取术语: {search_keywords}")

        # ===== 2. 向量搜索 =====
        query_embedding = await self.embedding_service.embed_text(normalized_query)
        vector_results = self.vector_store.search(
            query_embedding=query_embedding,
            campaign_id=campaign_id,
            top_k=top_k * 2
        )

        # ===== 3. BM25 关键词搜索 =====
        keyword_query = query + " " + " ".join(search_keywords)
        keyword_results = self.keyword_store.search(
            query=keyword_query,
            campaign_id=campaign_id,
            top_k=top_k * 2
        )

        # ===== 4. RRF 融合排序 =====
        fused = self._reciprocal_rank_fusion(
            result_lists=[vector_results, keyword_results],
            weights=[1.0, 1.0],
            k=60
        )

        # 取 top_k
        top_ids = [item["chunk_id"] for item in fused[:top_k]]

        # ===== 5. 从数据库获取完整chunk =====
        chunks = await db.get_chunks_by_ids(top_ids)

        # 保持融合排序的顺序
        id_to_chunk = {c.id: c for c in chunks}
        ordered_chunks = []
        for item in fused[:top_k]:
            cid = item["chunk_id"]
            if cid in id_to_chunk:
                c = id_to_chunk[cid]
                c.score = item["rrf_score"]
                ordered_chunks.append(c)

        # ===== 6. 交叉引用补全 =====
        enriched = await self._enrich_cross_references(ordered_chunks)

        # ===== 7. 自定义规则优先级处理 =====
        final = self._apply_priority(enriched, campaign_id)

        print(f"[Retriever] 返回 {len(final)} 个规则块")
        for c in final:
            tag = "🏠" if c.source.value == "Homebrew" else "📖"
            print(f"  {tag} [{c.score:.3f}] {c.title} ({c.category.value})")

        return final

    def _reciprocal_rank_fusion(
        self,
        result_lists: list[list[dict]],
        weights: list[float],
        k: int = 60
    ) -> list[dict]:
        """
        RRF 融合排序
        score = Σ weight_i / (k + rank_i)
        """
        rrf_scores: dict[str, float] = {}
        chunk_data: dict[str, dict] = {}

        for results, weight in zip(result_lists, weights):
            for rank, item in enumerate(results):
                cid = item["chunk_id"]
                chunk_data[cid] = item
                if cid not in rrf_scores:
                    rrf_scores[cid] = 0.0
                rrf_scores[cid] += weight / (k + rank + 1)

        # 排序
        sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        return [
            {**chunk_data[cid], "rrf_score": score}
            for cid, score in sorted_items
        ]

    async def _enrich_cross_references(
        self,
        chunks: list[RuleChunk],
        max_extra: int | None = None
    ) -> list[RuleChunk]:
        """
        自动补全被引用的规则
        例如: Sneak Attack 引用了 Advantage → 自动附加 Advantage 规则
        """
        max_extra = max_extra or settings.max_cross_references
        existing_ids = {c.id for c in chunks}
        needed_ids: list[str] = []

        for chunk in chunks:
            for ref_id in chunk.related_rule_ids:
                if ref_id not in existing_ids and ref_id not in needed_ids:
                    needed_ids.append(ref_id)

        # 最多补几个
        needed_ids = needed_ids[:max_extra]

        if needed_ids:
            extra_chunks = await db.get_chunks_by_ids(needed_ids)
            for ec in extra_chunks:
                ec.score = 0.0  # 标记为补充引用
            chunks.extend(extra_chunks)
            print(f"[Retriever] 交叉引用补全 +{len(extra_chunks)} 个")

        return chunks

    def _apply_priority(
        self,
        chunks: list[RuleChunk],
        campaign_id: str | None
    ) -> list[RuleChunk]:
        """
        规则优先级处理:
        1. superseded 的规则降权但保留（用于展示版本差异）
        2. 同名规则按优先级排序
        3. 自定义规则覆盖官方
        4. 2024 版优先于 2014 版
        """
        if not chunks:
            return chunks

        # 按 canonical_title 分组
        by_title: dict[str, list[RuleChunk]] = {}
        for c in chunks:
            key = self._canonical_title(c.title)
            by_title.setdefault(key, []).append(c)

        result = []
        for title, group in by_title.items():
            if len(group) == 1:
                chunk = group[0]
                # 跳过被取代的规则（除非是唯一结果）
                if chunk.status == "superseded":
                    chunk.is_overridden = True
                    chunk.score *= 0.3  # 大幅降权
                result.append(chunk)
                continue

            # 多个同名规则 → 排序
            group.sort(key=lambda c: self._calc_effective_priority(c, campaign_id), reverse=True)

            # 最高优先级的生效
            primary = group[0]
            result.append(primary)

            # 其余的标记为被覆盖，但也保留
            for c in group[1:]:
                c.is_overridden = True
                c.score *= 0.3

                # 给被覆盖的规则添加说明
                if c.status == "superseded":
                    c.errata_note = c.errata_note or f"此规则已被 {primary.source.value} 版本替代"
                elif c.source.value == "Homebrew" or primary.source.value == "Homebrew":
                    c.errata_note = c.errata_note or "存在自定义规则覆盖"
                else:
                    c.errata_note = c.errata_note or f"存在更新版本: {primary.source.value}"

                result.append(c)

        # 按 score 排序
        result.sort(key=lambda c: c.score, reverse=True)
        return result

    def _calc_effective_priority(self, chunk: RuleChunk, campaign_id: str | None) -> float:
        """计算规则的有效优先级"""
        score = chunk.score

        # 状态加权
        status_weight = {
            "active": 1.0,
            "superseded": 0.2,
            "deprecated": 0.1,
            "draft": 0.3,
        }
        score *= status_weight.get(chunk.status, 0.5)

        # 来源加权（2024 > 2014 > SRD）
        source_weight = {
            "PHB 2024": 1.0,
            "DMG 2024": 1.0,
            "MM 2024": 1.0,
            "Errata": 1.1,
            "Basic Rules 2024": 0.9,
            "PHB 2014": 0.6,
            "SRD 5.1 (2014)": 0.5,
            "Homebrew": 0.8,  # 基础权重，campaign 内会 boost
        }
        score *= source_weight.get(chunk.source.value, 0.7)

        # 自定义规则在自己的 campaign 内加权
        if campaign_id and chunk.campaign_id == campaign_id:
            score *= 2.0  # 翻倍

        # priority 字段
        score += chunk.priority * 0.01

        return score

    def _canonical_title(self, title: str) -> str:
        """标准化标题用于匹配"""
        import re
        t = title.lower().strip()
        t = re.sub(r"\s*\(.*?\)\s*", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        for prefix in ["modified ", "enhanced ", "improved ", "homebrew ", "custom "]:
            if t.startswith(prefix):
                t = t[len(prefix):]
        return t