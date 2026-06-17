"""变换基类"""
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class Transform(ABC):
    """数据预处理变换基类

    所有变换必须继承此类并实现 __call__ 方法。
    """

    def __init__(self, params: dict = None):
        self.params = params or {}

    @abstractmethod
    def __call__(self, raw_value: Any, *,
                 pv_name: str = "",
                 caget_fn: Optional[Callable] = None) -> float:
        """对原始读数做预处理，输出一个数值

        Args:
            raw_value: caget 的原始返回值
            pv_name: PV 名称（需要重复读取时用）
            caget_fn: 可选的 caget 回调（average 等需要重复读数时用）

        Returns:
            float: 处理后的数值，传给评分函数
        """
