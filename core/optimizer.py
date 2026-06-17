"""通用 EPICS 优化器

核心循环: ask → apply → read → score → tell → stop
"""
import sys
import numpy as np
import nevergrad as ng

try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        """纯文本进度条（无 tqdm 依赖时启用）"""
        def __init__(self, iterable, desc="", total=None, **_):
            self.iterable = iterable
            self.total = total or len(iterable)
            self.desc = desc
            self.n = 0

        def __iter__(self):
            for item in self.iterable:
                yield item
                self.n += 1
                pct = self.n * 100 // self.total
                bar = "█" * (pct // 2) + " " * (50 - pct // 2)
                line = f"  {self.desc}: [{bar}] {self.n}/{self.total}"
                sys.stdout.write(f"\r{line}")
                sys.stdout.flush()
            sys.stdout.write("\n")

        @staticmethod
        def write(msg):
            sys.stdout.write(f"\r\033[K{msg}\n")

from .epics_backend import caget_many, caget
from .variable_manager import VariableManager
from .hardware_controller import HardwareController
from .scoring.registry import create_scorer
from .transforms.registry import create_transform


class GenericOptimizer:
    """通用 EPICS 优化器"""

    def __init__(self, config: dict):
        """初始化优化器

        Args:
            config: 完整配置字典
        """
        self.config = config

        self.variable_mgr = VariableManager(config)
        self.hardware = HardwareController(config)
        self._all_obj_pvs: list[str] = []
        self._group_indices: list[list[int]] = []

        self._parse_objectives(config.get('objectives', {}))

        self._build_pv_index()

        opt = config.get('optimization', {})
        self.algorithm = opt.get('algorithm', 'NGOpt')
        self.budget = opt.get('budget', 50)
        self.early_stop_config = opt.get('early_stopping', {})

    def _parse_objectives(self, obj_config: dict) -> None:
        """解析目标配置

        Args:
            obj_config: objectives 字段
        """
        groups = obj_config.get('groups', [])
        self.objective_groups = []

        for g in groups:
            name = g.get('name', f"group_{len(self.objective_groups)}")
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
                    transforms.append(create_transform(item.get('transform')))

            scorer = create_scorer(
                scoring_config.get('method', 'l2'),
                scoring_config.get('params', {})
            )

            self.objective_groups.append({
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
            raise ValueError(f"不支持的总体评分方式: {overall}")

    def _weighted_sum_aggregate(self, group_scores, group_weights):
        total_w = sum(group_weights)
        if total_w == 0:
            return float('inf')
        return sum(s * w for s, w in zip(group_scores, group_weights)) / total_w

    def _build_pv_index(self) -> None:
        """构建目标 PV 去重索引

        解决多组引用同一个 PV 时的重复读取和索引偏移问题。
        """
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

    def _compute_score(self, readings: list) -> tuple:
        """计算各组分评分和总体评分

        Args:
            readings: 所有目标 PV 的读数

        Returns:
            tuple: (overall_score, list_of_group_scores)
        """
        group_scores = []
        for g, indices in zip(self.objective_groups, self._group_indices):
            grp_readings = []
            for pi, (idx, tr) in enumerate(zip(indices, g['transforms'])):
                raw = readings[idx]
                if tr is not None:
                    tlist = tr if isinstance(tr, list) else [tr]
                    for t in tlist:
                        raw = t(raw, pv_name=g['pvs'][pi], caget_fn=caget)
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

    def run(self) -> dict:
        """执行优化

        Returns:
            dict: 优化结果
        """
        var_mgr = self.variable_mgr
        initial_values = var_mgr.read_initial_values()
        var_mgr.initial_values = initial_values
        self.hardware.save_initial(var_mgr.pvs, initial_values)

        # 验证变量 PV ranges
        for i, r in enumerate(var_mgr.ranges):
            if not (isinstance(r, (list, tuple)) and len(r) == 2):
                raise ValueError(
                    f"variables[{i}] ({var_mgr.pvs[i]}) range 无效: {r}")
            try:
                float(r[0]), float(r[1])
            except (TypeError, ValueError):
                raise ValueError(
                    f"variables[{i}] ({var_mgr.pvs[i]}) range 包含非数字: {r}")

        # Nevergrad 参数空间
        parametrization = ng.p.Instrumentation(**{
            f"x{i}": ng.p.Scalar(
                init=initial_values[i],
                lower=var_mgr.ranges[i][0],
                upper=var_mgr.ranges[i][1]
            )
            for i in range(len(var_mgr))
        })

        try:
            optimizer_class = ng.optimizers.registry[self.algorithm]
        except KeyError:
            print(f"算法 {self.algorithm} 未找到，使用 NGOpt")
            optimizer_class = ng.optimizers.NGOpt

        optimizer = optimizer_class(
            parametrization=parametrization,
            budget=self.budget,
            num_workers=1,
        )

        # 历史记录
        history = {
            'device_pvs': list(var_mgr.pvs),
            'iterations': [],
            'scores': [],
            'group_scores': [],
            'parameters': [initial_values],
            'readings': [],
            'algorithm': self.algorithm,
            'budget': self.budget,
            'early_stop': False,
            'stop_iteration': self.budget,
        }

        # 初始点评估
        print("评估初始点...")
        readings = caget_many(self._all_obj_pvs)
        initial_score, grp_scores = self._compute_score(readings)
        print(f"初始评分: {initial_score:.4f}")
        if grp_scores:
            for g, s in zip(self.objective_groups, grp_scores):
                print(f"  组 [{g['name']}]: {s:.4f}")

        history['scores'].append(initial_score)
        history['group_scores'].append(grp_scores)
        history['readings'].append(readings)

        # 早停参数
        es = self.early_stop_config
        es_enabled = es.get('enabled', True)
        es_patience = es.get('patience', 10)
        es_min_improvement = es.get('min_relative_improvement', 0.005)

        best_score = initial_score
        no_improve = 0

        # 优化循环
        print(f"\n开始优化: {self.algorithm} 算法, {self.budget} 次迭代...")

        for i in tqdm(range(self.budget), desc="优化进度"):
            try:
                candidate = optimizer.ask()
                params = [candidate.kwargs[f"x{j}"] for j in range(len(var_mgr))]

                self.hardware.apply(var_mgr.pvs, params)
                readings = caget_many(self._all_obj_pvs)
                score, grp_scores = self._compute_score(readings)

                if np.isinf(score) or np.isnan(score):
                    print(f"  警告: 迭代 {i+1} 无效评分 {score}")
                    score = float('inf')

                optimizer.tell(candidate, score)

                history['iterations'].append(i + 1)
                history['scores'].append(score)
                history['group_scores'].append(grp_scores)
                history['parameters'].append(params)
                history['readings'].append(readings)

                tqdm.write(f"  当前: {score:.4f} 最佳: {best_score:.4f}")

                if es_enabled:
                    if score < best_score and best_score > 0:
                        rel_imp = (best_score - score) / best_score
                        if rel_imp > es_min_improvement:
                            best_score = score
                            no_improve = 0
                        else:
                            no_improve += 1
                    elif score < best_score:
                        best_score = score
                        no_improve = 0
                    else:
                        no_improve += 1

                    if no_improve >= es_patience:
                        print(f"\n早停! 连续 {es_patience} 次无显著改进")
                        history['early_stop'] = True
                        history['stop_iteration'] = i + 1
                        break

            except KeyboardInterrupt:
                print("\n用户中断，正在回滚...")
                self.hardware.rollback()
                raise
            except Exception as e:
                print(f"\n迭代 {i+1} 错误: {e}")
                continue

        # 最佳结果
        valid = [(j, s) for j, s in enumerate(history['scores'])
                 if not np.isinf(s) and not np.isnan(s)]
        if valid:
            best_idx, best_score = min(valid, key=lambda x: x[1])
            best_params = history['parameters'][best_idx]
        else:
            best_idx, best_score = 0, initial_score
            best_params = initial_values

        history['best_params'] = best_params
        history['best_score'] = best_score
        history['best_iteration_index'] = best_idx
        history['_groups'] = [
            {'pvs': g['pvs'], 'targets': g['targets']}
            for g in self.objective_groups
        ]

        print(f"\n优化完成! 最佳评分: {best_score:.4f}")
        return history

    def rollback(self):
        """手动触发回滚"""
        self.hardware.rollback()
