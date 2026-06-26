"""优化问题定义"""
from __future__ import annotations


class OptimizationProblem:
    """优化问题定义（不可变数据容器）

    由 optimizer._parse_objectives 解析配置后注入，不直接解析 JSON。
    """

    def __init__(self, objective_groups: list, all_obj_pvs: list,
                 group_indices: list, aggregate_fn):
        self.objective_groups = objective_groups
        self._all_obj_pvs = all_obj_pvs
        self._group_indices = group_indices
        self._aggregate = aggregate_fn

    @property
    def all_obj_pvs(self):
        # type: () -> list[str]
        return self._all_obj_pvs

    @property
    def group_indices(self):
        # type: () -> list[list[int]]
        return self._group_indices

    def compute_score(self, readings, caget_fn=None):
        # type: (list, callable) -> tuple
        group_scores = []
        for g, indices in zip(self.objective_groups, self._group_indices):
            grp_readings = []
            for pi, (idx, tr) in enumerate(zip(indices, g['transforms'])):
                raw = readings[idx]
                if tr is not None:
                    tlist = tr if isinstance(tr, list) else [tr]
                    for t in tlist:
                        raw = t(raw, pv_name=g['pvs'][pi], caget_fn=caget_fn)
                grp_readings.append(raw)

            if any(r is None for r in grp_readings):
                score = float('inf')
            else:
                score = g['scorer'](
                    grp_readings, g['targets'], g['weights'], g['ranges']
                )
            group_scores.append(score)

        overall = self._aggregate(
            group_scores,
            [g['weight'] for g in self.objective_groups]
        )
        return overall, group_scores
