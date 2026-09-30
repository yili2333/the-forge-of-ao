"""
使用 Qdrant 内存模式 — 开发时无需任何外部服务
生产环境改为连接 Qdrant 服务器即可
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny,
    models
)
from models import RuleChunk
from config import get_settings
import json

settings = get_settings()

COLLECTION_NAME = "dnd_rules"


class VectorStore:
    def __init__(self):
        # 内存模式 — 开发/测试用
        # 生产环境改为: QdrantClient(host="localhost", port=6333)
        self.client = QdrantClient(":memory:")
        self._collection_created = False

    def _ensure_collection(self, size: int | None = None):
        collections = self.client.get_collections().collections
        names = [c.name for c in collections]
        if COLLECTION_NAME not in names:
            dims = size or settings.embedding_dimensions
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=dims,
                    distance=Distance.COSINE
                )
            )
            self._collection_created = True

    def upsert_chunk(self, chunk: RuleChunk, embedding: list[float]):
        """插入或更新单个规则块"""
        self._ensure_collection(size=len(embedding))
        point = PointStruct(
            id=self._str_to_int_id(chunk.id),
            vector=embedding,
            payload={
                "chunk_id": chunk.id,
                "title": chunk.title,
                "content": chunk.content,
                "category": chunk.category.value,
                "source": chunk.source.value,
                "page": chunk.page,
                "parent_context": chunk.parent_context,
                "related_rule_ids": chunk.related_rule_ids,
                "keywords": chunk.keywords,
                "level_requirement": chunk.level_requirement,
                "campaign_id": chunk.campaign_id or "__global__",
                "priority": chunk.priority,
            }
        )
        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point]
        )

    def upsert_chunks(
        self,
        chunks: list[RuleChunk],
        embeddings: list[list[float]]
    ):
        """批量插入"""
        if embeddings:
            self._ensure_collection(size=len(embeddings[0]))
        points = []
        for chunk, emb in zip(chunks, embeddings):
            points.append(PointStruct(
                id=self._str_to_int_id(chunk.id),
                vector=emb,
                payload={
                    "chunk_id": chunk.id,
                    "title": chunk.title,
                    "content": chunk.content,
                    "category": chunk.category.value,
                    "source": chunk.source.value,
                    "page": chunk.page,
                    "parent_context": chunk.parent_context,
                    "related_rule_ids": chunk.related_rule_ids,
                    "keywords": chunk.keywords,
                    "level_requirement": chunk.level_requirement,
                    "campaign_id": chunk.campaign_id or "__global__",
                    "priority": chunk.priority,
                }
            ))

        # 分批上传
        batch_size = 100
        for i in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=points[i:i + batch_size]
            )

    def search(
        self,
        query_embedding: list[float],
        campaign_id: str | None = None,
        top_k: int = 10,
        category_filter: str | None = None
    ) -> list[dict]:
        """向量相似度搜索"""
        # 构建过滤条件：官方规则 + 该campaign的自定义规则
        must_conditions = []
        if campaign_id:
            must_conditions.append(
                FieldCondition(
                    key="campaign_id",
                    match=MatchAny(any=["__global__", campaign_id])
                )
            )
        else:
            must_conditions.append(
                FieldCondition(
                    key="campaign_id",
                    match=MatchValue(value="__global__")
                )
            )

        if category_filter:
            must_conditions.append(
                FieldCondition(
                    key="category",
                    match=MatchValue(value=category_filter)
                )
            )

        search_filter = Filter(must=must_conditions) if must_conditions else None

        response = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            query_filter=search_filter,
            limit=top_k,
            with_payload=True
        )

        return [
            {
                "chunk_id": r.payload["chunk_id"],
                "score": r.score,
                "payload": r.payload
            }
            for r in response.points
        ]

    def delete_chunk(self, chunk_id: str):
        """从向量索引中删除单个规则块。"""
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.PointIdsList(
                points=[self._str_to_int_id(chunk_id)]
            ),
        )

    def delete_by_campaign(self, campaign_id: str):
        """删除某个campaign的所有自定义规则"""
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="campaign_id",
                            match=MatchValue(value=campaign_id)
                        )
                    ]
                )
            )
        )

    @staticmethod
    def _str_to_int_id(s: str) -> int:
        """Qdrant 需要 int id，把字符串哈希为 int"""
        return int(hashlib.md5(s.encode()).hexdigest()[:16], 16)


import hashlib