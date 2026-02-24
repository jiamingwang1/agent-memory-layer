"""
五层记忆架构 (Five-Layer Memory Architecture)

Layer 1 - Instinct:  本能/身份锚点 (JSON, 只读为主)
Layer 2 - Knowledge: 知识/事实 (SQLite, SPO三元组)
Layer 3 - Episodic:  情景记忆 (SQLite, 带情感标记)
Layer 4 - Relational: 关系记忆 (SQLite, 温度/风格/默契)
Layer 5 - Meta:      元认知 (JSON, 自我监控)

Support:
- recall.py:         上下文回忆引擎 (三维评分注入)
- consolidation.py:  自动固化引擎 (LLM提取)
"""

from .instinct import InstinctMemory, InstinctProfile
from .knowledge import KnowledgeMemory, Fact
from .episodic import EpisodicMemory, Episode
from .relational import RelationalMemory, RelationshipState
from .meta import MetaMemory

__all__ = [
    "InstinctMemory", "InstinctProfile",
    "KnowledgeMemory", "Fact",
    "EpisodicMemory", "Episode",
    "RelationalMemory", "RelationshipState",
    "MetaMemory",
]
