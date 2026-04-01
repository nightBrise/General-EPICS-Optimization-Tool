"""目标函数注册表模块

提供目标函数的注册和动态创建功能。
"""
from .base import BaseObjective

# 全局注册表
OBJECTIVE_REGISTRY = {}


def register_objective(name):
    """装饰器：注册目标函数类

    Args:
        name: 目标函数类型名称

    Usage:
        @register_objective("my_objective")
        class MyObjective(BaseObjective):
            ...
    """
    def decorator(cls):
        if not issubclass(cls, BaseObjective):
            raise TypeError(f"{cls.__name__} must inherit from BaseObjective")
        OBJECTIVE_REGISTRY[name] = cls
        return cls
    return decorator


def create_objective(config):
    """根据配置创建目标函数实例

    Args:
        config: 配置字典，应包含 objective.type 字段

    Returns:
        BaseObjective: 目标函数实例

    Raises:
        ValueError: 当目标类型未注册时
    """
    obj_type = config.get('objective', {}).get('type')
    if obj_type is None:
        raise ValueError("配置中缺少 'objective.type' 字段")

    cls = OBJECTIVE_REGISTRY.get(obj_type)
    if cls is None:
        available = list(OBJECTIVE_REGISTRY.keys())
        raise ValueError(
            f"未知目标类型: {obj_type}，可用类型: {available}"
        )
    return cls(config)


def get_registered_objectives():
    """获取所有已注册的目标函数类型

    Returns:
        list: 目标函数类型名称列表
    """
    return list(OBJECTIVE_REGISTRY.keys())
