"""Nevergrad 优化算法插件"""
from __future__ import annotations
import time
from .registry import register_algorithm


def _make_ng_objective(objective, bounds):
    """将 Nevergrad 的关键字参数调用转为 list 调用"""
    def ng_objective(**kwargs):
        values = [kwargs["x{}".format(i)] for i in range(len(bounds))]
        return objective(values)
    return ng_objective


@register_algorithm("ngopt", "NGOpt")
class NGOptAlgorithm:
    """Nevergrad NGOpt — 自适应元算法"""

    def run(self, objective, bounds, budget, params, history, progress_fn):
        # type: (callable, list, int, dict, object, callable) -> object
        import nevergrad as ng

        instrumentation = ng.p.Instrumentation(**{
            "x{}".format(i): ng.p.Scalar(lower=b[0], upper=b[1])
            for i, b in enumerate(bounds)
        })

        try:
            optimizer = ng.optimizers.registry["NGOpt"](
                parametrization=instrumentation, budget=budget)
        except KeyError:
            print("\u672a\u627e\u5230 NGOpt\uff0c\u4f7f\u7528 NGOpt10")
            optimizer = ng.optimizers.registry["NGOpt10"](
                parametrization=instrumentation, budget=budget)

        ng_obj = _make_ng_objective(objective, bounds)

        print("\n\u5f00\u59cb\u4f18\u5316: Nevergrad NGOpt, {} \u6b21\u8fed\u4ee3...".format(budget))
        start = time.time()
        try:
            optimizer.minimize(ng_obj)
        except KeyboardInterrupt:
            print("\n\u7528\u6237\u4e2d\u65ad")
            raise
        elapsed = time.time() - start
        print("  NGOpt \u5b8c\u6210, \u8017\u65f6 {:.1f}\u79d2".format(elapsed))

        return history

    def __repr__(self):
        return "NGOptAlgorithm()"


@register_algorithm("cma", "CMA")
class CMAAlgorithm:
    """Nevergrad CMA — 协方差自适应算法"""

    def run(self, objective, bounds, budget, params, history, progress_fn):
        # type: (callable, list, int, dict, object, callable) -> object
        import nevergrad as ng

        instrumentation = ng.p.Instrumentation(**{
            "x{}".format(i): ng.p.Scalar(lower=b[0], upper=b[1])
            for i, b in enumerate(bounds)
        })

        try:
            optimizer = ng.optimizers.registry["CMA"](
                parametrization=instrumentation, budget=budget)
        except KeyError:
            print("\u672a\u627e\u5230 CMA\uff0c\u4f7f\u7528 CM")
            optimizer = ng.optimizers.registry["CM"](
                parametrization=instrumentation, budget=budget)

        ng_obj = _make_ng_objective(objective, bounds)

        print("\n\u5f00\u59cb\u4f18\u5316: Nevergrad CMA, {} \u6b21\u8fed\u4ee3...".format(budget))
        start = time.time()
        try:
            optimizer.minimize(ng_obj)
        except KeyboardInterrupt:
            print("\n\u7528\u6237\u4e2d\u65ad")
            raise
        elapsed = time.time() - start
        print("  CMA \u5b8c\u6210, \u8017\u65f6 {:.1f}\u79d2".format(elapsed))

        return history

    def __repr__(self):
        return "CMAAlgorithm()"
