from .base import Scorer, _effective_deviation
from .registry import register_scorer


@register_scorer("max")
class MaxScorer(Scorer):
    """Max 评分: max(wi * |ri - ti|)"""

    def __call__(self, readings, targets, weights, ranges=None):
        if not readings:
            return float('inf')
        max_dev = 0.0
        for i, (r, t, w) in enumerate(zip(readings, targets, weights)):
            dev = _effective_deviation(r, t, ranges[i] if ranges else None)
            max_dev = max(max_dev, w * abs(dev))
        return max_dev
