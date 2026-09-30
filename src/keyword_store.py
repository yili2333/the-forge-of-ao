"""
BM25 关键词检索 — 补充向量检索的不足
特别对精确术语匹配效果好
"""

import re
import jieba
from rank_bm25 import BM25Okapi
from models import RuleChunk


class KeywordStore:
    def __init__(self):
        self.chunks: list[RuleChunk] = []
        self.bm25: BM25Okapi | None = None
        self.tokenized_corpus: list[list[str]] = []

    def build_index(self, chunks: list[RuleChunk]):
        """构建 BM25 索引"""
        self.chunks = chunks
        self.tokenized_corpus = [
            self._tokenize(self._chunk_to_text(chunk))
            for chunk in chunks
        ]
        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)

    def add_chunks(self, new_chunks: list[RuleChunk]):
        """增量添加规则块后重建索引"""
        self.chunks.extend(new_chunks)
        self.tokenized_corpus.extend([
            self._tokenize(self._chunk_to_text(chunk))
            for chunk in new_chunks
        ])
        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)

    def add_chunk(self, chunk: RuleChunk):
        """增量添加单个规则块。"""
        self.add_chunks([chunk])

    def remove_chunk(self, chunk_id: str):
        """从索引中移除单个规则块，然后重建 BM25 索引。"""
        idx = next((i for i, c in enumerate(self.chunks) if c.id == chunk_id), None)
        if idx is None:
            return
        self.chunks.pop(idx)
        self.tokenized_corpus.pop(idx)
        self.bm25 = BM25Okapi(self.tokenized_corpus) if self.tokenized_corpus else None

    def search(
        self,
        query: str,
        campaign_id: str | None = None,
        top_k: int = 10
    ) -> list[dict]:
        """BM25 搜索"""
        if not self.bm25 or not self.chunks:
            return []

        tokenized_query = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)

        # 组合 (index, score) 并排序
        scored = list(enumerate(scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scored[:top_k * 2]:  # 多取一些，后面过滤
            chunk = self.chunks[idx]
            # 过滤 campaign
            if campaign_id:
                if chunk.campaign_id is not None and chunk.campaign_id != campaign_id:
                    continue
            else:
                if chunk.campaign_id is not None:
                    continue

            if score > 0:
                results.append({
                    "chunk_id": chunk.id,
                    "score": float(score),
                    "payload": {
                        "chunk_id": chunk.id,
                        "title": chunk.title,
                        "content": chunk.content,
                        "category": chunk.category.value,
                        "source": chunk.source.value,
                        "keywords": chunk.keywords,
                        "parent_context": chunk.parent_context,
                        "related_rule_ids": chunk.related_rule_ids,
                        "priority": chunk.priority,
                        "campaign_id": chunk.campaign_id or "__global__",
                    }
                })

            if len(results) >= top_k:
                break

        return results

    def _chunk_to_text(self, chunk: RuleChunk) -> str:
        """将规则块转为可索引文本"""
        parts = [
            chunk.title,
            chunk.title,  # 标题重复加权
            chunk.content,
            chunk.parent_context,
            " ".join(chunk.keywords)
        ]
        return " ".join(parts)

    def _tokenize(self, text: str) -> list[str]:
        """混合分词：英文按空格 + 中文用jieba"""
        # 先用正则分离中英文
        text = text.lower()
        # 英文单词
        en_tokens = re.findall(r'[a-z]+(?:\'[a-z]+)?', text)
        # 中文用 jieba
        zh_text = re.sub(r'[a-z0-9\s\'\-\.\,\(\)]', ' ', text)
        zh_tokens = list(jieba.cut(zh_text))
        zh_tokens = [t.strip() for t in zh_tokens if t.strip()]

        return en_tokens + zh_tokens