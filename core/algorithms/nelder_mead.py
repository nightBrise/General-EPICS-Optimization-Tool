import numpy as np
import scipy.optimize as spo
from .registry import register_algorithm


@register_algorithm("nelder-mead")
class NelderMeadAlgorithm:
    """Nelder-Mead (scipy minimize)"""

    def run(self, objective, bounds, budget, params, history, progress_fn):
        # type: (callable, list, int, dict, object, callable) -> object
        xatol = params.get('xatol', 0.0001)
        fatol = params.get('fatol', 0.0001)

        initial = history.parameters[0] if history.parameters else \
                  [(b[0] + b[1]) / 2.0 for b in bounds]
        x0 = np.array(initial, dtype=float)

        count_before = len(history.iterations)

        print("\n\u5f00\u59cb\u4f18\u5316: scipy Nelder-Mead, {} \u6b21\u8fed\u4ee3...".format(budget))
        try:
            res = spo.minimize(
                objective, x0, method='Nelder-Mead',
                options={
                    'maxiter': budget,
                    'xatol': xatol,
                    'fatol': fatol,
                    'disp': False,
                }
            )
        except KeyboardInterrupt:
            print("\n\u7528\u6237\u4e2d\u65ad")
            raise

        count_after = len(history.iterations)
        print("  NM \u5b8c\u6210: \u5b9e\u9645 {} \u6b21\u51fd\u6570\u8c03\u7528".format(count_after - count_before))
        return history

    def __repr__(self):
        return "NelderMeadAlgorithm(nelder-mead)"
