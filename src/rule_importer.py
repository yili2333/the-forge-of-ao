"""
规则导入器 — 集成冲突检测
"""

import uuid
from models import (
    RuleChunk, RuleCategory, RuleSource,
    ImportRuleRequest, ImportRuleItem, ImportRuleResponse,
    RuleConflict
)
from conflict_detector import ConflictDetector
from embedding_service import EmbeddingService
from vector_store import VectorStore
from keyword_store import KeywordStore
import db


class RuleImporter:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        keyword_store: KeywordStore,
    ):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.keyword_store = keyword_store
        self.conflict_detector = ConflictDetector()

    async def import_official_rules(
        self,
        rules: list[RuleChunk],
        check_conflicts: bool = True
    ) -> list[RuleConflict]:
        """
        导入官方规则（批量）
        返回检测到的冲突列表
        """
        conflicts = []

        # 冲突检测
        if check_conflicts:
            existing = await db.get_all_chunks()
            if existing:
                print(f"   🔍 检测冲突: {len(rules)} 条新规则 vs {len(existing)} 条已有规则...")
                rules, conflicts = self.conflict_detector.check_conflicts(rules, existing)

                if conflicts:
                    print(f"   ⚠️  检测到 {len(conflicts)} 个冲突:")
                    for c in conflicts[:10]:
                        icon = {
                            "version_update": "🔄",
                            "duplicate": "📋",
                            "contradiction": "❗",
                            "homebrew_override": "🏠",
                        }.get(c.conflict_type.value, "❓")
                        print(f"      {icon} [{c.conflict_type.value}] {c.description.split(chr(10))[0]}")
                    if len(conflicts) > 10:
                        print(f"      ... 还有 {len(conflicts) - 10} 个")
                    print(f"   ✅ 已自动解决 {sum(1 for c in conflicts if c.auto_resolved)} 个")

                    # 更新已有规则的状态（比如标记为 superseded）
                    for existing_chunk in existing:
                        if existing_chunk.status == "superseded":
                            await db.save_chunk(existing_chunk)

                print(f"   📝 过滤后: {len(rules)} 条有效规则")

        if not rules:
            print("   ℹ️  没有新规则需要导入")
            return conflicts

        # 嵌入
        texts = [self._chunk_to_embed_text(c) for c in rules]
        embeddings = await self.embedding_service.embed_texts(texts)

        # 存储
        for chunk in rules:
            await db.save_chunk(chunk)
        self.vector_store.upsert_chunks(rules, embeddings)
        self.keyword_store.add_chunks(rules)

        print(f"   ✅ 导入完成: {len(rules)} 条规则")
        return conflicts

    async def import_custom_rules(
        self, request: ImportRuleRequest
    ) -> ImportRuleResponse:
        """导入自定义规则"""
        campaign_id = request.campaign_id
        chunks: list[RuleChunk] = []

        for item in request.rules:
            chunk = RuleChunk(
                id=f"homebrew-{campaign_id}-{uuid.uuid4().hex[:8]}",
                title=item.title,
                content=item.content,
                category=item.category,
                source=RuleSource.HOMEBREW,
                parent_context=item.parent_context or f"自定义规则 ({campaign_id})",
                keywords=item.keywords,
                campaign_id=campaign_id,
                priority=10,
                edition="Homebrew",
                status="active",
                related_rule_ids=[]
            )
            chunks.append(chunk)

        # 检测冲突
        existing = await db.get_all_chunks(campaign_id=campaign_id)
        chunks, conflicts = self.conflict_detector.check_conflicts(chunks, existing)

        # 嵌入和存储
        if chunks:
            texts = [self._chunk_to_embed_text(c) for c in chunks]
            embeddings = await self.embedding_service.embed_texts(texts)
            for chunk in chunks:
                await db.save_chunk(chunk)
            self.vector_store.upsert_chunks(chunks, embeddings)
            self.keyword_store.add_chunks(chunks)

        # 构建冲突消息
        conflict_msg = ""
        if conflicts:
            conflict_msg = f" (检测到 {len(conflicts)} 个冲突，已自动处理)"

        return ImportRuleResponse(
            success=True,
            chunks_created=len(chunks),
            message=f"成功导入 {len(chunks)} 条自定义规则到战役 {campaign_id}{conflict_msg}",
            conflicts_found=conflicts,
        )

    async def import_errata(
        self,
        rule_title: str,
        new_content: str,
        errata_note: str,
        source: RuleSource = RuleSource.PHB_2024,
    ) -> list[RuleConflict]:
        """
        导入勘误更新
        自动找到被勘误的旧规则并标记
        """
        chunk = RuleChunk(
            id=f"errata-{uuid.uuid4().hex[:8]}",
            title=rule_title,
            content=new_content,
            category=RuleCategory.GENERAL_RULE,
            source=RuleSource.ERRATA,
            edition="Errata",
            status="active",
            errata_note=errata_note,
            priority=20,  # 勘误优先级高
        )

        return await self.import_official_rules([chunk], check_conflicts=True)

    async def delete_campaign_rules(self, campaign_id: str):
        await db.delete_campaign_rules(campaign_id)
        self.vector_store.delete_by_campaign(campaign_id)
        all_chunks = await db.get_all_chunks()
        self.keyword_store.build_index(all_chunks)

    def _chunk_to_embed_text(self, chunk: RuleChunk) -> str:
        parts = [
            f"Title: {chunk.title}",
            f"Category: {chunk.category.value}",
        ]
        if chunk.parent_context:
            parts.append(f"Context: {chunk.parent_context}")
        parts.append(f"Content: {chunk.content}")
        if chunk.keywords:
            parts.append(f"Keywords: {', '.join(chunk.keywords)}")
        return "\n".join(parts)