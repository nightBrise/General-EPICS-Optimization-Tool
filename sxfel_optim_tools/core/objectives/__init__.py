"""目标函数模块

提供束流优化、轨道优化目标函数。
"""
from .base import BaseObjective
from .registry import register_objective, create_objective, get_registered_objectives
from .metrics import metrics, MetricsTracker

# 导入并注册目标函数
from .beam import BeamObjective, optimize_beam, save_optimization_results
from .orbit_zero import OrbitObjective, OrbitZeroObjective

# 导出公共接口
__all__ = [
    'BaseObjective',
    'BeamObjective',
    'OrbitObjective',
    'OrbitZeroObjective',
    'optimize_beam',
    'save_optimization_results',
    'create_objective',
    'get_registered_objectives',
    'metrics',
    'MetricsTracker',
]
