"""
统一记忆系统 (Unified Memory System)

把五层记忆 + 回忆引擎 + 固化引擎串成一个入口。
对外只暴露几个简单接口：

1. on_session_start(context) → 注入记忆
2. on_message(msg) → 实时更新（轻量）
3. on_session_end(transcript) → 固化记忆
4. health_check() → 自我诊断
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional

from layers import (
    InstinctMemory,
    KnowledgeMemory, Fact,
    EpisodicMemory, Episode,
    RelationalMemory,
    MetaMemory,
)
from recall import ContextualRecall
from sleep import SleepConsolidation


class MemorySystem:
    """五层记忆的统一入口"""

    def __init__(self, data_dir: str, embedding_config: dict = None):
        """
        data_dir: 记忆数据存放目录
        embedding_config: {"api_base": "...", "api_key": "...", "model": "..."}
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        # 初始化五层
        self.instinct = InstinctMemory(
            os.path.join(data_dir, "instinct.json")
        )
        self.knowledge = KnowledgeMemory(
            os.path.join(data_dir, "knowledge.db")
        )
        self.episodic = EpisodicMemory(
            os.path.join(data_dir, "episodic.db")
        )
        self.relational = RelationalMemory(
            os.path.join(data_dir, "relational.db")
        )
        self.meta = MetaMemory(
            os.path.join(data_dir, "meta.json")
        )

        # 回忆引擎
        emb = embedding_config or {}
        self.recall = ContextualRecall(
            episodic=self.episodic,
            relational=self.relational,
            embedding_api_base=emb.get("api_base"),
            embedding_api_key=emb.get("api_key"),
            embedding_model=emb.get("model", "text-embedding-3-small"),
        )

    # ========== 对外接口 ==========

    def on_session_start(self, opening_message: str = "",
                         person_id: str = None) -> str:
        """
        新session开始时调用。
        返回要注入到session开头的记忆文本。
        
        注入顺序（从底层到高层）：
        1. 本能层 → 身份提示
        2. 元认知层 → 健康状态（如果有告警）
        3. 关系层 → 对话者的沟通风格提示
        4. 回忆引擎 → 相关情景记忆
        """
        self.meta.record_session_start()

        sections = []

        # 1. 本能层（始终注入）
        sections.append(self.instinct.get_identity_prompt())

        # 2. 元认知告警（只在有问题时注入）
        if self.meta.needs_recalibration():
            sections.append(self.meta.get_health_report())

        # 3. 关系层（如果知道对话者）
        if person_id:
            style_prompt = self.relational.get_style_prompt(person_id)
            if style_prompt:
                sections.append(style_prompt)

        # 4. 回忆引擎（如果有opening message）
        if opening_message:
            recalled = self.recall.smart_recall(
                opening_message,
                person_id=person_id,
                inject_limit=1500,
            )
            if recalled:
                sections.append(recalled)

        # 5. 相关知识（如果知道对话者）
        if person_id:
            knowledge_text = self.knowledge.format_knowledge(
                person_id, max_chars=800
            )
            if knowledge_text:
                sections.append(knowledge_text)

        return "\n\n---\n\n".join(sections)

    def on_message(self, message: str, role: str = "user",
                   person_id: str = None):
        """
        收到消息时的轻量更新。
        不做重计算，只更新关系温度等即时指标。
        """
        if role == "user" and person_id:
            # 简单情感判断（后续可接LLM）
            quality = 0.6  # 默认中等质量交互
            if any(w in message for w in ["谢谢", "好的", "👍", "❤️", "不错"]):
                quality = 0.8
            elif any(w in message for w in ["不要", "别", "停", "烦", "差"]):
                quality = 0.3
            self.relational.record_interaction(person_id, quality=quality)

    def on_session_end(self, transcript: str, person_id: str = None):
        """
        session结束时调用（或上下文压缩前调用）。
        触发固化引擎，把对话提炼成长期记忆。
        
        注意：这个方法需要LLM调用，是异步/后台执行的。
        在没有consolidation engine的LLM配置时，只做简单记录。
        """
        # 记录一个基础episode
        ep = Episode(
            id=f"ep_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            summary=f"对话session（{len(transcript)}字符）",
            emotional_valence=0.0,
            emotional_arousal=0.3,
            importance_score=0.5,
            participants=[person_id] if person_id else [],
            tags=["auto_captured"],
        )
        self.episodic.store(ep)

    def on_compression(self):
        """上下文被压缩时调用"""
        self.meta.record_compression()

    def health_check(self) -> str:
        """返回系统健康报告"""
        assessment = self.meta.self_assess()
        report = self.meta.get_health_report()

        # 加上各层统计
        stats = [
            report,
            "",
            "### 📊 各层统计",
            f"- 本能层: v{self.instinct.profile.version}",
            f"- 知识层: {self.knowledge.count()}条事实",
            f"- 情景层: {self.episodic.count()}条记忆",
            f"- 关系层: 已加载",
            f"- 元认知: {len(self.meta.drift_signals)}条偏差信号",
        ]

        return "\n".join(stats)

    def sleep(self, person_id: str = "default", 
              api_base: str = None, api_key: str = None) -> dict:
        """执行睡眠整理（遗忘+强化+模式发现+关系衰减）"""
        engine = SleepConsolidation(
            episodic_db=os.path.join(self.data_dir, "episodic.db"),
            relational_db=os.path.join(self.data_dir, "relational.db"),
            api_base=api_base,
            api_key=api_key,
        )
        return engine.run(person_id)

    def learn_fact(self, fact_id: str, category: str, subject: str,
                   predicate: str, value: str, confidence: float = 0.8,
                   source: str = ""):
        """快捷方法：学习一条新知识"""
        self.knowledge.store(Fact(
            id=fact_id,
            category=category,
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=confidence,
            source=source,
        ))

    def remember(self, summary: str, valence: float = 0.0,
                 arousal: float = 0.5, importance: float = 0.5,
                 participants: list = None, tags: list = None):
        """快捷方法：手动记住一件事"""
        import uuid
        ep = Episode(
            id=f"ep_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            summary=summary,
            emotional_valence=valence,
            emotional_arousal=arousal,
            importance_score=importance,
            participants=participants or [],
            tags=tags or [],
        )
        self.episodic.store(ep)


# ===== 测试 =====
if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # 初始化
        ms = MemorySystem(tmpdir)
        print("✅ MemorySystem初始化成功")

        # 学习知识
        ms.learn_fact("f1", "person", "aa", "交易所", "Gate.io", 1.0, "对话")
        ms.learn_fact("f2", "person", "aa", "年龄", "17岁", 1.0, "USER.md")
        print(f"✅ 知识层: {ms.knowledge.count()}条")

        # 记住事情
        ms.remember(
            "aa确认Agent记忆层是Web4.0核心方向",
            valence=0.9, arousal=0.85, importance=0.95,
            participants=["aa"], tags=["web4", "决策"],
        )
        ms.remember(
            "VPS1和VPS2已欠费关停",
            valence=-0.3, arousal=0.4, importance=0.6,
            tags=["infra"],
        )
        print(f"✅ 情景层: {ms.episodic.count()}条")

        # 关系互动
        ms.on_message("谢谢小助，做得不错", role="user", person_id="aa")
        print("✅ 关系温度更新")

        # 新session注入
        injection = ms.on_session_start(
            opening_message="继续推进记忆层",
            person_id="aa",
        )
        assert "小助" in injection
        print(f"\n=== Session注入文本 ({len(injection)}字符) ===")
        print(injection[:500] + "..." if len(injection) > 500 else injection)

        # 健康检查
        report = ms.health_check()
        assert "自我状态" in report
        print(f"\n=== 健康报告 ===")
        print(report)

        # 压缩事件
        ms.on_compression()
        assert ms.meta.compression_count == 1

        print("\n✅ MemorySystem全部测试通过！")
