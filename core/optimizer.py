"""通用 EPICS 优化器 — 编排层

核心循环: ask → apply → read → score → tell → stop
通过 core/algorithms/ 插件架构分发到各算法后端。
"""
from __future__ import annotations
import time

try:
    import nevergrad
    _HAS_NEVERGRAD = True
except ImportError:
    _HAS_NEVERGRAD = False

from .epics_backend import caget_many, caget
from .variable_manager import VariableManager
from .hardware_controller import HardwareController
from .scoring.registry import create_scorer
from .transforms.registry import create_transform
from .algorithms.registry import get_algorithm
from .problem import OptimizationProblem
from .history import History
from .objective import ObjectiveFunction


def _resolve_algorithm(algorithm_name, has_nevergrad):
    # type: (str, bool) -> str
    defaults = ('NGOpt' if has_nevergrad else 'differential_evolution')
    return algorithm_name or defaults


class GenericOptimizer:
    """通用 EPICS 优化器 — 编排"""

    def __init__(self, config):
        # type: (dict) -> None
        self.config = config

        self.variable_mgr = VariableManager(config)
        self.hardware = HardwareController(config)

        self.objective_groups = self._parse_objectives(
            config.get('objectives', {}))
        self._build_pv_index()
        aggregate_fn = self._weighted_sum_aggregate

        self.problem = OptimizationProblem(
            self.objective_groups, self._all_obj_pvs,
            self._group_indices, aggregate_fn
        )

        opt = config.get('optimization', {})
        self.algorithm = _resolve_algorithm(
            opt.get('algorithm', ''), _HAS_NEVERGRAD)
        self.algorithm_params = opt.get('algorithm_params', {})
        self.budget = opt.get('budget', 50)

    def _parse_objectives(self, obj_config):
        # type: (dict) -> list
        groups = obj_config.get('groups', [])
        objective_groups = []

        for g in groups:
            name = g.get('name', "group_{}".format(len(objective_groups)))
            weight = g.get('weight', 1.0)
            pvs_raw = g.get('pvs', [])
            scoring_config = g.get('scoring', {'method': 'l2'})

            pvs = []
            targets = []
            weights = []
            ranges = []
            transforms = []

            for item in pvs_raw:
                if isinstance(item, str):
                    pvs.append(item)
                    targets.append(0.0)
                    weights.append(1.0)
                    ranges.append(None)
                    transforms.append(None)
                else:
                    pvs.append(item['pv'])
                    targets.append(item.get('target', 0.0))
                    weights.append(item.get('weight', 1.0))
                    ranges.append(item.get('range', None))
                    transforms.append(
                        create_transform(item.get('transform')))

            scorer = create_scorer(
                scoring_config.get('method', 'l2'),
                scoring_config.get('params', {})
            )

            objective_groups.append({
                'name': name,
                'weight': weight,
                'pvs': pvs,
                'targets': targets,
                'weights': weights,
                'ranges': ranges,
                'transforms': transforms,
                'scorer': scorer,
            })

        overall = obj_config.get('overall_scoring', 'weighted_sum')
        if overall == 'weighted_sum':
            self._aggregate = self._weighted_sum_aggregate
        else:
            raise ValueError(
                "\u4e0d\u652f\u6301\u7684\u603b\u4f53\u8bc4\u5206\u65b9\u5f0f: {}".format(overall))

        return objective_groups

    def _weighted_sum_aggregate(self, group_scores, group_weights):
        total_w = sum(group_weights)
        if total_w == 0:
            return float('inf')
        return sum(s * w for s, w in zip(group_scores, group_weights)) / total_w

    def _build_pv_index(self):
        # type: () -> None
        seen = {}
        self._all_obj_pvs = []
        self._group_indices = []

        for g in self.objective_groups:
            indices = []
            for pv in g['pvs']:
                if pv not in seen:
                    seen[pv] = len(self._all_obj_pvs)
                    self._all_obj_pvs.append(pv)
                indices.append(seen[pv])
            self._group_indices.append(indices)

    @staticmethod
    def _default_progress(iteration, score, best):
        import sys
        sys.stdout.write("\r  [{:3d}] \u5f53\u524d: {:.4f} \u6700\u4f73: {:.4f}{}".format(
            iteration, score, best, ' ' * 10))
        sys.stdout.flush()

    def _compute_score(self, readings):
        # type: (list) -> tuple
        """兼容旧接口（run_optimization.py _read_current_values）"""
        return self.problem.compute_score(readings, caget)

    @property
    def all_obj_pvs(self):
        # type: () -> list[str]
        return self.problem.all_obj_pvs

    def run(self):
        # type: () -> dict
        var_mgr = self.variable_mgr
        initial_values = var_mgr.read_initial_values()
        var_mgr.initial_values = initial_values
        self.hardware.save_initial(var_mgr.pvs, initial_values)

        for i, r in enumerate(var_mgr.ranges):
            if not (isinstance(r, (list, tuple)) and len(r) == 2):
                raise ValueError(
                    "variables[{}] ({}) range \u65e0\u6548: {}".format(
                        i, var_mgr.pvs[i], r))
            try:
                float(r[0]), float(r[1])
            except (TypeError, ValueError):
                raise ValueError(
                    "variables[{}] ({}) range \u5305\u542b\u975e\u6570\u5b57: {}".format(
                        i, var_mgr.pvs[i], r))

        # Fix 4: \u8fb9\u754c\u88c1\u526a
        for i, val in enumerate(initial_values):
            lo, hi = var_mgr.ranges[i]
            if val < lo:
                print("  \u8b66\u544a: {} \u521d\u59cb\u503c {:.4f} < \u4e0b\u754c {:.4f}\uff0c\u88c1\u526a\u5230 {:.4f}".format(
                    var_mgr.pvs[i], val, lo, lo))
                initial_values[i] = lo
            elif val > hi:
                print("  \u8b66\u544a: {} \u521d\u59cb\u503c {:.4f} > \u4e0a\u754c {:.4f}\uff0c\u88c1\u526a\u5230 {:.4f}".format(
                    var_mgr.pvs[i], val, hi, hi))
                initial_values[i] = hi

        # Fix 1: Nevergrad \u964d\u7ea7\u63d0\u9192
        if self.algorithm in ('ngopt', 'cma') and not _HAS_NEVERGRAD:
            print("  \u8b66\u544a: Nevergrad \u672a\u5b89\u88c5\uff0c{} \u7b97\u6cd5\u4e0d\u53ef\u7528\uff0c\u81ea\u52a8\u964d\u7ea7\u5230 differential_evolution".format(
                self.algorithm))
            self.algorithm = 'differential_evolution'

        history = History(
            var_mgr.pvs, initial_values, self.algorithm, self.budget,
            self.objective_groups, self._group_indices)

        print("\u8bc4\u4f30\u521d\u59cb\u70b9...")
        readings = caget_many(self.problem.all_obj_pvs)
        initial_score, grp_scores = self.problem.compute_score(readings, caget)
        print("\u521d\u59cb\u8bc4\u5206: {:.4f}".format(initial_score))
        if grp_scores:
            for g, s in zip(self.objective_groups, grp_scores):
                print("  \u7ec4 [{}]: {:.4f}".format(g['name'], s))
        history.add_initial(initial_score, grp_scores)

        objective = ObjectiveFunction(
            self.hardware, self.problem, history,
            var_mgr.pvs, self._default_progress)

        algo_cls = get_algorithm(self.algorithm)
        if algo_cls is None:
            print("\u7b97\u6cd5 {} \u672a\u77e5\uff0c\u4f7f\u7528 DE".format(self.algorithm))
            algo_cls = get_algorithm("de")

        algo = algo_cls()
        bounds = [(r[0], r[1]) for r in var_mgr.ranges]

        start = time.time()
        algo.run(objective, bounds, self.budget, self.algorithm_params,
                 history, print)
        history.elapsed_sec = time.time() - start
        history.update_best()

        print("\n\u4f18\u5316\u5b8c\u6210! \u6700\u4f73\u8bc4\u5206: {:.4f}".format(history.best_score))
        return history.to_dict()

    def rollback(self):
        self.hardware.rollback()
