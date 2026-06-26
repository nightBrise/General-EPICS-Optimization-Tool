"""评分器基类"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional as _Optional


def _effective_deviation(reading: float, target: float, pv_range: _Optional[list[float]]) -> float:
    """计算有效偏差

    Args:
        reading: PV 读数
        target: 目标值
        pv_range: 可接受范围 [min, max]，None 表示无限制

    Returns:
        float: 偏差值。读数在 pv_range 内返回 0
    """
    if pv_range is None:
        return reading - target
    lo, hi = pv_range
    if lo <= reading <= hi:
        return 0.0
    if reading < lo:
        return reading - lo
    return reading - hi


class Scorer(ABC):
    """评分器基类。

    所有评分策略必须继承此类并实现 __call__ 方法。
    """

    def __init__(self, params: dict = None):
        self.params = params or {}

    @abstractmethod
    def __call__(self, readings: list[float], targets: list[float],
                 weights: list[float], ranges: _Optional[list[_Optional[list[float]]]] = None) -> float:
        """计算评分（越小越好）

        Args:
            readings: 组内目标 PV 的读数列表
            targets: 目标值列表
            weights: 权重列表
            ranges: 可接受区间列表，None 表示无区间限制
        """
