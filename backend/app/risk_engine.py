from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


DEFAULT_WEIGHTS: dict[str, float] = {
    "severity": 0.25,
    "transmission": 0.25,
    "scale": 0.15,
    "travel": 0.15,
    "transit": 0.10,
    "capacity": 0.10,
}


def risk_level(score: float) -> str:
    if score >= 80:
        return "red"
    if score >= 60:
        return "orange"
    if score >= 40:
        return "yellow"
    return "blue"


def risk_level_cn(score: float) -> str:
    return {"red": "红色", "orange": "橙色", "yellow": "黄色", "blue": "蓝色"}[risk_level(score)]


def calculate_risk(
    factors: Mapping[str, float], weights: Mapping[str, float] | None = None
) -> tuple[float, str]:
    selected = dict(weights or DEFAULT_WEIGHTS)
    if not selected or abs(sum(selected.values()) - 1.0) > 1e-6:
        raise ValueError("风险因子权重之和必须为 1")

    score = 0.0
    for key, weight in selected.items():
        value = float(factors.get(key, 0))
        if not 0 <= value <= 100:
            raise ValueError(f"风险因子 {key} 必须在 0—100 之间")
        # capacity represents response capability, so a higher capability lowers risk.
        effective = 100 - value if key == "capacity" else value
        score += effective * weight
    rounded = round(max(0.0, min(100.0, score)), 1)
    return rounded, risk_level(rounded)


@dataclass(frozen=True)
class PassengerRiskResult:
    score: float
    level: str
    reasons: tuple[str, ...]
    advice: tuple[str, ...]


def calculate_passenger_risk(
    country_scores: list[tuple[str, float]],
    has_health_declaration: bool,
    transit_count: int = 0,
) -> PassengerRiskResult:
    highest_country = max(country_scores, key=lambda item: item[1], default=("无风险旅居地", 0.0))
    score = highest_country[1]
    reasons = [f"14天内旅居地最高风险：{highest_country[0]} {highest_country[1]:.0f}分"]

    if not has_health_declaration:
        score += 12
        reasons.append("未完成健康申报，风险上调12分")
    if transit_count:
        transit_bonus = min(10, transit_count * 3)
        score += transit_bonus
        reasons.append(f"存在{transit_count}个中转国家，风险上调{transit_bonus}分")

    score = round(min(100.0, score), 1)
    level = risk_level(score)
    advice_map = {
        "red": ("引导至专用检疫通道", "开展流行病学调查", "按病种要求采样检测", "通知属地联防联控"),
        "orange": ("加强健康申报核验", "实施体温复测", "按比例开展核酸抽检"),
        "yellow": ("核验健康申报", "常规体温监测", "发放健康提示"),
        "blue": ("常态卫生检疫",),
    }
    return PassengerRiskResult(score, level, tuple(reasons), advice_map[level])
