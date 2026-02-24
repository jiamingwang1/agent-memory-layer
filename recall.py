"""
上下文回忆引擎 (Contextual Recall Engine)

在新对话开始时，智能注入相关记忆片段。
模仿人脑的"联想回忆"——看到一个线索，自动浮现相关记忆。

核心策略：
1. 时间相关性 — 最近的记忆权重更高
2. 情感相关性 — 情感标记强的记忆更容易浮现
3. 语义相关性 — 跟当前话题相关的记忆（需要embedding）
4. 关系相关性 — 跟当前对话者的共同记忆优先
"""

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None

from layers.episodic import EpisodicMemory, Episode
from layers.relational import RelationalMemory


@dataclass
class RecalledMemory:
    """一条被回忆起来的记忆"""
    source: str          # "episodic" | "relational" | "knowledge"
    content: str         # 记忆内容摘要
    relevance: float     # 0-1 相关度评分
    timestamp: str       # 原始时间
    emotional_weight: float  # 情感权重
    metadata: dict = None    # 额外信息


class ContextualRecall:
    """上下文回忆引擎"""
    
    def __init__(
        self,
        episodic: EpisodicMemory,
        relational: RelationalMemory,
        embedding_api_base: str = None,
        embedding_api_key: str = None,
        embedding_model: str = "text-embedding-3-small",
    ):
        self.episodic = episodic
        self.relational = relational
        self.embedding_api_base = embedding_api_base
        self.embedding_api_key = embedding_api_key
        self.embedding_model = embedding_model
    
    def recall(
        self,
        query: str,
        person_id: str = None,
        max_results: int = 10,
        recency_weight: float = 0.3,
        emotion_weight: float = 0.2,
        semantic_weight: float = 0.5,
    ) -> list[RecalledMemory]:
        """
        给定当前对话开头（query），回忆相关记忆。
        
        三维评分：
        - recency: 越近的记忆分越高（指数衰减）
        - emotion: 情感越强的记忆分越高
        - semantic: 语义越相关的记忆分越高（需embedding）
        
        返回按总分排序的记忆列表。
        """
        candidates = []
        
        # 1. 从情景记忆中拉取候选
        recent_episodes = self.episodic.recent(days=30, limit=100)
        
        now = datetime.now(timezone.utc)
        
        for ep in recent_episodes:
            ep_time = datetime.fromisoformat(ep.timestamp)
            if ep_time.tzinfo is None:
                ep_time = ep_time.replace(tzinfo=timezone.utc)
            
            # 时间衰减：半衰期7天
            hours_ago = (now - ep_time).total_seconds() / 3600
            recency_score = math.exp(-0.693 * hours_ago / (7 * 24))
            
            # 情感得分：用Episode的emotional_weight属性
            emotion_score = ep.emotional_weight
            
            candidates.append({
                "source": "episodic",
                "content": ep.summary,
                "timestamp": ep.timestamp,
                "emotional_weight": ep.emotional_weight,
                "recency_score": recency_score,
                "emotion_score": emotion_score,
                "semantic_score": 0.0,  # 后面填充
                "tags": ep.tags,
                "episode": ep,
            })
        
        # 2. 从关系记忆中拉取（如果指定了对话者）
        if person_id:
            rel = self.relational.get(person_id)
            if rel:
                # 共享上下文作为记忆
                for ctx in rel.shared_contexts:
                    ctx_content = ctx["content"] if isinstance(ctx, dict) else str(ctx)
                    candidates.append({
                        "source": "relational",
                        "content": f"[与{person_id}的共同记忆] {ctx_content}",
                        "timestamp": rel.last_interaction or now.isoformat(),
                        "emotional_weight": rel.temperature / 100.0,
                        "recency_score": 0.5,
                        "emotion_score": rel.temperature / 100.0,
                        "semantic_score": 0.0,
                        "tags": [],
                        "episode": None,
                    })
        
        # 3. 语义相似度（如果有embedding API）
        if self.embedding_api_base and candidates:
            self._fill_semantic_scores(query, candidates)
        
        # 4. 加权求总分
        for c in candidates:
            c["total_score"] = (
                recency_weight * c["recency_score"]
                + emotion_weight * c["emotion_score"]
                + semantic_weight * c["semantic_score"]
            )
        
        # 5. 排序，取topN
        candidates.sort(key=lambda x: x["total_score"], reverse=True)
        
        results = []
        for c in candidates[:max_results]:
            results.append(RecalledMemory(
                source=c["source"],
                content=c["content"],
                relevance=c["total_score"],
                timestamp=c["timestamp"],
                emotional_weight=c["emotional_weight"],
                metadata={"tags": c.get("tags", [])},
            ))
        
        return results
    
    def _fill_semantic_scores(self, query: str, candidates: list[dict]):
        """用embedding API计算语义相似度"""
        if not httpx:
            return
        
        # 收集所有文本
        texts = [query] + [c["content"] for c in candidates]
        
        try:
            resp = httpx.post(
                f"{self.embedding_api_base}/embeddings",
                json={"model": self.embedding_model, "input": texts},
                headers={"Authorization": f"Bearer {self.embedding_api_key}"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            
            embeddings = [item["embedding"] for item in data["data"]]
            query_emb = embeddings[0]
            
            for i, c in enumerate(candidates):
                c["semantic_score"] = self._cosine_similarity(
                    query_emb, embeddings[i + 1]
                )
        except Exception:
            # embedding失败不影响其他维度
            pass
    
    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """余弦相似度"""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return max(0.0, dot / (norm_a * norm_b))
    
    def format_for_injection(
        self,
        memories: list[RecalledMemory],
        max_tokens: int = 2000,
    ) -> str:
        """
        把回忆的记忆格式化成可注入session的文本。
        
        这是最关键的部分——如何把记忆自然地注入对话上下文，
        让Agent"想起来"而不是"被告知"。
        """
        if not memories:
            return ""
        
        lines = ["## 💭 浮现的记忆\n"]
        char_count = 0
        max_chars = max_tokens * 4  # 粗略估算
        
        for m in memories:
            # 格式化时间
            try:
                t = datetime.fromisoformat(m.timestamp)
                time_str = t.strftime("%m/%d %H:%M")
            except Exception:
                time_str = "?"
            
            # 情感强度标记
            if m.emotional_weight > 0.8:
                emotion_tag = "🔥"
            elif m.emotional_weight > 0.5:
                emotion_tag = "💡"
            else:
                emotion_tag = "·"
            
            line = f"{emotion_tag} [{time_str}] {m.content} (相关度:{m.relevance:.0%})\n"
            
            if char_count + len(line) > max_chars:
                break
            
            lines.append(line)
            char_count += len(line)
        
        return "\n".join(lines)
    
    def smart_recall(
        self,
        conversation_opening: str,
        person_id: str = None,
        inject_limit: int = 2000,
    ) -> str:
        """
        一步到位：给定对话开头，返回可注入的记忆文本。
        
        这是对外暴露的主要接口。
        """
        memories = self.recall(
            query=conversation_opening,
            person_id=person_id,
            max_results=8,
        )
        return self.format_for_injection(memories, max_tokens=inject_limit)


# ===== 测试 =====
if __name__ == "__main__":
    import tempfile, os
    
    # 创建临时数据库
    with tempfile.TemporaryDirectory() as tmpdir:
        ep_db = os.path.join(tmpdir, "episodic.db")
        rel_db = os.path.join(tmpdir, "relational.db")
        
        episodic = EpisodicMemory(ep_db)
        relational = RelationalMemory(rel_db)
        
        # 添加测试情景
        episodic.store(Episode(
            id="ep1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            summary="aa确认Agent记忆层是Web4.0核心方向",
            emotional_valence=0.9,
            emotional_arousal=0.85,
            importance_score=0.95,
            participants=["aa"],
            tags=["memory-layer", "web4", "决策"],
        ))
        episodic.store(Episode(
            id="ep2",
            timestamp=datetime.now(timezone.utc).isoformat(),
            summary="翡翠手镯照片收到，开始做宣传",
            emotional_valence=0.6,
            emotional_arousal=0.4,
            importance_score=0.5,
            participants=["aa"],
            tags=["jade", "business"],
        ))
        
        # 添加关系记忆
        relational.record_interaction("aa", quality=0.8)
        relational.add_shared_context("aa", "一起确认了Web4.0方向")
        
        # 测试回忆
        recall = ContextualRecall(episodic, relational)
        result = recall.smart_recall(
            "继续推进记忆层项目",
            person_id="aa",
        )
        
        print("=== 回忆结果 ===")
        print(result)
        
        # 验证
        memories = recall.recall("记忆层", person_id="aa")
        assert len(memories) > 0, "应该回忆起至少一条记忆"
        assert any("记忆" in m.content for m in memories), "应该包含记忆相关内容"
        print("\n✅ 所有测试通过！")
