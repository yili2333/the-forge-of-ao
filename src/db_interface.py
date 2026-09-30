"""
数据库接口抽象层
作者: Yang Zixu
功能: 提供统一的数据库接口，支持SQLite和MySQL之间的切换
"""
from abc import ABC, abstractmethod
from models import RuleChunk
from typing import List, Optional


class DatabaseInterface(ABC):
    """数据库接口抽象类"""
    
    @abstractmethod
    async def init_db(self):
        """初始化数据库表"""
        pass
    
    @abstractmethod
    async def save_chunk(self, chunk: RuleChunk):
        """保存规则块"""
        pass
    
    @abstractmethod
    async def get_chunk_by_id(self, chunk_id: str) -> Optional[RuleChunk]:
        """根据ID获取规则块"""
        pass
    
    @abstractmethod
    async def get_chunks_by_ids(self, chunk_ids: List[str]) -> List[RuleChunk]:
        """根据ID列表获取规则块"""
        pass
    
    @abstractmethod
    async def get_all_chunks(self, campaign_id: Optional[str] = None) -> List[RuleChunk]:
        """获取所有规则块"""
        pass
    
    @abstractmethod
    async def delete_campaign_rules(self, campaign_id: str):
        """删除战役相关的规则"""
        pass