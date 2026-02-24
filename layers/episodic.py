"""
情景层 (Episodic Layer) — 第三层记忆

对应人脑：海马体的情景记忆功能
存储：带情感标记的对话片段，不是全量日志
"""

import json
import math
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Episode:
    """一个情景记忆单元"""
    id: str
    timestamp: str  # ISO format
    summary: str
    emotional_valence: float = 0.0      # -1(消极) 到 +1(积极)
    emotional_arousal: float = 0.0      # 0(平淡) 到 1(激动)
    importance_score: float = 0.5       # 0-1
    participants: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    key_quotes: list[str] = field(default_factory=list)  # 原文关键句
    tags: list[str] = field(default_factory=list)
    linked_episodes: list[str] = field(default_factory=list)
    access_count: int = 0
    
    @property
    def age_days(self) -> float:
        created = datetime.fromisoformat(self.timestamp)
        now = datetime.now(timezone.utc)
        return (now - created).total_seconds() / 86400
    
    @property
    def emotional_weight(self) -> float:
        """情感权重 — 模拟人脑闪光灯记忆效应"""
        base = self.importance_score
        emotional_boost = self.emotional_arousal * 0.3
        valence_boost = abs(self.emotional_valence) * 0.2
        if self.emotional_valence < 0:
            valence_boost *= 1.2  # 负面偏差
        decay_rate = 0.01 * (1 - self.emotional_arousal * 0.5)
        time_decay = math.exp(-decay_rate * self.age_days)
        access_boost = math.log1p(self.access_count) * 0.1
        return (base + emotional_boost + valence_boost + access_boost) * time_decay


class EpisodicMemory:
    """情景层 — 时序+语义+情感多维索引"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                summary TEXT NOT NULL,
                emotional_valence REAL DEFAULT 0.0,
                emotional_arousal REAL DEFAULT 0.0,
                importance_score REAL DEFAULT 0.5,
                participants TEXT DEFAULT '[]',
                context TEXT DEFAULT '{}',
                key_quotes TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                linked_episodes TEXT DEFAULT '[]',
                access_count INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodes_timestamp 
            ON episodes(timestamp DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodes_importance 
            ON episodes(importance_score DESC)
        """)
        conn.commit()
        conn.close()
    
    def store(self, episode: Episode) -> str:
        """存储一个情景"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO episodes 
            (id, timestamp, summary, emotional_valence, emotional_arousal,
             importance_score, participants, context, key_quotes, tags,
             linked_episodes, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            episode.id, episode.timestamp, episode.summary,
            episode.emotional_valence, episode.emotional_arousal,
            episode.importance_score,
            json.dumps(episode.participants),
            json.dumps(episode.context),
            json.dumps(episode.key_quotes),
            json.dumps(episode.tags),
            json.dumps(episode.linked_episodes),
            episode.access_count
        ))
        conn.commit()
        conn.close()
        return episode.id
    
    def get(self, episode_id: str) -> Optional[Episode]:
        """获取并唤醒（增加access_count）"""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM episodes WHERE id = ? AND archived = 0", 
            (episode_id,)
        ).fetchone()
        if not row:
            conn.close()
            return None
        # 唤醒：增加访问计数
        conn.execute(
            "UPDATE episodes SET access_count = access_count + 1 WHERE id = ?",
            (episode_id,)
        )
        conn.commit()
        conn.close()
        return self._row_to_episode(row)
    
    def recent(self, days: int = 7, limit: int = 20) -> list[Episode]:
        """获取最近的情景"""
        conn = sqlite3.connect(self.db_path)
        cutoff = datetime.now(timezone.utc).isoformat()
        rows = conn.execute("""
            SELECT * FROM episodes 
            WHERE archived = 0 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [self._row_to_episode(r) for r in rows]
    
    def search_by_importance(self, min_score: float = 0.7, limit: int = 10) -> list[Episode]:
        """按重要性检索"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT * FROM episodes 
            WHERE importance_score >= ? AND archived = 0
            ORDER BY importance_score DESC 
            LIMIT ?
        """, (min_score, limit)).fetchall()
        conn.close()
        return [self._row_to_episode(r) for r in rows]
    
    def archive(self, episode_id: str):
        """归档（软删除）— 遗忘但不销毁"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE episodes SET archived = 1 WHERE id = ?",
            (episode_id,)
        )
        conn.commit()
        conn.close()
    
    def count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE archived = 0"
        ).fetchone()[0]
        conn.close()
        return count
    
    def _row_to_episode(self, row) -> Episode:
        return Episode(
            id=row[0],
            timestamp=row[1],
            summary=row[2],
            emotional_valence=row[3],
            emotional_arousal=row[4],
            importance_score=row[5],
            participants=json.loads(row[6]),
            context=json.loads(row[7]),
            key_quotes=json.loads(row[8]),
            tags=json.loads(row[9]),
            linked_episodes=json.loads(row[10]),
            access_count=row[11]
        )
