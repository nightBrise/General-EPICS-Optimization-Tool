from typing import Dict, Type

_registry = {}  # type: Dict[str, Type]


def register_algorithm(*names):
    """注册算法。可注册多个别名。"""
    def decorator(cls):
        for n in names:
            _registry[n] = cls
        return cls
    return decorator


def get_algorithm(name):
    # type: (str) -> Type
    """按名称查找算法，未找到返回 None。"""
    return _registry.get(name)


def list_algorithms():
    # type: () -> list
    return list(_registry.keys())
