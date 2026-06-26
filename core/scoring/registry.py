"""评分器注册表"""
from __future__ import annotations
from .base import Scorer

SCORER_REGISTRY = {}


def register_scorer(name: str):
    """注册评分器

    Args:
        name: 评分器名称（用于配置中引用）

    Usage:
        @register_scorer("my_scorer")
        class MyScorer(Scorer):
            ...
    """
    def decorator(cls):
        if not issubclass(cls, Scorer):
            raise TypeError(f"{cls.__name__} must inherit from Scorer")
        SCORER_REGISTRY[name] = cls
        return cls
    return decorator


def create_scorer(method: str, params: dict = None) -> Scorer:
    """根据方法名创建评分器

    Args:
        method: "l2", "l1", "max", "weighted_sum", 或 "custom:<name>"
        params: 评分器参数

    Returns:
        Scorer: 评分器实例
    """
    if method.startswith("custom:"):
        name = method[7:]
        cls = SCORER_REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"未注册的自定义评分器: {name}，可用: {list(SCORER_REGISTRY.keys())}")
    else:
        cls = SCORER_REGISTRY.get(method)
        if cls is None:
            raise ValueError(f"未知评分方法: {method}，可用: {list(SCORER_REGISTRY.keys())}")
    return cls(params)


def get_registered_scorers() -> list[str]:
    return list(SCORER_REGISTRY.keys())
