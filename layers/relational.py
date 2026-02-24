"""
关系层 (Relational Layer) — 第四层记忆

对应人脑：前额叶 + 镜像神经元系统
这是最关键的创新层——所有竞品都没做好的部分
"""

import json
import sqlite3
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CommunicationStyle:
    """交流风格模型 — 自动适应用户偏好"""
    preferred_length: str = "medium"  # short/medium/long
    humor_receptivity: float = 0.5    # 0-1
    directness: float = 0.5           # 0(委婉) - 1(直接)
    emoji_usage: float = 0.3          # 0-1
    formality: float = 0.5            # 0(随意) - 1(正式)
    topic_preferences: dict = field(default_factory=dict)  # 话题→偏好深度


@dataclass
class EmotionalModel:
    """用户情绪模型"""
    baseline_mood: str = "neutral"
    mood_triggers: dict = field(default_factory=dict)     # 触发词→情绪
    comfort_strategies: list = field(default_factory=list) # 有效的安慰方式
    stress_indicators: list = field(default_factory=list)  # 压力信号
    current_mood: str = "unknown"
    mood_history: list = field(default_factory=list)       # 最近情绪记录


@dataclass 
class SharedContext:
    """共同的默契/暗语/inside joke"""
    content: str
    created: str
    category: str = "general"  # joke/reference/shorthand/agreement
    last_used: str = ""


@dataclass
class RelationshipState:
    """关系状态 — 每个用户一份"""
    user_id: str
    
    # 关系温度 0-100
    temperature: float = 10.0
    temperature_history: list = field(default_factory=list)
    
    # 交流风格
    style: CommunicationStyle = field(default_factory=CommunicationStyle)
    
    # 默契库
    shared_contexts: list = field(default_factory=list)
    
    # 情绪模型
    emotional_model: EmotionalModel = field(default_factory=EmotionalModel)
    
    # 信任层级 1-5
    trust_level: int = 1
    
    # 元数据
    first_interaction: str = ""
    last_interaction: str = ""
    total_interactions: int = 0
    
    def update_temperature(self, quality: float):
        """更新关系温度 — 升温慢降温快"""
        if quality > 0:
            delta = quality * 0.5   # 慢慢升
        else:
            delta = quality * 2.0   # 快速降
        self.temperature = max(0, min(100, self.temperature + delta))
        self.temperature_history.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "value": self.temperature,
            "delta": delta
        })
        # 只保留最近100条历史
        if len(self.temperature_history) > 100:
            self.temperature_history = self.temperature_history[-100:]
    
    def natural_decay(self, days_since_last: int):
        """自然衰减 — 长期不联系温度下降"""
        if days_since_last > 7:
            self.temperature *= 0.98 ** (days_since_last - 7)


class RelationalMemory:
    """关系层 — 管理所有用户关系"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                user_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
    
    def get(self, user_id: str) -> RelationshipState:
        """获取用户关系状态，不存在则创建"""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT state_json FROM relationships WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        conn.close()
        
        if row:
            return self._deserialize(row[0])
        else:
            state = RelationshipState(
                user_id=user_id,
                first_interaction=datetime.now(timezone.utc).isoformat()
            )
            self.save(state)
            return state
    
    def save(self, state: RelationshipState):
        """保存关系状态"""
        state.last_interaction = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO relationships (user_id, state_json, updated_at)
            VALUES (?, ?, ?)
        """, (
            state.user_id,
            self._serialize(state),
            datetime.now(timezone.utc).isoformat()
        ))
        conn.commit()
        conn.close()
    
    def record_interaction(self, user_id: str, quality: float, 
                           mood: str = "unknown"):
        """记录一次交互"""
        state = self.get(user_id)
        state.total_interactions += 1
        state.update_temperature(quality)
        if mood != "unknown":
            state.emotional_model.current_mood = mood
            state.emotional_model.mood_history.append({
                "time": datetime.now(timezone.utc).isoformat(),
                "mood": mood
            })
            # 只保留最近50条
            if len(state.emotional_model.mood_history) > 50:
                state.emotional_model.mood_history = state.emotional_model.mood_history[-50:]
        self.save(state)
        return state
    
    def add_shared_context(self, user_id: str, content: str, 
                           category: str = "general"):
        """添加默契/共识"""
        state = self.get(user_id)
        ctx = SharedContext(
            content=content,
            created=datetime.now(timezone.utc).isoformat(),
            category=category
        )
        state.shared_contexts.append(asdict(ctx))
        self.save(state)
    
    def get_style_prompt(self, user_id: str) -> str:
        """生成交流风格提示词 — 注入到system prompt"""
        state = self.get(user_id)
        s = state.style
        
        parts = []
        parts.append(f"关系温度: {state.temperature:.0f}/100")
        parts.append(f"信任层级: {state.trust_level}/5")
        parts.append(f"互动次数: {state.total_interactions}")
        
        if state.temperature < 20:
            parts.append("风格: 礼貌友好但保持距离")
        elif state.temperature < 50:
            parts.append("风格: 轻松自然，可以开玩笑")
        elif state.temperature < 80:
            parts.append("风格: 熟悉亲近，像好朋友")
        else:
            parts.append("风格: 非常亲密，可以直说不用客气")
        
        if s.emoji_usage > 0.5:
            parts.append("多用emoji")
        if s.directness > 0.7:
            parts.append("直接说重点")
        if s.humor_receptivity > 0.6:
            parts.append("可以幽默")
        
        if state.emotional_model.current_mood != "unknown":
            parts.append(f"用户当前情绪: {state.emotional_model.current_mood}")
        
        if state.shared_contexts:
            recent = state.shared_contexts[-3:]
            parts.append("近期默契: " + "; ".join(c["content"] for c in recent))
        
        return " | ".join(parts)
    
    def _serialize(self, state: RelationshipState) -> str:
        d = asdict(state)
        return json.dumps(d, ensure_ascii=False)
    
    def _deserialize(self, json_str: str) -> RelationshipState:
        d = json.loads(json_str)
        style = CommunicationStyle(**d.pop("style", {}))
        emotional = EmotionalModel(**d.pop("emotional_model", {}))
        shared = d.pop("shared_contexts", [])
        state = RelationshipState(**d)
        state.style = style
        state.emotional_model = emotional
        state.shared_contexts = shared
        return state
