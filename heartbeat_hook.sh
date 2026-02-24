#!/bin/bash
# 心跳钩子 — 每次心跳自动调用
# 1. 快速健康检查（静默，只在有告警时输出）
# 2. 记录心跳事件到情景记忆
# 用法: bash projects/memory-layer/heartbeat_hook.sh ["工作描述"]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK_DESC="${1:-routine heartbeat}"

# 健康检查（只输出告警行）
HEALTH=$(python3 "$SCRIPT_DIR/openclaw_hook.py" health 2>/dev/null | grep -E "🔴|🚨|⚠️")
if [ -n "$HEALTH" ]; then
    echo "$HEALTH"
fi

# 记录心跳到情景记忆
python3 "$SCRIPT_DIR/openclaw_hook.py" record \
    --text "心跳: $WORK_DESC" \
    --emotion focused \
    --importance 0.3 2>/dev/null

# 输出当前记忆统计（一行）
EPISODES=$(python3 "$SCRIPT_DIR/cli.py" health 2>/dev/null | grep "情景层" | sed 's/.*: //')
FACTS=$(python3 "$SCRIPT_DIR/cli.py" health 2>/dev/null | grep "知识层" | sed 's/.*: //')
echo "📊 记忆: $FACTS | $EPISODES"
