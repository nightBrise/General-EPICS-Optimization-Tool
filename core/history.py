"""迭代记录容器"""
from __future__ import annotations


class History:
    """类型化迭代记录容器

    替代原来无类型的 dict。to_dict() 包含 result_recorder 所需全部字段。
    """

    def __init__(self, device_pvs, initial_values,
                 algorithm, budget,
                 objective_groups, group_indices):
        # type: (list, list, str, int, list, list) -> None
        self.device_pvs = list(device_pvs)
        self.initial_values = list(initial_values)
        self.algorithm = algorithm
        self.budget = budget

        self.iterations = []
        self.scores = []
        self.group_scores = []
        self.parameters = []
        self.readings = []
        self.elapsed_ms_list = []
        self.failures = []
        self.elapsed_sec = 0.0
        self.best_score = float('inf')
        self.best_params = None
        self.best_readings = None
        self.best_iteration_index = 0
        self.early_stop = False
        self.stop_iteration = budget

        self._groups_raw = [
            {'pvs': g['pvs'], 'targets': g['targets']}
            for g in objective_groups
        ]
        self._group_indices = group_indices

    def add_initial(self, score, group_scores):
        # type: (float, list) -> None
        self.iterations.append(0)
        self.scores.append(score)
        self.group_scores.append(group_scores)
        self.parameters.append(self.initial_values)
        self.readings.append([])
        self.elapsed_ms_list.append(0.0)

    def append(self, iteration, score, group_scores,
               params, readings, elapsed_ms):
        # type: (int, float, list, list, list, float) -> None
        self.iterations.append(iteration)
        self.scores.append(score)
        self.group_scores.append(group_scores)
        self.parameters.append(params)
        self.readings.append(readings)
        self.elapsed_ms_list.append(elapsed_ms)

    def update_best(self):
        # type: () -> None
        valid = [(i, s) for i, s in enumerate(self.scores)
                 if s is not None and s < float('inf')]
        if valid:
            self.best_iteration_index, self.best_score = min(valid, key=lambda x: x[1])
            self.best_params = self.parameters[self.best_iteration_index]
            self.best_readings = self.readings[self.best_iteration_index] \
                if self.best_iteration_index < len(self.readings) else None

    def to_dict(self):
        # type: () -> dict
        return {
            'device_pvs': self.device_pvs,
            'iterations': self.iterations,
            'scores': self.scores,
            'group_scores': self.group_scores,
            'parameters': self.parameters,
            'readings': self.readings,
            'elapsed_ms_list': self.elapsed_ms_list,
            'failure_log': self.failures,
            'elapsed_sec': self.elapsed_sec,
            'algorithm': self.algorithm,
            'budget': self.budget,
            'early_stop': self.early_stop,
            'stop_iteration': self.stop_iteration,
            'best_score': self.best_score,
            'best_params': self.best_params,
            'best_readings': self.best_readings,
            'best_iteration_index': self.best_iteration_index,
            '_groups': self._groups_raw,
            '_group_indices': self._group_indices,
        }
