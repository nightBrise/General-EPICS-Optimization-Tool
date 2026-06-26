"""贝叶斯优化算法插件 — 三级降级策略"""
from __future__ import annotations
from .registry import register_algorithm


@register_algorithm("bayesian")
class BayesianAlgorithm:
    """贝叶斯优化 — GP + EI (三级降级: skopt → sklearn → DE)"""

    def run(self, objective, bounds, budget, params, history, progress_fn):
        # type: (callable, list, int, dict, object, callable) -> object
        try:
            import skopt
            return self._run_skopt(objective, bounds, budget, params, history, progress_fn)
        except ImportError:
            pass

        try:
            from sklearn.gaussian_process import GaussianProcessRegressor
            return self._run_custom(objective, bounds, budget, params, history, progress_fn)
        except ImportError:
            print("  \u8b66\u544a: Bayesian \u7b97\u6cd5\u9700\u8981 scikit-learn\uff0c\u964d\u7ea7\u5230 differential_evolution")
            from .registry import get_algorithm
            return get_algorithm("de")().run(objective, bounds, budget, params, history, progress_fn)

    def _run_skopt(self, objective, bounds, budget, params, history, progress_fn):
        import skopt

        dimensions = [skopt.space.Real(lo, hi) for lo, hi in bounds]
        acq = params.get('acq_func', 'EI')
        n_init = params.get('n_initial_points', min(10, budget // 2))
        xi = params.get('xi', 0.01)

        x0 = history.parameters if history.parameters else None
        y0 = history.scores if history.scores else None

        print("\n\u5f00\u59cb\u4f18\u5316: Bayesian (skopt gp_minimize), {} \u6b21\u8fed\u4ee3...".format(budget))
        skopt.gp_minimize(
            objective, dimensions,
            n_calls=budget, n_initial_points=n_init,
            acq_func=acq, xi=xi,
            x0=x0, y0=y0,
            verbose=False,
        )
        return history

    def _run_custom(self, objective, bounds, budget, params, history, progress_fn):
        import numpy as np
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import Matern, ConstantKernel
        from scipy.stats import norm

        # --- 参数 ---
        alpha = params.get('alpha', 0.1)
        n_candidates = params.get('n_candidates', 5000)
        xi = params.get('xi', 0.01)

        # --- 初始化数据 ---
        X = np.array(history.parameters, dtype=float)
        y = np.array(history.scores, dtype=float)

        # --- GP 模型 ---
        # 使用 ConstantKernel × Matern 替代 Matern + WhiteKernel
        # WhiteKernel 在 Griewank 等高频函数中会导致 length_scale 膨胀
        kernel = ConstantKernel(1.0, constant_value_bounds=(1e-2, 1e4)) \
            * Matern(nu=2.5, length_scale=100.0)
        gp = GaussianProcessRegressor(
            kernel=kernel, alpha=alpha, normalize_y=True, n_restarts_optimizer=3)

        print("\n\u5f00\u59cb\u4f18\u5316: Bayesian (sklearn GP + EI), {} \u6b21\u8fed\u4ee3...".format(budget))

        try:
            for i in range(budget):
                gp.fit(X, y)
                x_next = self._acq_optimize(gp, y.min(), bounds, n_candidates, xi, norm)
                objective(x_next)
                X = np.array(history.parameters, dtype=float)
                y = np.array(history.scores, dtype=float)
        except KeyboardInterrupt:
            print("\n\u7528\u6237\u4e2d\u65ad")
            raise

        return history

    @staticmethod
    def _expected_improvement(mu, sigma, y_best, xi, norm):
        import numpy as np
        with np.errstate(divide='ignore'):
            imp = y_best - mu - xi
            Z = imp / sigma
            ei = imp * norm.cdf(Z) + sigma * norm.pdf(Z)
            ei[sigma < 1e-9] = 0.0
        return ei

    @staticmethod
    def _acq_optimize(gp, y_best, bounds, n_candidates, xi, norm):
        import numpy as np
        dim = len(bounds)
        X_candidates = np.random.uniform(
            [b[0] for b in bounds],
            [b[1] for b in bounds],
            size=(n_candidates, dim)
        )
        mu, sigma = gp.predict(X_candidates, return_std=True)
        ei = BayesianAlgorithm._expected_improvement(mu, sigma, y_best, xi, norm)
        best_idx = np.argmax(ei)
        return X_candidates[best_idx].tolist()

    def __repr__(self):
        return "BayesianAlgorithm()"
