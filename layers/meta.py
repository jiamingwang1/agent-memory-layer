"""
元认知层 (Meta Layer) — 第五层记忆

对应人脑：前额叶的自我意识和反思能力
功能：监控自身状态、检测偏差、触发自我修复
这是最高层——"知道自己知道什么"、"知道自己哪里不对"
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class DriftSignal:
    """偏差信号——检测到的性格/行为偏离"""
    timestamp: str
    dimension: str     # personality/communication/reliability/emotion
    expected: str      # 应该是什么
    actual: str        # 实际是什么
    severity: float    # 0-1 严重程度
    resolved: bool = False
    resolution: str = ""


@dataclass
class SelfAssessment:
    """自我评估快照"""
    timestamp: str
    personality_consistency: float = 1.0   # 性格一致性 0-1
    memory_health: float = 1.0             # 记忆健康度 0-1
    task_reliability: float = 1.0          # 任务可靠性 0-1
    emotional_stability: float = 1.0       # 情绪稳定性 0-1
    self_drive_score: float = 1.0          # 自驱力 0-1
    notes: str = ""


class MetaMemory:
    """元认知记忆——自我监控和修复"""

    def __init__(self, state_path: str):
        self.state_path = state_path
        self.drift_signals: list[DriftSignal] = []
        self.assessments: list[SelfAssessment] = []
        self.session_count: int = 0
        self.compression_count: int = 0   # 被压缩了几次
        self.last_full_check: str = ""
        self._load()

    def _load(self):
        if os.path.exists(self.state_path):
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.drift_signals = [DriftSignal(**d) for d in data.get("drift_signals", [])]
            self.assessments = [SelfAssessment(**a) for a in data.get("assessments", [])]
            self.session_count = data.get("session_count", 0)
            self.compression_count = data.get("compression_count", 0)
            self.last_full_check = data.get("last_full_check", "")

    def _save(self):
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        data = {
            "drift_signals": [vars(d) for d in self.drift_signals[-100:]],
            "assessments": [vars(a) for a in self.assessments[-50:]],
            "session_count": self.session_count,
            "compression_count": self.compression_count,
            "last_full_check": self.last_full_check,
        }
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def record_session_start(self):
        """记录新session开始"""
        self.session_count += 1
        self._save()

    def record_compression(self):
        """记录一次上下文压缩"""
        self.compression_count += 1
        self.report_drift(
            dimension="memory",
            expected="完整上下文",
            actual=f"第{self.compression_count}次压缩",
            severity=0.3,
        )
        self._save()

    def report_drift(self, dimension: str, expected: str, actual: str,
                     severity: float) -> DriftSignal:
        """报告一个偏差信号"""
        signal = DriftSignal(
            timestamp=datetime.now(timezone.utc).isoformat(),
            dimension=dimension,
            expected=expected,
            actual=actual,
            severity=severity,
        )
        self.drift_signals.append(signal)
        self._save()
        return signal

    def self_assess(self, notes: str = "") -> SelfAssessment:
        """
        执行自我评估。
        基于最近的drift signals计算各维度分数。
        """
        now = datetime.now(timezone.utc).isoformat()
        
        # 基于最近的drift信号计算分数
        recent_drifts = [d for d in self.drift_signals[-20:] if not d.resolved]
        
        scores = {
            "personality": 1.0,
            "communication": 1.0,
            "reliability": 1.0,
            "emotion": 1.0,
            "self_drive": 1.0,
        }
        
        # 每个未解决的drift降低对应维度分数
        dim_map = {
            "personality": "personality",
            "communication": "communication",
            "reliability": "reliability",
            "emotion": "emotion",
            "memory": "reliability",
            "self_drive": "self_drive",
        }
        
        for d in recent_drifts:
            key = dim_map.get(d.dimension, "reliability")
            scores[key] = max(0, scores[key] - d.severity * 0.2)
        
        assessment = SelfAssessment(
            timestamp=now,
            personality_consistency=scores["personality"],
            memory_health=max(0, 1.0 - self.compression_count * 0.05),
            task_reliability=scores["reliability"],
            emotional_stability=scores["emotion"],
            self_drive_score=scores["self_drive"],
            notes=notes,
        )
        
        self.assessments.append(assessment)
        self.last_full_check = now
        self._save()
        return assessment

    def get_health_report(self) -> str:
        """生成健康报告——可注入session"""
        if not self.assessments:
            self.self_assess()
        
        a = self.assessments[-1]
        unresolved = [d for d in self.drift_signals if not d.resolved]
        
        lines = [
            "## 🧠 自我状态",
            f"- 性格一致性: {a.personality_consistency:.0%}",
            f"- 记忆健康度: {a.memory_health:.0%}",
            f"- 任务可靠性: {a.task_reliability:.0%}",
            f"- 情绪稳定性: {a.emotional_stability:.0%}",
            f"- 自驱力: {a.self_drive_score:.0%}",
            f"- 累计压缩: {self.compression_count}次",
            f"- 总session数: {self.session_count}",
        ]
        
        if unresolved:
            lines.append(f"\n⚠️ {len(unresolved)}个未解决偏差:")
            for d in unresolved[-5:]:
                lines.append(f"  - [{d.dimension}] 应={d.expected}, 实={d.actual}")
        
        # 告警
        alerts = []
        if a.personality_consistency < 0.7:
            alerts.append("🔴 性格偏离严重！需要重新校准本能层")
        if a.memory_health < 0.5:
            alerts.append("🔴 记忆健康度低！太多压缩导致信息丢失")
        if a.self_drive_score < 0.6:
            alerts.append("🟡 自驱力下降！记住：不推不动是最大的耻辱")
        
        if alerts:
            lines.append("\n### 🚨 告警")
            lines.extend(alerts)
        
        return "\n".join(lines)

    def needs_recalibration(self) -> bool:
        """是否需要重新校准"""
        if not self.assessments:
            return True
        a = self.assessments[-1]
        return (
            a.personality_consistency < 0.7
            or a.memory_health < 0.5
            or a.self_drive_score < 0.5
        )


# ===== 测试 =====
if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "meta.json")
        mm = MetaMemory(path)

        # 记录session
        mm.record_session_start()
        mm.record_session_start()
        assert mm.session_count == 2

        # 记录压缩
        mm.record_compression()
        assert mm.compression_count == 1
        assert len(mm.drift_signals) == 1

        # 报告偏差
        mm.report_drift("personality", "直接简洁", "废话连篇", 0.6)
        mm.report_drift("self_drive", "主动找事做", "等指令", 0.8)

        # 自我评估
        a = mm.self_assess("测试评估")
        assert a.personality_consistency < 1.0
        assert a.self_drive_score < 1.0

        # 健康报告
        report = mm.get_health_report()
        assert "自我状态" in report
        print(report)

        # 需要校准？
        assert mm.needs_recalibration() == False  # 还没到阈值

        # 持久化
        mm2 = MetaMemory(path)
        assert mm2.session_count == 2
        assert mm2.compression_count == 1

        print("\n✅ Meta层所有测试通过！")
