from .base import Scorer, _effective_deviation
from .registry import register_scorer


@register_scorer("weighted_sum")
class WeightedSumScorer(Scorer):
    """加权和评分: Σ(wi * (ri - ti)) / Σ wi"""

    def __call__(self, readings, targets, weights, ranges=None):
        if not readings:
            return float('inf')
        total = 0.0
        w_sum = 0.0
        for i, (r, t, w) in enumerate(zip(readings, targets, weights)):
            dev = _effective_deviation(r, t, ranges[i] if ranges else None)
            total += w * dev
            w_sum += w
        if w_sum == 0:
            return float('inf')
        return total / w_sum
