"""变量 PV 管理器"""
from __future__ import annotations
import numpy as np
from .epics_backend import caget_many


class VariableManager:
    """管理优化变量 PV：PV 列表、范围、初始值"""

    def __init__(self, config: dict):
        """从配置初始化

        Args:
            config: 完整配置字典
        """
        raw = config.get('variables', [])
        self.pvs: list[str] = []
        self.ranges: list[list[float]] = []
        self.base_steps: list[float] = []
        self.initial_values: list[float] = []

        for v in raw:
            self.pvs.append(v['pv'])
            self.ranges.append(v['range'])
            self.base_steps.append(v.get('base_step', 0.01))

    def read_initial_values(self) -> list[float]:
        """从 EPICS 读取所有变量 PV 的当前值，保存为初始值

        Returns:
            list[float]: 当前值列表
        """
        values = caget_many(self.pvs)
        clamped = []
        for i, (v, r) in enumerate(zip(values, self.ranges)):
            if v is None:
                v = sum(r) / 2
                print(f"  警告: 无法读取 {self.pvs[i]}，使用范围中点 {v}")
            v = np.clip(v, r[0], r[1])
            clamped.append(float(v))
        self.initial_values = list(clamped)
        return clamped

    def clamp_params(self, params: list[float]) -> list[float]:
        """将参数限制在范围内"""
        return [np.clip(p, r[0], r[1]) for p, r in zip(params, self.ranges)]

    def __len__(self):
        return len(self.pvs)

    def __repr__(self):
        return f"VariableManager({len(self)} PVs)"
