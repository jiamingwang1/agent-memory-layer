"""
OpenClaw 集成桥接 (Bridge)

不改OpenClaw核心代码，通过以下方式集成：

1. pre-compaction hook: 在memory flush时自动固化当前对话
2. session start hook: 在新session开始时自动注入记忆上下文
3. cron sleep: 每天凌晨运行睡眠整理

集成方式：作为独立脚本被OpenClaw的cron/heartbeat调用
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 添加项目路径
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from layers.episodic import EpisodicMemory
from layers.relational import RelationalMemory
from layers.semantic import SemanticMemory
from layers.meta import MetaMemory
from consolidation import ConsolidationEngine
from recall import ContextualRecall
from sleep import SleepConsolidation


# 默认配置
DEFAULT_DB = os.path.expanduser("~/.openclaw/workspace/memory-layer.db")
DEFAULT_API_BASE = "https://ai.t8star.cn/v1"
DEFAULT_MODEL = "gpt-4o-mini"


class OpenClawBridge:
    """OpenClaw ↔ Memory Layer 桥接"""
    
    def __init__(self, db_path: str = None, api_key: str = None):
        self.db_path = db_path or DEFAULT_DB
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        
        # 初始化各层
        self.episodic = EpisodicMemory(self.db_path)
        self.relational = RelationalMemory(self.db_path)
        self.semantic = SemanticMemory(self.db_path)
        self.meta = MetaMemory(self.db_path)
        self.consolidation = ConsolidationEngine(
            api_key=self.api_key, model=DEFAULT_MODEL
        )
        self.recall = ContextualRecall(self.db_path)
        self.sleep = SleepConsolidation(
            self.db_path, api_key=self.api_key, model=DEFAULT_MODEL
        )
    
    def on_conversation_end(self, conversation: list[dict], 
                            user_id: str = "aa") -> dict:
        """
        对话结束时调用 — 自动固化
        
        可被OpenClaw的pre-compaction memory flush触发
        """
        result = self.consolidation.consolidate(
            conversation, self.episodic, self.relational, user_id
        )
        
        # 同步更新VIBE.md（关系层变化→写入软记忆文件）
        if result.get("relationship_update"):
            self._update_vibe_md(user_id, result["relationship_update"])
        
        return result
    
    def on_session_start(self, user_id: str = "aa", 
                         first_message: str = "") -> str:
        """
        新session开始时调用 — 生成记忆上下文
        
        返回的文本可以追加到system prompt中
        """
        parts = []
        
        # 1. 情景+关系层上下文
        recall_ctx = self.recall.build_context(user_id, first_message, 
                                                token_budget=1500)
        if recall_ctx:
            parts.append(recall_ctx)
        
        # 2. 知识层上下文
        semantic_ctx = self.semantic.format_for_context(
            keyword=first_message[:50] if first_message else ""
        )
        if semantic_ctx:
            parts.append(semantic_ctx)
        
        # 3. 意识层上下文
        meta_ctx = self.meta.format_for_context()
        if meta_ctx:
            parts.append(meta_ctx)
        
        return "\n\n".join(parts)
    
    def run_sleep_cycle(self, user_id: str = "aa") -> dict:
        """
        睡眠整理 — 建议作为cron每天凌晨运行
        """
        result = self.sleep.run(user_id)
        
        # 如果发现了新模式，添加到知识层
        for pattern in result.get("patterns", []):
            self.semantic.add_implicit(
                fact_id=f"pattern-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                fact=pattern["description"],
                evidence=pattern.get("evidence", []),
                confidence=pattern.get("confidence", 0.5)
            )
        
        # 运行知识衰减
        self.semantic.decay_implicit()
        
        return result
    
    def import_from_memory_md(self, memory_md_path: str, user_id: str = "aa"):
        """
        从现有MEMORY.md导入到结构化记忆层
        一次性迁移工具
        """
        if not os.path.exists(memory_md_path):
            return {"error": "MEMORY.md not found"}
        
        with open(memory_md_path, 'r') as f:
            content = f.read()
        
        # 简单解析：按##分段，每段作为一个知识条目
        sections = content.split("\n## ")
        imported = 0
        for section in sections:
            lines = section.strip().split("\n")
            if not lines:
                continue
            title = lines[0].strip("# ").strip()
            body = "\n".join(lines[1:]).strip()
            if title and body:
                self.semantic.add_explicit(
                    key=f"memory:{title[:50]}",
                    value=body[:500],  # 截断太长的
                    source="MEMORY.md导入"
                )
                imported += 1
        
        return {"imported": imported}
    
    def _update_vibe_md(self, user_id: str, update: dict):
        """根据关系层变化更新VIBE.md"""
        vibe_path = os.path.expanduser("~/.openclaw/workspace/VIBE.md")
        if not os.path.exists(vibe_path):
            return
        
        # 只更新情绪状态部分（不覆盖整个文件）
        mood = update.get("mood", "unknown")
        if mood != "unknown":
            try:
                with open(vibe_path, 'r') as f:
                    content = f.read()
                
                # 更新或追加情绪记录
                timestamp = datetime.now().strftime("%m/%d %H:%M")
                mood_line = f"- {timestamp} 情绪: {mood}"
                
                # 找到情绪状态部分追加
                if "## aa最近的情绪状态" in content:
                    # 在该section末尾追加
                    pass  # TODO: 精确追加逻辑
            except Exception:
                pass  # 静默失败，不影响主流程
    
    def get_stats(self) -> dict:
        """获取记忆系统统计"""
        return {
            "episodes": self.episodic.count(),
            "knowledge": self.semantic.count(),
            "meta": self.meta.count(),
            "db_path": self.db_path,
            "db_size_kb": os.path.getsize(self.db_path) / 1024 
                          if os.path.exists(self.db_path) else 0
        }


def main():
    """CLI入口"""
    import argparse
    parser = argparse.ArgumentParser(description="Memory Layer OpenClaw Bridge")
    parser.add_argument("action", choices=[
        "consolidate", "recall", "sleep", "import", "stats"
    ])
    parser.add_argument("--user", default="aa")
    parser.add_argument("--message", default="")
    parser.add_argument("--memory-md", default="")
    parser.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args()
    
    bridge = OpenClawBridge(db_path=args.db)
    
    if args.action == "recall":
        ctx = bridge.on_session_start(args.user, args.message)
        print(ctx)
    elif args.action == "sleep":
        result = bridge.run_sleep_cycle(args.user)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.action == "import":
        path = args.memory_md or os.path.expanduser("~/.openclaw/workspace/MEMORY.md")
        result = bridge.import_from_memory_md(path, args.user)
        print(json.dumps(result, ensure_ascii=False))
    elif args.action == "stats":
        stats = bridge.get_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(f"Unknown action: {args.action}")


if __name__ == "__main__":
    main()

# ⚠️ DEPRECATED: 此文件基于旧架构（单db + SemanticMemory）
# 新架构请使用 memory_system.py（统一入口）+ cli.py（CLI工具）
# 保留此文件仅作参考
