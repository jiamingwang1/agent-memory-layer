"""
自动固化引擎 (Auto-Consolidation Engine)

模仿人脑从短期记忆到长期记忆的固化过程。
每次对话结束后自动运行：提取情景、更新知识、调整关系。
"""

import json
import uuid
import os
from datetime import datetime, timezone
from typing import Optional

# 使用 OpenAI 兼容接口（贞贞工坊或其他）
try:
    import httpx
except ImportError:
    httpx = None


# 情景提取的 prompt
EPISODE_EXTRACTION_PROMPT = """分析以下对话，提取一个情景记忆单元。

对话内容：
{conversation}

请以JSON格式返回（不要包含markdown代码块标记）：
{{
  "summary": "一句话概括这段对话的核心内容",
  "emotional_valence": 0.0 到 1.0 之间的数（-1极消极，0中性，+1极积极），
  "emotional_arousal": 0.0 到 1.0 之间的数（0平淡，1极激动），
  "importance_score": 0.0 到 1.0 之间的数（日常闲聊0.2，重要决策0.8，改变人生的事1.0），
  "key_quotes": ["对话中最重要的1-3句原文"],
  "tags": ["相关标签，3-5个"],
  "mood": "用户在这段对话中的主要情绪（happy/sad/angry/anxious/hopeful/neutral/excited等）",
  "interaction_quality": -1.0 到 1.0 之间的数（-1对话很差/用户很不满，0普通，+1对话很好/用户很满意）
}}

注意：
- 重点关注用户表达的情感和态度，不只是事实
- key_quotes要保留原文语气，特别是情感强烈的句子
- importance_score要考虑这件事对用户的长期影响
"""

# 事实提取的 prompt
FACT_EXTRACTION_PROMPT = """从以下对话中提取所有新的事实信息（用户偏好、个人信息、决策、约定等）。

对话内容：
{conversation}

请以JSON格式返回（不要包含markdown代码块标记）：
{{
  "explicit_facts": [
    {{"key": "分类:具体项", "value": "事实内容", "confidence": 1.0}}
  ],
  "implicit_facts": [
    {{"fact": "推断的内容", "evidence": "推断依据", "confidence": 0.5到0.9}}
  ]
}}

explicit_facts = 用户明确说出的（confidence始终为1.0）
implicit_facts = 从行为/语气推断的（confidence根据确定性打分）

只提取新信息，跳过AI已经知道的常识。如果没有新事实，返回空数组。
"""


class ConsolidationEngine:
    """自动固化引擎"""
    
    def __init__(self, api_base: str = None, api_key: str = None, 
                 model: str = "gpt-4o-mini"):
        self.api_base = api_base or os.getenv("OPENAI_API_BASE", "https://ai.t8star.cn/v1")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
    
    def consolidate(self, conversation: list[dict], 
                    episodic_memory, relational_memory,
                    user_id: str = "default") -> dict:
        """
        固化一段对话到记忆系统
        
        Args:
            conversation: [{"role": "user"/"assistant", "content": "..."}]
            episodic_memory: EpisodicMemory instance
            relational_memory: RelationalMemory instance
            user_id: 用户ID
            
        Returns:
            {"episode": Episode, "facts": [...], "relationship_update": {...}}
        """
        conv_text = self._format_conversation(conversation)
        result = {}
        
        # 1. 提取情景 → 情景层
        episode_data = self._llm_extract(
            EPISODE_EXTRACTION_PROMPT.format(conversation=conv_text)
        )
        if episode_data:
            from layers.episodic import Episode
            episode = Episode(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc).isoformat(),
                summary=episode_data.get("summary", ""),
                emotional_valence=float(episode_data.get("emotional_valence", 0)),
                emotional_arousal=float(episode_data.get("emotional_arousal", 0)),
                importance_score=float(episode_data.get("importance_score", 0.5)),
                participants=[user_id, "assistant"],
                key_quotes=episode_data.get("key_quotes", []),
                tags=episode_data.get("tags", [])
            )
            episodic_memory.store(episode)
            result["episode"] = episode
            
            # 2. 更新关系 → 关系层
            quality = float(episode_data.get("interaction_quality", 0))
            mood = episode_data.get("mood", "unknown")
            state = relational_memory.record_interaction(user_id, quality, mood)
            result["relationship_update"] = {
                "temperature": state.temperature,
                "mood": mood,
                "quality": quality
            }
        
        # 3. 提取事实 → 知识层（TODO: 接入知识层后启用）
        # fact_data = self._llm_extract(
        #     FACT_EXTRACTION_PROMPT.format(conversation=conv_text)
        # )
        # result["facts"] = fact_data
        
        return result
    
    def _format_conversation(self, conversation: list[dict]) -> str:
        """格式化对话为文本"""
        lines = []
        for msg in conversation:
            role = "用户" if msg["role"] == "user" else "AI"
            content = msg.get("content", "")
            if isinstance(content, list):
                # 处理多模态内容
                content = " ".join(
                    c.get("text", "") for c in content 
                    if isinstance(c, dict) and c.get("type") == "text"
                )
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
    
    def _llm_extract(self, prompt: str) -> Optional[dict]:
        """调用LLM提取信息"""
        if not httpx:
            # fallback: 返回None，跳过LLM提取
            return None
        
        try:
            resp = httpx.post(
                f"{self.api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"}
                },
                timeout=30
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:
            print(f"[ConsolidationEngine] LLM调用失败: {e}")
            return None


# 便捷函数
def consolidate_conversation(conversation: list[dict], 
                              db_path: str = "memory.db",
                              user_id: str = "default",
                              **kwargs) -> dict:
    """一键固化对话"""
    from layers.episodic import EpisodicMemory
    from layers.relational import RelationalMemory
    
    em = EpisodicMemory(db_path)
    rm = RelationalMemory(db_path)
    engine = ConsolidationEngine(**kwargs)
    
    return engine.consolidate(conversation, em, rm, user_id)
