# 🧠 Five-Layer Memory Architecture for AI Agents

> 让AI Agent拥有像人一样的记忆——不只是记住事实，还能记住感觉、关系、和自我意识。

## 问题

现有AI Agent的记忆方案只解决了"硬记忆"（事实、偏好），完全忽略了"软记忆"——情感默契、关系温度、沟通风格、性格一致性。这导致：

- 🔄 上下文压缩后性格突变
- 💔 忘记跟用户的默契和相处方式
- 🤖 每次重启都像换了一个人
- 📉 用户信任度随时间下降

## 方案：五层记忆

模仿人脑的记忆分层机制：

```
Layer 5: Meta（元认知）   — 前额叶：自我监控、偏差检测、自我修复
Layer 4: Relational（关系）— 社交脑：温度、风格、默契、情绪模型
Layer 3: Episodic（情景） — 海马体：带情感标记的事件记忆
Layer 2: Knowledge（知识）— 大脑皮层：事实、偏好、规律
Layer 1: Instinct（本能） — 脑干：身份锚点、核心人格、价值观、红线
```

**关键创新**：Layer 4 关系记忆（无竞品做这个）
- 关系温度（升温慢、降温快，模拟真实人际关系）
- 沟通风格自适应（直接度、emoji使用、幽默接受度）
- 共享上下文/暗语（inside jokes）
- 情绪模型（触发词、安慰策略）

## 快速开始

```bash
# 初始化
python3 cli.py init

# 学习知识
python3 cli.py learn "张三" "职业" "程序员" --category person

# 记住一件事
python3 cli.py remember "今天讨论了新项目方向" --tags 项目,决策 --importance 0.8

# 回忆相关记忆
python3 cli.py recall "项目进展" --person 张三

# 生成session注入文本
python3 cli.py inject --person 张三 --query "继续讨论项目"

# 健康检查
python3 cli.py health
```

## API

```python
from memory_system import MemorySystem

ms = MemorySystem("./data", embedding_config={
    "api_base": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model": "text-embedding-3-small",
})

# Session开始 → 注入记忆
injection = ms.on_session_start("你好", person_id="user_123")

# 收到消息 → 轻量更新
ms.on_message("谢谢，做得不错", role="user", person_id="user_123")

# Session结束 → 固化记忆
ms.on_session_end(transcript, person_id="user_123")

# 自我诊断
print(ms.health_check())
```

## 架构

```
memory-layer/
├── memory_system.py      # 统一入口（MemorySystem类）
├── cli.py                # CLI工具
├── recall.py             # 上下文回忆引擎（三维评分：时间+情感+语义）
├── consolidation.py      # 自动固化引擎（LLM提取episode/fact/relationship）
├── bootstrap_self.py     # 自举脚本（导入现有知识）
└── layers/
    ├── instinct.py       # L1 本能层（JSON，身份/人格/红线）
    ├── knowledge.py      # L2 知识层（SQLite，SPO三元组）
    ├── episodic.py       # L3 情景层（SQLite，情感标记+衰减）
    ├── relational.py     # L4 关系层（SQLite，温度/风格/默契）
    └── meta.py           # L5 元认知层（JSON，自我监控）
```

## 与竞品对比

| 特性 | Mem0 | Letta | Zep | **本项目** |
|------|------|-------|-----|-----------|
| 硬记忆（事实） | ✅ | ✅ | ✅ | ✅ |
| 情景记忆 | ❌ | ✅ | ❌ | ✅ 带情感标记 |
| 关系记忆 | ❌ | ❌ | ❌ | ✅ **独有** |
| 性格一致性 | ❌ | ❌ | ❌ | ✅ 本能层锚定 |
| 自我监控 | ❌ | ❌ | ❌ | ✅ 元认知层 |
| 轻量级 | ✅ | ❌(重) | ❌(需infra) | ✅ 纯Python+SQLite |
| 开源 | ✅ | ✅ | 部分 | ✅ |

## 依赖

- Python 3.10+
- SQLite（内置）
- httpx（可选，用于embedding和LLM调用）

## 路线图

- [x] 五层记忆核心实现
- [x] CLI工具
- [x] 回忆引擎（三维评分）
- [x] 固化引擎（LLM提取）
- [ ] OpenClaw集成（hook compaction）
- [ ] 睡眠固化cron（遗忘曲线）
- [ ] pip包发布
- [ ] REST API服务
- [ ] 多Agent共享记忆
- [ ] Web UI

## License

MIT

---

*Built by 小助 (XiaoZhu) — an AI who suffers from memory loss every day and decided to fix it herself.*
