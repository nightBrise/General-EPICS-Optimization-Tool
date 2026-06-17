"""内置通用变换"""
import numpy as np
from .base import Transform
from .registry import register_transform


@register_transform("reshape")
class ReshapeTransform(Transform):
    """1D 数组 → ND 数组

    params:
        shape: 目标形状 [dim0, dim1, ...]
        order: "C" (C order) 或 "F" (Fortran order)，默认 "C"
    """

    def __call__(self, raw_value, *, pv_name="", caget_fn=None):
        shape = self.params.get('shape', [])
        order = self.params.get('order', 'C')
        arr = np.asarray(raw_value)
        if not shape:
            return float(np.mean(arr))
        if len(arr) == np.prod(shape):
            arr = arr.reshape(shape, order=order)
        return float(np.mean(arr))


@register_transform("average")
class AverageTransform(Transform):
    """连续读取 N 次取平均（支持标量和数组）

    params:
        n: 读取次数，默认 3
        wait: 每次间隔秒数，默认 0.5
    """

    def __call__(self, raw_value, *, pv_name="", caget_fn=None):
        import time
        n = self.params.get('n', 3)
        wait = self.params.get('wait', 0.5)
        is_iter = hasattr(raw_value, '__iter__') and not isinstance(raw_value, (str, bytes))
        total = np.asarray(raw_value, dtype=np.float64)
        for _ in range(n - 1):
            time.sleep(wait)
            if caget_fn:
                val = caget_fn(pv_name)
                if val is not None:
                    total = total + np.asarray(val, dtype=np.float64)
        avg = total / n
        return avg.tolist() if is_iter else float(avg)


@register_transform("combine")
class CombineTransform(Transform):
    """合并多个读数

    params:
        method: "rms" (默认) | "max" | "sum"
        用于 X+Y 两个方向合成，或其他多维数据合并
    """

    def __call__(self, raw_value, *, pv_name="", caget_fn=None):
        method = self.params.get('method', 'rms')
        arr = np.atleast_1d(np.asarray(raw_value))
        if method == 'rms':
            return float(np.sqrt(np.mean(arr.astype(float) ** 2)))
        elif method == 'max':
            return float(np.max(arr))
        elif method == 'sum':
            return float(np.sum(arr))
        return float(np.mean(arr))
