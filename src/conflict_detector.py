"""
规则冲突检测引擎
在规则导入时自动检测冲突，并提供解决方案
"""

import hashlib
import re
import uuid
from datetime import datetime

from models import (
    RuleChunk, RuleConflict, ConflictType,
    RuleSource, RuleStatus
)

# ===== 来源优先级（数字越大越优先）=====
SOURCE_PRIORITY = {
    RuleSource.HOMEBREW: 100,  # 自定义最高
    RuleSource.ERRATA: 90,  # 勘误次之
    RuleSource.PHB_2024: 80,  # 2024 > 2014
    RuleSource.DMG_2024: 80,
    RuleSource.MM_2024: 80,
    RuleSource.BASIC_RULES: 70,
    RuleSource.PHB_2014: 50,
    RuleSource.SRD_2014: 40,  # SRD 优先级最低
}

# 同一版本内的来源优先级
EDITION_PRIORITY = {
    "Homebrew": 100,
    "Errata": 90,
    "PHB 2024": 80,
    "DMG 2024": 80,
    "MM 2024": 80,
    "Basic Rules 2024": 70,
    "SRD 5.1 (2014)": 40,
    "PHB 2014": 50,
}


class ConflictDetector:
    """规则冲突检测和解决"""

    def __init__(self):
        pass

    def check_conflicts(
            self,
            new_chunks: list[RuleChunk],
            existing_chunks: list[RuleChunk]
    ) -> tuple[list[RuleChunk], list[RuleConflict]]:
        """
        检测新导入的规则与已有规则之间的冲突

        返回:
        - processed_chunks: 处理后的规则列表（已标记状态）
        - conflicts: 检测到的冲突列表
        """
        conflicts: list[RuleConflict] = []
        processed = list(new_chunks)  # 复制一份

        # 建立已有规则的索引
        existing_by_canonical = {}
        existing_by_hash = {}

        for chunk in existing_chunks:
            canon = self._canonical_title(chunk.title)
            if canon not in existing_by_canonical:
                existing_by_canonical[canon] = []
            existing_by_canonical[canon].append(chunk)

            content_hash = self._content_hash(chunk.content)
            existing_by_hash[content_hash] = chunk

        # 逐条检测
        for new_chunk in processed:
            new_canon = self._canonical_title(new_chunk.title)
            new_hash = self._content_hash(new_chunk.content)
            new_chunk.canonical_title = new_canon
            new_chunk.content_hash = new_hash

            # 检测1: 完全重复
            if new_hash in existing_by_hash:
                existing = existing_by_hash[new_hash]
                conflict = RuleConflict(
                    id=f"conflict-{uuid.uuid4().hex[:8]}",
                    conflict_type=ConflictType.DUPLICATE,
                    rule_a_id=existing.id,
                    rule_a_title=existing.title,
                    rule_a_source=existing.source.value,
                    rule_b_id=new_chunk.id,
                    rule_b_title=new_chunk.title,
                    rule_b_source=new_chunk.source.value,
                    description=f"内容完全相同的重复规则: '{new_chunk.title}'",
                    resolution="自动跳过重复规则",
                    auto_resolved=True,
                )
                conflicts.append(conflict)
                new_chunk.status = "deprecated"  # 标记为废弃
                continue

            # 检测2: 同名不同内容（版本更新或矛盾）
            if new_canon in existing_by_canonical:
                for existing in existing_by_canonical[new_canon]:
                    # 跳过同一个 chunk
                    if existing.id == new_chunk.id:
                        continue

                    # 跳过不同 campaign 的自定义规则
                    if (existing.campaign_id and new_chunk.campaign_id
                            and existing.campaign_id != new_chunk.campaign_id):
                        continue

                    conflict_type, resolution = self._classify_conflict(
                        existing, new_chunk
                    )

                    conflict = RuleConflict(
                        id=f"conflict-{uuid.uuid4().hex[:8]}",
                        conflict_type=conflict_type,
                        rule_a_id=existing.id,
                        rule_a_title=existing.title,
                        rule_a_source=existing.source.value,
                        rule_b_id=new_chunk.id,
                        rule_b_title=new_chunk.title,
                        rule_b_source=new_chunk.source.value,
                        description=self._describe_conflict(
                            existing, new_chunk, conflict_type
                        ),
                        resolution=resolution,
                        auto_resolved=True,
                    )
                    conflicts.append(conflict)

                    # 自动解决：标记旧版本为 superseded
                    self._auto_resolve(existing, new_chunk, conflict_type)

        # 过滤掉重复的
        processed = [c for c in processed if c.status != "deprecated"]

        return processed, conflicts

    def _classify_conflict(
            self,
            existing: RuleChunk,
            new_chunk: RuleChunk
    ) -> tuple[ConflictType, str]:
        """判断冲突类型并给出解决方案"""

        existing_priority = self._get_priority(existing)
        new_priority = self._get_priority(new_chunk)

        # 自定义 vs 官方
        if new_chunk.source == RuleSource.HOMEBREW:
            return (
                ConflictType.HOMEBREW_OVERRIDE,
                f"自定义规则 '{new_chunk.title}' 覆盖官方规则"
            )

        if existing.source == RuleSource.HOMEBREW:
            return (
                ConflictType.HOMEBREW_OVERRIDE,
                f"已有自定义规则 '{existing.title}'，保留自定义版本"
            )

        # 勘误
        if new_chunk.source == RuleSource.ERRATA:
            return (
                ConflictType.VERSION_UPDATE,
                f"勘误更新: '{new_chunk.title}' 替代旧版本"
            )

        # 版本更新 (2024 vs 2014)
        is_2024_new = "2024" in (new_chunk.source.value + new_chunk.edition)
        is_2014_existing = "2014" in (existing.source.value + existing.edition)

        if is_2024_new and is_2014_existing:
            return (
                ConflictType.VERSION_UPDATE,
                f"2024版 '{new_chunk.title}' 替代2014版"
            )

        is_2014_new = "2014" in (new_chunk.source.value + new_chunk.edition)
        is_2024_existing = "2024" in (existing.source.value + existing.edition)

        if is_2014_new and is_2024_existing:
            return (
                ConflictType.VERSION_UPDATE,
                f"已有2024版，新导入的2014版标记为旧版本"
            )

        # SRD vs PHB（同版本，PHB更详细）
        if "SRD" in new_chunk.source.value and "SRD" not in existing.source.value:
            return (
                ConflictType.DUPLICATE,
                f"已有更详细的版本，跳过 SRD 版本"
            )

        if "SRD" in existing.source.value and "SRD" not in new_chunk.source.value:
            return (
                ConflictType.VERSION_UPDATE,
                f"用更详细的版本替代 SRD 版本"
            )

        # 默认：内容矛盾
        return (
            ConflictType.CONTRADICTION,
            f"同名规则内容不同，保留优先级更高的版本"
        )

    def _auto_resolve(
            self,
            existing: RuleChunk,
            new_chunk: RuleChunk,
            conflict_type: ConflictType
    ):
        """自动解决冲突：标记状态和优先级"""

        existing_priority = self._get_priority(existing)
        new_priority = self._get_priority(new_chunk)

        if conflict_type == ConflictType.HOMEBREW_OVERRIDE:
            if new_chunk.source == RuleSource.HOMEBREW:
                # 新的是自定义 → 新的生效，旧的标记
                existing.is_overridden = True
                new_chunk.priority = max(new_chunk.priority, existing.priority + 10)
            else:
                # 旧的是自定义 → 保留旧的
                new_chunk.is_overridden = True

        elif conflict_type == ConflictType.VERSION_UPDATE:
            if new_priority >= existing_priority:
                # 新版本优先级更高 → 旧版本标记为 superseded
                existing.status = "superseded"
                existing.superseded_by = new_chunk.id
                new_chunk.supersedes = existing.id
                new_chunk.priority = max(new_chunk.priority, existing.priority + 1)
            else:
                # 旧版本优先级更高（比如已有2024，新导入2014）
                new_chunk.status = "superseded"
                new_chunk.superseded_by = existing.id

        elif conflict_type == ConflictType.DUPLICATE:
            if new_priority >= existing_priority:
                existing.status = "superseded"
                existing.superseded_by = new_chunk.id
            else:
                new_chunk.status = "deprecated"

        elif conflict_type == ConflictType.CONTRADICTION:
            # 矛盾的两个都保留，但标记高优先级的
            if new_priority >= existing_priority:
                new_chunk.priority = max(new_chunk.priority, existing.priority + 1)
                existing.errata_note = f"存在同名规则冲突，另一版本: {new_chunk.id}"
            else:
                new_chunk.errata_note = f"存在同名规则冲突，另一版本: {existing.id}"

    def _get_priority(self, chunk: RuleChunk) -> int:
        """计算规则的综合优先级"""
        base = 0

        # 来源优先级
        try:
            source_enum = RuleSource(chunk.source) if isinstance(chunk.source, str) else chunk.source
            base = SOURCE_PRIORITY.get(source_enum, 50)
        except (ValueError, KeyError):
            base = 50

        # 自定义的 priority 字段
        base += chunk.priority

        # campaign 规则额外加分
        if chunk.campaign_id:
            base += 20

        return base

    def _canonical_title(self, title: str) -> str:
        """
        标准化标题，用于匹配同名规则
        "Sneak Attack" = "sneak attack" = "Sneak Attack (Rogue)"
        """
        t = title.lower().strip()
        # 去除括号内容
        t = re.sub(r"\s*\(.*?\)\s*", " ", t)
        # 去除多余空格
        t = re.sub(r"\s+", " ", t).strip()
        # 去除常见前缀/后缀
        for prefix in ["modified ", "enhanced ", "improved ", "homebrew ", "custom "]:
            if t.startswith(prefix):
                t = t[len(prefix):]
        return t

    def _content_hash(self, content: str) -> str:
        """内容哈希，用于检测完全重复"""
        # 标准化内容后取哈希
        normalized = re.sub(r"\s+", " ", content.lower().strip())
        return hashlib.md5(normalized.encode()).hexdigest()

    def _describe_conflict(
            self,
            existing: RuleChunk,
            new_chunk: RuleChunk,
            conflict_type: ConflictType
    ) -> str:
        """生成人类可读的冲突描述"""
        descriptions = {
            ConflictType.VERSION_UPDATE: (
                f"版本更新: '{new_chunk.title}'\n"
                f"  旧版: {existing.source.value} (ID: {existing.id})\n"
                f"  新版: {new_chunk.source.value} (ID: {new_chunk.id})"
            ),
            ConflictType.DUPLICATE: (
                f"重复规则: '{new_chunk.title}'\n"
                f"  已有: {existing.source.value}\n"
                f"  新增: {new_chunk.source.value}"
            ),
            ConflictType.CONTRADICTION: (
                f"内容矛盾: '{new_chunk.title}'\n"
                f"  版本A: {existing.source.value}\n"
                f"  版本B: {new_chunk.source.value}\n"
                f"  两个版本的措辞或数值不同"
            ),
            ConflictType.HOMEBREW_OVERRIDE: (
                f"自定义覆盖: '{new_chunk.title}'\n"
                f"  官方: {existing.source.value}\n"
                f"  自定义: {new_chunk.source.value}"
            ),
        }
        return descriptions.get(conflict_type, f"未知冲突: {new_chunk.title}")


# ===== 便捷函数 =====

def detect_and_resolve(
        new_chunks: list[RuleChunk],
        existing_chunks: list[RuleChunk]
) -> tuple[list[RuleChunk], list[RuleConflict]]:
    """
    一键检测并解决冲突

    使用:
        processed, conflicts = detect_and_resolve(new_rules, existing_rules)
        for c in conflicts:
            print(f"[{c.conflict_type}] {c.description}")
    """
    detector = ConflictDetector()
    return detector.check_conflicts(new_chunks, existing_chunks)