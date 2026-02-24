"""
睡眠整理 (Sleep Consolidation)

模仿人脑睡眠期间的记忆整理：
- NREM阶段：遗忘琐碎记忆
- REM阶段：强化重要记忆
- 整合阶段：发现跨情景模式，提炼为知识
- 关系维护：温度自然衰减

设计为cron job，建议每天凌晨运行一次。
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from layers.episodic import EpisodicMemory, Episode
from layers.relational import RelationalMemory

try:
    import httpx
except ImportError:
    httpx = None


PATTERN_DISCOVERY_PROMPT = """分析以下最近的对话情景记忆，发现跨情景的模式和规律。

情景列表：
{episodes}

请以JSON格式返回（不要包含markdown代码块标记）：
{{
  "patterns": [
    {{
      "description": "发现的模式或规律",
      "evidence": ["支撑证据1", "支撑证据2"],
      "confidence": 0.5到1.0,
      "category": "behavior/emotion/preference/habit/relationship"
    }}
  ],
  "mood_trend": "用户最近整体情绪趋势（improving/stable/declining/volatile）",
  "relationship_note": "关于用户关系状态的观察（可选，没有就空字符串）"
}}

重点关注：
- 用户的行为模式（比如总是深夜活跃、遇到挫折的应对方式）
- 情绪变化趋势
- 反复提到的主题
- 隐含的需求或期望
"""


class SleepConsolidation:
    """睡眠整理引擎"""
    
    def __init__(self, episodic_db: str = None, relational_db: str = None,
                 api_base: str = None, api_key: str = None, 
                 model: str = "gpt-4o-mini",
                 # 向后兼容：单db_path同时用于两个层
                 db_path: str = None):
        ep_db = episodic_db or db_path or "episodic.db"
        rel_db = relational_db or db_path or "relational.db"
        self.episodic = EpisodicMemory(ep_db)
        self.relational = RelationalMemory(rel_db)
        self.api_base = api_base or os.getenv("OPENAI_API_BASE", "https://ai.t8star.cn/v1")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
    
    def run(self, user_id: str = "default") -> dict:
        """
        执行一次完整的睡眠整理
        
        Returns:
            {"archived": int, "strengthened": int, "patterns": [...], "mood_trend": str}
        """
        result = {
            "archived": 0,
            "strengthened": 0,
            "patterns": [],
            "mood_trend": "unknown",
            "relationship_note": ""
        }
        
        # 阶段1: NREM — 遗忘琐碎记忆
        result["archived"] = self._forget_trivial()
        
        # 阶段2: REM — 强化重要记忆
        result["strengthened"] = self._strengthen_important()
        
        # 阶段3: 整合 — 发现跨情景模式
        patterns = self._integrate_patterns()
        if patterns:
            result["patterns"] = patterns.get("patterns", [])
            result["mood_trend"] = patterns.get("mood_trend", "unknown")
            result["relationship_note"] = patterns.get("relationship_note", "")
        
        # 阶段4: 关系维护 — 温度自然衰减
        self._relationship_maintenance(user_id)
        
        return result
    
    def _forget_trivial(self) -> int:
        """
        NREM阶段：遗忘不重要的情景
        
        规则：重要性低 + 情感淡 + 从未被唤醒 + 超过30天 → 归档
        """
        all_episodes = self.episodic.recent(days=365, limit=1000)
        archived = 0
        
        for ep in all_episodes:
            should_archive = (
                ep.importance_score < 0.3
                and abs(ep.emotional_valence) < 0.2
                and ep.emotional_arousal < 0.2
                and ep.access_count == 0
                and ep.age_days > 30
            )
            if should_archive:
                self.episodic.archive(ep.id)
                archived += 1
        
        return archived
    
    def _strengthen_important(self) -> int:
        """
        REM阶段：强化重要记忆
        
        规则：
        - 高情感唤醒 → 重要性+20%（闪光灯记忆效应）
        - 被频繁唤醒（access_count > 3）→ 重要性+10%
        """
        all_episodes = self.episodic.recent(days=30, limit=100)
        strengthened = 0
        
        for ep in all_episodes:
            changed = False
            
            # 高情感记忆强化
            if ep.emotional_arousal > 0.7:
                new_score = min(1.0, ep.importance_score * 1.2)
                if new_score != ep.importance_score:
                    ep.importance_score = new_score
                    changed = True
            
            # 频繁唤醒的记忆强化
            if ep.access_count > 3:
                new_score = min(1.0, ep.importance_score * 1.1)
                if new_score != ep.importance_score:
                    ep.importance_score = new_score
                    changed = True
            
            if changed:
                self.episodic.store(ep)  # 更新
                strengthened += 1
        
        return strengthened
    
    def _integrate_patterns(self) -> Optional[dict]:
        """
        整合阶段：分析最近情景，发现跨对话模式
        """
        recent = self.episodic.recent(days=7, limit=20)
        if len(recent) < 3:
            return None  # 数据太少
        
        # 格式化情景
        ep_texts = []
        for ep in recent:
            quotes = f" 原话: {ep.key_quotes[0]}" if ep.key_quotes else ""
            ep_texts.append(
                f"- [{ep.timestamp[:10]}] {ep.summary} "
                f"(情感:{ep.emotional_valence:+.1f}, "
                f"唤醒:{ep.emotional_arousal:.1f}, "
                f"重要:{ep.importance_score:.1f}){quotes}"
            )
        
        prompt = PATTERN_DISCOVERY_PROMPT.format(
            episodes="\n".join(ep_texts)
        )
        
        return self._llm_analyze(prompt)
    
    def _relationship_maintenance(self, user_id: str):
        """关系温度自然衰减"""
        state = self.relational.get(user_id)
        if state.last_interaction:
            last = datetime.fromisoformat(state.last_interaction)
            now = datetime.now(timezone.utc)
            days = (now - last).total_seconds() / 86400
            if days > 7:
                state.natural_decay(int(days))
                self.relational.save(state)
    
    def _llm_analyze(self, prompt: str) -> Optional[dict]:
        """调用LLM分析"""
        if not httpx or not self.api_key:
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
            print(f"[SleepConsolidation] LLM分析失败: {e}")
            return None


def run_sleep_cycle(data_dir: str = None, user_id: str = "default",
                    db_path: str = None, **kwargs) -> dict:
    """便捷函数：执行一次睡眠整理"""
    if data_dir:
        kwargs["episodic_db"] = os.path.join(data_dir, "episodic.db")
        kwargs["relational_db"] = os.path.join(data_dir, "relational.db")
    elif db_path:
        kwargs["db_path"] = db_path
    engine = SleepConsolidation(**kwargs)
    return engine.run(user_id)


if __name__ == "__main__":
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else "memory.db"
    user = sys.argv[2] if len(sys.argv) > 2 else "default"
    result = run_sleep_cycle(db, user)
    print(json.dumps(result, ensure_ascii=False, indent=2))
