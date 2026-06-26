import scipy.optimize as spo
from .registry import register_algorithm


@register_algorithm("differential_evolution", "de")
class DEAlgorithm:
    """Differential Evolution (scipy)"""

    def run(self, objective, bounds, budget, params, history, progress_fn):
        # type: (callable, list, int, dict, object, callable) -> object
        tol = params.get('tol', 0.01)

        print("\n\u5f00\u59cb\u4f18\u5316: scipy differential_evolution, {} \u6b21\u8fed\u4ee3...".format(budget))
        try:
            spo.differential_evolution(
                objective,
                bounds,
                maxiter=budget,
                seed=None,
                callback=None,
                tol=tol,
                polish=False,
            )
        except KeyboardInterrupt:
            print("\n\u7528\u6237\u4e2d\u65ad")
            raise

        return history

    def __repr__(self):
        return "DEAlgorithm(differential_evolution)"
