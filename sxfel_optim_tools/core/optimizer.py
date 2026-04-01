"""通用优化器模块

封装Nevergrad优化循环，提供统一的优化接口。
"""
import time
import numpy as np
import nevergrad as ng
import sys
from tqdm import tqdm

from .utils import select_optimization_devices


class Optimizer:
    """通用优化器，封装Nevergrad优化循环"""

    def __init__(self, config, objective_fn):
        """初始化优化器

        Args:
            config: 配置字典
            objective_fn: 目标函数对象（BaseObjective子类）
        """
        self.config = config
        self.objective_fn = objective_fn
        self.opt_config = config.get('optimization', {})

    def run(self, device_types=None, device_pvs=None):
        """执行优化

        Args:
            device_types: 要优化的设备类型列表
            device_pvs: 要优化的具体设备PV列表

        Returns:
            tuple: (最佳参数, 最佳分数, 设备PV列表, 优化历史)
        """
        # 重置全局指标
        from .objectives.metrics import metrics
        metrics.reset()

        # 选择设备
        device_pvs, current_values, bounds = select_optimization_devices(
            self.config, device_types, device_pvs
        )

        # 定义参数空间
        parametrization = ng.p.Instrumentation(
            **{f"x{i}": ng.p.Scalar(
                init=current_values[i],
                lower=bounds[i][0],
                upper=bounds[i][1]
            ) for i in range(len(device_pvs))}
        )

        # 创建优化器
        algorithm = self.opt_config.get('algorithm', 'Compass')
        budget = self.opt_config.get('budget', 50)

        try:
            optimizer_class = ng.optimizers.registry[algorithm]
        except KeyError:
            print(f"算法 {algorithm} 不在nevergrad注册表中，使用NGOpt")
            optimizer_class = ng.optimizers.NGOpt

        optimizer = optimizer_class(
            parametrization=parametrization,
            budget=budget,
            num_workers=1
        )

        # 优化历史
        optimization_history = {
            'device_pvs': device_pvs.copy(),
            'device_names': [pv.split(':')[-1] for pv in device_pvs],
            'iterations': [],
            'algorithm': algorithm,
            'budget': budget,
            'early_stop': False,
            'stop_iteration': budget
        }

        # 早停参数
        early_stop_config = self.opt_config.get('early_stopping', {})
        early_stop_enabled = early_stop_config.get('enabled', True)
        early_stop_patience = early_stop_config.get('patience', 10)
        min_relative_improvement = early_stop_config.get('min_relative_improvement', 0.005)

        # 评估初始点
        print("\n评估初始点...")
        initial_params_dict = {f"x{i}": current_values[i] for i in range(len(current_values))}
        initial_score = self.objective_fn.get_score(current_values, device_pvs)

        iteration_history = {
            'parameters': [current_values.copy()],
            'scores': [initial_score]
        }

        print(f"初始评分: {initial_score:.4f}")

        # 执行优化
        print(f"\n开始优化: {algorithm} 算法, {budget} 次迭代...")
        start_time = time.time()
        best_score_so_far = initial_score
        no_improvement_count = 0

        for i in tqdm(range(budget), desc="优化进度", unit="iter"):
            try:
                # 获取建议
                candidate = optimizer.ask()

                # 评估
                params = [candidate.kwargs[f"x{j}"] for j in range(len(device_pvs))]
                value = self.objective_fn.get_score(params, device_pvs)

                if np.isinf(value) or np.isnan(value):
                    print(f"  警告: 迭代 {i+1} 返回无效值 {value}")
                    value = float('inf')

                # 告知优化器
                optimizer.tell(candidate, value)

                # 记录历史
                iteration_history['parameters'].append(params.copy())
                iteration_history['scores'].append(value)
                optimization_history['iterations'].append(i + 1)

                # 早停检查
                if early_stop_enabled:
                    if value < best_score_so_far:
                        relative_improvement = (best_score_so_far - value) / best_score_so_far
                        if relative_improvement > min_relative_improvement:
                            best_score_so_far = value
                            no_improvement_count = 0
                        else:
                            no_improvement_count += 1
                    else:
                        no_improvement_count += 1

                    if no_improvement_count >= early_stop_patience:
                        print(f"\n早停! 连续 {early_stop_patience} 次无显著改进")
                        optimization_history['early_stop'] = True
                        optimization_history['stop_iteration'] = i + 1
                        break

                # 更新进度条描述
                elapsed = time.time() - start_time
                tqdm.write(f"  当前: {value:.4f} 最佳: {best_score_so_far:.4f} 耗时: {elapsed:.1f}s")

            except Exception as e:
                print(f"\n错误 (迭代 {i+1}): {e}")
                continue

        print("\n优化完成!")

        # 获取最佳参数
        try:
            recommendation = optimizer.provide_recommendation()
            best_params = [recommendation.kwargs[f"x{i}"] for i in range(len(device_pvs))]
            best_score = recommendation.loss
        except Exception:
            print("获取推荐失败，使用观察到的最佳值")
            valid_scores = [(j, s) for j, s in enumerate(iteration_history['scores'])
                           if not np.isinf(s) and not np.isnan(s)]
            if valid_scores:
                best_idx, best_score = min(valid_scores, key=lambda x: x[1])
                best_params = iteration_history['parameters'][best_idx]
            else:
                best_params = current_values.copy()
                best_score = initial_score

        # 整合历史
        optimization_history['iteration_history'] = iteration_history
        optimization_history['best_params'] = best_params.copy()
        optimization_history['best_score'] = best_score

        # 获取当前指标
        current_metrics = metrics.get_current()
        best_metrics = metrics.get_best()
        optimization_history['initial_score'] = initial_score
        optimization_history['initial_metrics'] = current_metrics
        optimization_history['best_metrics'] = best_metrics

        return best_params, best_score, device_pvs, optimization_history
