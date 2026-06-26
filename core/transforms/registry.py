"""变换注册表"""
from __future__ import annotations
from .base import Transform

TRANSFORM_REGISTRY = {}


def register_transform(name: str):
    """注册变换

    Args:
        name: 变换名称

    Usage:
        @register_transform("my_transform")
        class MyTransform(Transform):
            ...
    """
    def decorator(cls):
        if not issubclass(cls, Transform):
            raise TypeError(f"{cls.__name__} must inherit from Transform")
        TRANSFORM_REGISTRY[name] = cls
        return cls
    return decorator


def create_transform(transform_config: dict = None) -> Transform | list[Transform] | None:
    """根据配置创建变换实例

    Args:
        transform_config: {'type': '...', 'params': {...}} 或 [{'type':...}, ...] 或 None

    Returns:
        单个 Transform、Transform 链（列表）、或 None
    """
    if transform_config is None:
        return None
    if isinstance(transform_config, list):
        result = [_create_single(tc) for tc in transform_config]
        result = [t for t in result if t is not None]
        return result if result else None
    return _create_single(transform_config)


def _create_single(transform_config: dict) -> Transform | None:
    ttype = transform_config.get('type', '')
    if not ttype or ttype == 'none':
        return None
    params = transform_config.get('params', {})
    if ttype.startswith("custom:"):
        name = ttype[7:]
        cls = TRANSFORM_REGISTRY.get(name)
        if cls is None:
            raise ValueError(
                f"未注册的自定义变换: {name}，可用: {list(TRANSFORM_REGISTRY.keys())}")
    else:
        cls = TRANSFORM_REGISTRY.get(ttype)
        if cls is None:
            raise ValueError(
                f"未知变换类型: {ttype}，可用: {list(TRANSFORM_REGISTRY.keys())}")
    return cls(params)


def get_registered_transforms() -> list[str]:
    return list(TRANSFORM_REGISTRY.keys())
