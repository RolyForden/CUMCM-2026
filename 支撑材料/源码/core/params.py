"""C 题统一物理参数。

参数对象只保存题意口径；优化器、执行器和核算器各自实现状态方程，
避免通过复用同一计算函数造成“共同写错仍能对拍”。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatteryParams:
    eta_charge: float = 0.9
    eta_discharge: float = 0.9
    soc_min: float = 1200.0
    soc_max: float = 10800.0
    power_max: float = 5000.0
    delta_t: float = 1.0 / 6.0

    def __post_init__(self) -> None:
        if not (0.0 < self.eta_charge <= 1.0):
            raise ValueError("eta_charge 必须在 (0, 1] 内")
        if not (0.0 < self.eta_discharge <= 1.0):
            raise ValueError("eta_discharge 必须在 (0, 1] 内")
        if self.soc_min < 0 or self.soc_max <= self.soc_min:
            raise ValueError("SOC 上下界无效")
        if self.power_max <= 0 or self.delta_t <= 0:
            raise ValueError("功率上限和时段长度必须为正")

    @property
    def energy_limit(self) -> float:
        return self.power_max * self.delta_t


DEFAULT_BATTERY = BatteryParams()
