"""优化目标函数 — 黑盒，无梯度"""
from __future__ import annotations
import time
import numpy as np
from .epics_backend import caget_many, caget


class ObjectiveFunction:
    """优化目标函数 — callable(x) -> float

    每次调用 = 一次完整的 ask → apply → read → score 循环。
    x 可以是 numpy array（scipy 传入）或 list。
    """

    def __init__(self, hw, problem, history, var_pvs, progress_fn):
        # type: (object, object, object, list, callable) -> None
        self.hw = hw
        self.problem = problem
        self.history = history
        self.var_pvs = var_pvs
        self.progress_fn = progress_fn
        self.iteration = 0

    def __call__(self, x):
        # type: (object) -> float
        self.iteration += 1
        t0 = time.time()

        values = x.tolist() if hasattr(x, 'tolist') else list(x)

        self.hw.apply(self.var_pvs, values,
                      iteration=self.iteration,
                      failure_log=self.history.failures)

        readings = caget_many(self.problem.all_obj_pvs)
        score, grp_scores = self.problem.compute_score(readings, caget)

        if np.isinf(score) or np.isnan(score):
            score = float('inf')

        if score < self.history.best_score:
            self.history.best_score = score

        elapsed_ms = (time.time() - t0) * 1000
        self.history.append(self.iteration, score, grp_scores, values, readings, elapsed_ms)

        self.progress_fn(self.iteration, score, self.history.best_score)
        return score
