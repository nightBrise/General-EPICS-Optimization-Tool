import numpy as np
from .base import Scorer, _effective_deviation
from .registry import register_scorer


@register_scorer("l2")
class L2Scorer(Scorer):
    """L2 评分: sqrt(Σ(wi * (ri - ti)^2) / Σ wi)"""

    def __call__(self, readings, targets, weights, ranges=None):
        if not readings:
            return float('inf')
        total = 0.0
        w_sum = 0.0
        for i, (r, t, w) in enumerate(zip(readings, targets, weights)):
            dev = _effective_deviation(r, t, ranges[i] if ranges else None)
            total += w * dev ** 2
            w_sum += w
        if w_sum == 0:
            return float('inf')
        return np.sqrt(total / w_sum)
