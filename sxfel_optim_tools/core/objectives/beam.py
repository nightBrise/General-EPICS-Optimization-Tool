"""束流目标函数模块

提供束流尺寸优化的目标函数和优化流程。
"""
import numpy as np
import nevergrad as ng
import time
import sys
import os

from .base import BaseObjective
from .registry import register_objective
from .metrics import metrics
from ..epics_backend import caget, caput, caget_many, caput_many
from ..utils import (
    safe_device_operation,
    select_optimization_devices,
    get_image_from_YAG,
    calculate_spot_metrics,
)


@register_objective("beam_size")
class BeamObjective(BaseObjective):
    """束流尺寸优化目标函数

    优化目标：最小化束流尺寸同时优化圆度
    """

    def __init__(self, config):
        """初始化束流目标函数

        Args:
            config: 配置字典
        """
        super().__init__(config)
        self.camera_config = config.get('camera', {})
        self.num_averages = self.params.get('num_averages', 3)
        self.target_diagonal_size = self.params.get('target_diagonal_size_pixels', 0)
        self.maintain_position = self.params.get('maintain_position', False)

        # 参数配置
        self.repetition_rate = self.params.get('repetition_rate', 10)
        self.min_adjust_interval = self.params.get('min_adjust_interval', 6)
        self.poll_interval = self.params.get('poll_interval', 0.2)
        self.tolerance = self.params.get('tolerance', 0.0001)
        self.max_wait = self.params.get('max_wait', 10)

        self.initial_centroid_x = None
        self.initial_centroid_y = None
        self._raw_image = None
        self._last_adjust_time = 0

    def get_score(self, params, device_pvs):
        """评估束流尺寸

        Args:
            params: 设备参数列表
            device_pvs: 设备PV列表

        Returns:
            float: 综合评分（越小越好）
        """
        # 1. 安全设置设备参数
        success = safe_device_operation(device_pvs, params, self.config)
        if not success:
            return float('inf')

        # 2. 检查硬件调整间隔
        elapsed = time.time() - self._last_adjust_time
        if elapsed < self.min_adjust_interval:
            wait_time = self.min_adjust_interval - elapsed
            print(f"  等待硬件调整间隔: {wait_time:.1f}秒")
            time.sleep(wait_time)

        # 3. 轮询等待所有元件达到设定值
        from ..utils import wait_for_all_devices_settled
        success, failed_devs = wait_for_all_devices_settled(
            device_pvs, params,
            tolerance=self.tolerance,
            max_wait=self.max_wait,
            poll_interval=self.poll_interval
        )

        if not success:
            error_msg = "错误: 以下元件写入失败:\n"
            for pv, info in failed_devs.items():
                if info['deviation'] is not None:
                    error_msg += f"  - {pv}: 当前={info['current']:.4f}, 目标={info['target']:.4f}, 偏差={info['deviation']:.6f}\n"
                else:
                    error_msg += f"  - {pv}: 读取失败\n"
            error_msg += "请处理上述问题，优化将回滚到初始参数。"
            from core.optimizer import OptimizationError
            raise OptimizationError(error_msg)

        self._last_adjust_time = time.time()

        # 4. 获取平均图像和束斑指标
        raw_image, size_x, size_y, centroid_x, centroid_y, combined_size, roundness = \
            self._get_average_YAG_image()

        self._raw_image = raw_image

        # 检查结果有效性
        if not (np.isfinite(size_x) and np.isfinite(size_y) and
                np.isfinite(centroid_x) and np.isfinite(centroid_y)):
            return float('inf')

        # 记录初始位置
        if self.initial_centroid_x is None:
            self.initial_centroid_x = centroid_x
            self.initial_centroid_y = centroid_y

        # 更新当前指标
        current_metrics = {
            'physical_size': combined_size,
            'size_x': size_x,
            'size_y': size_y,
            'roundness': roundness,
            'params': params.copy(),
            'centroid_x': centroid_x,
            'centroid_y': centroid_y
        }

        # 计算评分
        size_score = combined_size
        non_roundness_penalty = combined_size * (1 - roundness)

        position_penalty = 0.0
        if self.maintain_position:
            dx = centroid_x - self.initial_centroid_x
            dy = centroid_y - self.initial_centroid_y
            distance = np.sqrt(dx**2 + dy**2)
            img_width, img_height = self.camera_config.get('shape', [1392, 1040])
            img_diagonal = np.sqrt(img_width**2 + img_height**2)
            normalized_distance = distance / img_diagonal
            position_penalty = combined_size * normalized_distance * 100
            current_metrics['position_distance'] = distance
            current_metrics['normalized_distance'] = normalized_distance

        if self.maintain_position:
            score = 0.4 * size_score + 0.4 * non_roundness_penalty + 0.2 * position_penalty
        else:
            score = 0.5 * size_score + 0.5 * non_roundness_penalty

        metrics.update(current_metrics, score)

        return score

    def _get_average_YAG_image(self):
        """获取并平均多次YAG图像"""
        raw_images = []
        valid_count = 0

        camera_pv = self.camera_config.get('pv', 'LA-BI:PRF22:RAW:ArrayData')
        shape = self.camera_config.get('shape', [1392, 1040])

        for _ in range(self.num_averages):
            img = get_image_from_YAG(camera_pv, shape)
            if img is not None and np.any(img > 0):
                raw_images.append(img.astype(np.float32))
                valid_count += 1
                time.sleep(0.5)

        if valid_count == 0:
            return None, float('inf'), float('inf'), -1, -1, float('inf'), 0

        averaged_image = np.mean(raw_images, axis=0)
        size_x, size_y, centroid_x, centroid_y = calculate_spot_metrics(averaged_image)
        combined_size = np.sqrt(size_x**2 + size_y**2) if np.isfinite(size_x) and np.isfinite(size_y) else float('inf')
        roundness = min(size_x, size_y) / max(size_x, size_y) if max(size_x, size_y) > 0 else 0

        return raw_images[0], size_x, size_y, centroid_x, centroid_y, combined_size, roundness

    def save_results(self, history, config, results_dir='results'):
        """保存优化结果到HDF5文件

        Args:
            history: 优化历史字典
            config: 配置字典
            results_dir: 结果保存目录

        Returns:
            str: 保存的文件路径
        """
        from ..results import save_beam
        return save_beam(history, config, results_dir)


# -------------------------------------
# 束流优化高级函数
# -------------------------------------


def get_average_YAG_image(camera_pv, shape, num_reads=1):
    """获取多次YAG图像并取平均，减少抖动影响

    Args:
        camera_pv (str): 相机数据PV地址
        shape (list): 图像尺寸[宽度, 高度]
        num_reads (int): 读取次数

    Returns:
        tuple: (averaged_image, spot_size_x, spot_size_y, centroid_x, centroid_y,
                combined_size, roundness)
    """
    if num_reads <= 0:
        num_reads = 1

    raw_images = []
    valid_count = 0

    for i in range(num_reads):
        img = get_image_from_YAG(camera_pv, shape)
        if img is not None and np.any(img > 0):
            raw_images.append(img.astype(np.float32))
            valid_count += 1
            time.sleep(0.5)
        else:
            print(f"警告: 第 {i+1}/{num_reads} 次读取图像无效")

    if valid_count == 0:
        print("错误: 未捕获到有效图像")
        return None, float('inf'), float('inf'), -1, -1, float('inf'), 0

    averaged_image = np.mean(raw_images, axis=0)
    size_x, size_y, centroid_x, centroid_y = calculate_spot_metrics(averaged_image)
    combined_size = np.sqrt(size_x**2 + size_y**2) if np.isfinite(size_x) and np.isfinite(size_y) else float('inf')
    roundness = min(size_x, size_y) / max(size_x, size_y) if max(size_x, size_y) > 0 else 0

    return raw_images[0], size_x, size_y, centroid_x, centroid_y, combined_size, roundness


def objective_function(params_dict, device_pvs, config):
    """目标函数：最小化束流尺寸同时优化圆度

    Args:
        params_dict: 参数字典（Nevergrad格式）
        device_pvs: 设备PV列表
        config: 配置字典

    Returns:
        float: 评分值
    """
    from .metrics import metrics

    params = [params_dict[f"x{i}"] for i in range(len(device_pvs))]

    success = safe_device_operation(device_pvs, params, config)
    if not success:
        return float('inf')

    time.sleep(2)

    camera_config = config['camera']
    num_averages = config.get('image_processing', {}).get('num_averages', 3)
    target_diagonal_size = config.get('target_diagonal_size_pixels', 0)
    maintain_position = config.get('maintain_position', False)

    raw_image, size_x, size_y, centroid_x, centroid_y, combined_size, roundness = get_average_YAG_image(
        camera_config['pv'],
        camera_config['shape'],
        num_reads=num_averages,
    )

    objective_function.raw_image = raw_image

    if not (np.isfinite(size_x) and np.isfinite(size_y) and
            np.isfinite(centroid_x) and np.isfinite(centroid_y)):
        return float('inf')

    roundness = min(size_x, size_y) / max(size_x, size_y) if max(size_x, size_y) > 0 else 0

    current_metrics = {
        'physical_size': combined_size,
        'size_x': size_x,
        'size_y': size_y,
        'roundness': roundness,
        'params': params.copy(),
        'centroid_x': centroid_x,
        'centroid_y': centroid_y
    }

    if target_diagonal_size > 0:
        relative_error = (combined_size - target_diagonal_size) / target_diagonal_size
        size_score = relative_error ** 2
    else:
        size_score = combined_size

    non_roundness_penalty = combined_size * (1 - roundness)

    position_penalty = 0.0
    if maintain_position and hasattr(objective_function, 'initial_centroid_x'):
        dx = centroid_x - objective_function.initial_centroid_x
        dy = centroid_y - objective_function.initial_centroid_y
        distance = np.sqrt(dx**2 + dy**2)
        img_width, img_height = camera_config['shape']
        img_diagonal = np.sqrt(img_width**2 + img_height**2)
        normalized_distance = distance / img_diagonal
        position_penalty = combined_size * normalized_distance * 100
        current_metrics['position_distance'] = distance
        current_metrics['normalized_distance'] = normalized_distance

    if maintain_position:
        score = 0.4 * size_score + 0.4 * non_roundness_penalty + 0.2 * position_penalty
    else:
        score = 0.5 * size_score + 0.5 * non_roundness_penalty

    metrics.update(current_metrics, score)

    return score


def create_optimizer(algorithm_name, parametrization, budget):
    """创建优化器实例

    Args:
        algorithm_name (str): 优化算法名称
        parametrization: Nevergrad 参数化对象
        budget (int): 优化预算

    Returns:
        nevergrad.optimizer: 优化器实例
    """
    try:
        optimizer_class = ng.optimizers.registry[algorithm_name]
    except KeyError:
        print(f"算法 {algorithm_name} 未找到，使用默认 NGOpt")
        optimizer_class = ng.optimizers.NGOpt

    return optimizer_class(
        parametrization=parametrization,
        budget=budget,
        num_workers=1
    )


def optimize_beam(config, algorithm='NGOpt', budget=50, device_types=None, device_pvs=None):
    """执行束流优化

    Args:
        config (dict): 配置字典
        algorithm (str): 优化算法名称
        budget (int): 优化迭代次数
        device_types (list): 要优化的设备类型列表
        device_pvs (list): 要优化的具体设备PV列表

    Returns:
        tuple: (最佳参数, 最佳分数, 设备PV列表, 优化历史)
    """
    from .metrics import metrics

    metrics.reset()

    iteration_history = {
        'images': [],
        'parameters': [],
        'physical_sizes': [],
        'size_x': [],
        'size_y': [],
        'roundness': [],
        'scores': [],
        'centroid_x': [],
        'centroid_y': [],
        'is_best': []
    }

    device_pvs, current_values, bounds = select_optimization_devices(
        config,
        device_types,
        device_pvs,
        use_default_fallback=True
    )

    opt_config = config.get('optimization', {})
    algorithm = opt_config.get('algorithm', algorithm)
    budget = opt_config.get('budget', budget)

    parametrization = ng.p.Instrumentation(
        **{f"x{i}": ng.p.Scalar(init=current_values[i], lower=bounds[i][0], upper=bounds[i][1])
           for i in range(len(device_pvs))}
    )

    optimizer = create_optimizer(algorithm, parametrization, budget)

    optimization_history = {
        'device_pvs': device_pvs.copy(),
        'device_names': [pv.split(':')[-1] for pv in device_pvs],
        'iterations': [],
        'algorithm': algorithm,
        'budget': budget,
        'early_stop': False,
        'stop_iteration': budget
    }

    early_stop_config = opt_config.get('early_stopping', {})
    early_stop_enabled = early_stop_config.get('enabled', True)
    early_stop_patience = early_stop_config.get('patience', 10)
    min_relative_improvement = early_stop_config.get('min_relative_improvement', 0.005)
    no_improvement_count = 0

    print("\n设置初始参数（安全检查中）...")
    initial_params_dict = {f"x{i}": current_values[i] for i in range(len(current_values))}
    safe_device_operation(device_pvs, current_values, config)

    camera_config = config['camera']
    num_averages = config.get('image_processing', {}).get('num_averages', 3)
    maintain_position = config.get('maintain_position', False)

    original_images, size_x, size_y, centroid_x, centroid_y, initial_physical_size, initial_roundness = get_average_YAG_image(
        camera_config['pv'],
        camera_config['shape'],
        num_reads=num_averages,
    )

    non_roundness_penalty = initial_physical_size * (1 - initial_roundness)
    initial_score = 0.5 * initial_physical_size + 0.5 * non_roundness_penalty

    current_metrics = {
        'physical_size': initial_physical_size,
        'size_x': size_x,
        'size_y': size_y,
        'roundness': initial_roundness,
        'score': initial_score,
        'params': current_values.copy(),
        'centroid_x': centroid_x,
        'centroid_y': centroid_y
    }
    metrics.update(current_metrics, initial_score)

    if original_images is not None:
        iteration_history['images'].append(original_images.copy())
    else:
        iteration_history['images'].append(None)

    iteration_history['parameters'].append(current_values.copy())
    iteration_history['physical_sizes'].append(initial_physical_size)
    iteration_history['size_x'].append(size_x)
    iteration_history['size_y'].append(size_y)
    iteration_history['roundness'].append(initial_roundness)
    iteration_history['scores'].append(initial_score)
    iteration_history['centroid_x'].append(centroid_x)
    iteration_history['centroid_y'].append(centroid_y)
    iteration_history['is_best'].append(True)

    if maintain_position:
        objective_function.initial_centroid_x = centroid_x
        objective_function.initial_centroid_y = centroid_y
        print(f"✓ 位置维持模式激活，初始位置: ({centroid_x:.1f}, {centroid_y:.1f})")

    optimization_history['initial_physical_size'] = initial_physical_size
    optimization_history['initial_roundness'] = initial_roundness
    optimization_history['initial_score'] = initial_score

    print(f"初始束流尺寸: {initial_physical_size:.4f}, 圆度: {initial_roundness:.4f}, Score: {initial_score:.4f}")

    print(f"\n开始优化: {algorithm} 算法, {budget} 次迭代...")
    start_time = time.time()
    last_update_time = time.time()
    update_interval = 0.5
    best_score_so_far = initial_score

    for i in range(budget):
        try:
            candidate = optimizer.ask()
            value = objective_function(candidate.kwargs, device_pvs, config)

            if np.isinf(value) or np.isnan(value):
                print(f"  警告: 迭代 {i+1} 目标函数返回无效值 {value}")
                value = float('inf')

            optimizer.tell(candidate, value)

            params = [candidate.kwargs[f"x{i}"] for i in range(len(device_pvs))]
            current_metrics = metrics.get_current()

            if hasattr(objective_function, 'raw_image') and objective_function.raw_image is not None:
                iteration_history['images'].append(objective_function.raw_image.copy())
            else:
                iteration_history['images'].append(None)

            iteration_history['parameters'].append(params.copy())
            iteration_history['physical_sizes'].append(current_metrics.get('physical_size', float('inf')))
            iteration_history['size_x'].append(current_metrics.get('size_x', 0))
            iteration_history['size_y'].append(current_metrics.get('size_y', 0))
            iteration_history['roundness'].append(current_metrics.get('roundness', 0))
            iteration_history['scores'].append(value)
            iteration_history['centroid_x'].append(current_metrics.get('centroid_x', 0))
            iteration_history['centroid_y'].append(current_metrics.get('centroid_y', 0))
            iteration_history['is_best'].append(value < best_score_so_far)

            optimization_history['iterations'].append(i+1)

            if early_stop_enabled:
                relative_improvement = (best_score_so_far - value) / best_score_so_far
                if value < best_score_so_far and relative_improvement > min_relative_improvement:
                    best_score_so_far = value
                    no_improvement_count = 0
                else:
                    no_improvement_count += 1
                if no_improvement_count >= early_stop_patience:
                    print(f"\n早停触发! 连续 {early_stop_patience} 次迭代无显著改进")
                    optimization_history['early_stop'] = True
                    optimization_history['stop_iteration'] = i+1
                    break

            current_time = time.time()
            if current_time - last_update_time > update_interval or i == budget-1 or i == 0:
                elapsed = current_time - start_time
                iterations_per_second = (i+1) / elapsed if elapsed > 0 else 0
                remaining = (budget - (i+1)) / iterations_per_second if iterations_per_second > 0 else 0

                percent = 100 * ((i+1) / float(budget))
                filled_length = int(30 * (i+1) // budget)
                bar = '█' * filled_length + '-' * (30 - filled_length)

                progress_line = f"\r优化进度 |{bar}| {i+1}/{budget} [{percent:.1f}%]"
                time_line = f" 耗时: {elapsed:.1f}s, 预计剩余: {remaining:.1f}s"

                current_line = "\n当前: "
                if current_metrics:
                    physical_size = current_metrics.get('physical_size', float('inf'))
                    roundness_val = current_metrics.get('roundness', 0)
                    score = current_metrics.get('score', float('inf'))
                    position_info = ""
                    if maintain_position and 'position_distance' in current_metrics:
                        position_info = f", 位置偏移={current_metrics['position_distance']:.1f}px"
                    params_list = current_metrics.get('params', [])
                    current_line += f"尺寸={physical_size:.2f}, 圆度={roundness_val:.3f}, Score={score:.2f}{position_info}, 参数=["
                    current_line += ", ".join([f"{p:.3f}" for p in params_list[:3]]) + (", ..." if len(params_list) > 3 else "")
                    current_line += "]"

                best_metrics = metrics.get_best()
                best_line = "\n最佳: "
                if best_metrics:
                    best_physical_size = best_metrics.get('physical_size', float('inf'))
                    best_roundness_val = best_metrics.get('roundness', 0)
                    best_score_val = best_metrics.get('score', float('inf'))
                    best_params_list = best_metrics.get('params', [])
                    best_line += f"尺寸={best_physical_size:.2f}, 圆度={best_roundness_val:.3f}, Score={best_score_val:.2f}, 参数=["
                    best_line += ", ".join([f"{p:.3f}" for p in best_params_list[:3]]) + (", ..." if len(best_params_list) > 3 else "")
                    best_line += "]"

                sys.stdout.write(progress_line + time_line + current_line + best_line)
                sys.stdout.flush()
                last_update_time = current_time

        except Exception as e:
            print(f"\n错误 (迭代 {i+1}): {str(e)}")
            continue

    print("\n优化完成!")

    optimization_history['iteration_history'] = iteration_history

    try:
        recommendation = optimizer.provide_recommendation()
        best_params = [recommendation.kwargs[f"x{i}"] for i in range(len(device_pvs))]
        best_score = recommendation.loss

        valid_scores = [(i, score) for i, score in enumerate(iteration_history['scores'])
                       if not np.isinf(score) and not np.isnan(score)]
        if valid_scores:
            best_iter_idx, _ = min(valid_scores, key=lambda x: x[1])
            optimization_history['best_iteration_index'] = best_iter_idx
            optimization_history['best_physical_size'] = iteration_history['physical_sizes'][best_iter_idx]
            optimization_history['best_roundness'] = iteration_history['roundness'][best_iter_idx]
            optimization_history['best_score'] = iteration_history['scores'][best_iter_idx]
        else:
            optimization_history['best_iteration_index'] = 0
            optimization_history['best_physical_size'] = initial_physical_size
            optimization_history['best_roundness'] = initial_roundness
            optimization_history['best_score'] = initial_score

        if initial_physical_size > 0 and not np.isinf(initial_physical_size):
            improvement = ((initial_physical_size - optimization_history['best_physical_size']) / initial_physical_size) * 100
        else:
            improvement = 0
        optimization_history['improvement_percent'] = improvement

    except Exception as e:
        print(f"  错误 (获取推荐): {str(e)}")
        print("  回退到观察到的最佳值")
        valid_scores = [(i, score) for i, score in enumerate(iteration_history['scores'])
                       if not np.isinf(score) and not np.isnan(score)]
        if valid_scores:
            best_iter_idx, best_score = min(valid_scores, key=lambda x: x[1])
            best_params = iteration_history['parameters'][best_iter_idx]
            optimization_history['best_iteration_index'] = best_iter_idx
            optimization_history['best_physical_size'] = iteration_history['physical_sizes'][best_iter_idx]
            optimization_history['best_roundness'] = iteration_history['roundness'][best_iter_idx]
            optimization_history['best_score'] = best_score
        else:
            best_params = current_values.copy()
            best_score = initial_score
            optimization_history['best_iteration_index'] = 0
            optimization_history['best_physical_size'] = initial_physical_size
            optimization_history['best_roundness'] = initial_roundness
            optimization_history['best_score'] = initial_score

    optimization_history['best_params'] = best_params.copy()
    optimization_history['best_score'] = best_score

    return best_params, best_score, device_pvs, optimization_history


def save_optimization_results(optimization_history, config, results_dir='results'):
    """使用HDF5格式保存优化结果

    Args:
        optimization_history (dict): 优化历史记录
        config (dict): 配置字典
        results_dir (str): 结果保存目录

    Returns:
        str: 结果文件路径
    """
    os.makedirs(results_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(results_dir, f"beam_optimization_{timestamp}.h5")

    try:
        import h5py
    except ImportError:
        raise ImportError("需要 h5py 库，请运行: pip install h5py")

    _save_hdf5_results(filename, optimization_history, config)
    return filename


def _save_hdf5_results(filename, optimization_history, config):
    """使用HDF5格式保存结果"""
    import h5py

    with h5py.File(filename, 'w') as f:
        metadata = f.create_group('metadata')
        metadata.attrs['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
        metadata.attrs['algorithm'] = optimization_history.get('algorithm', 'Unknown')
        metadata.attrs['budget'] = optimization_history.get('budget', 0)
        metadata.attrs['early_stop'] = optimization_history.get('early_stop', False)
        metadata.attrs['stop_iteration'] = optimization_history.get('stop_iteration', optimization_history.get('budget', 0))
        metadata.attrs['best_iteration_index'] = optimization_history.get('best_iteration_index', 0)

        device_pvs = optimization_history['device_pvs']
        metadata.create_dataset('device_pvs', data=np.array(device_pvs, dtype='S'))
        metadata.create_dataset('device_names', data=np.array(
            optimization_history.get('device_names', [pv.split(':')[-1] for pv in device_pvs]),
            dtype='S'
        ))

        config_group = f.create_group('config')
        if 'camera' in config:
            config_group.attrs['camera_pv'] = config['camera'].get('pv', '')
            config_group.attrs['gain_pv'] = config['camera'].get('gain_pv', '')
            config_group.attrs['image_shape_width'] = config['camera'].get('shape', [1392, 1040])[0]
            config_group.attrs['image_shape_height'] = config['camera'].get('shape', [1392, 1040])[1]

        summary = f.create_group('summary')
        summary.attrs['initial_physical_size'] = optimization_history.get('initial_physical_size', 0)
        summary.attrs['best_physical_size'] = optimization_history.get('best_physical_size', 0)
        summary.attrs['improvement_percent'] = optimization_history.get('improvement_percent', 0)
        summary.attrs['initial_roundness'] = optimization_history.get('initial_roundness', 0)
        summary.attrs['best_roundness'] = optimization_history.get('best_roundness', 0)

        iterations = f.create_group('iterations')
        iter_history = optimization_history['iteration_history']
        total_iterations = len(iter_history['scores'])

        for i in range(total_iterations):
            iter_num = i + 1
            iter_group = iterations.create_group(f'iter_{iter_num}')

            if iter_history['images'][i] is not None:
                img = iter_history['images'][i]
                if img.dtype != np.uint16:
                    img = img.astype(np.uint16)
                iter_group.create_dataset('image', data=img,
                                        compression="gzip", compression_opts=6,
                                        chunks=(img.shape[0], img.shape[1]))

            params = np.array(iter_history['parameters'][i], dtype=np.float32)
            iter_group.create_dataset('parameters', data=params)

            iter_group.attrs['physical_size'] = float(iter_history['physical_sizes'][i])
            iter_group.attrs['size_x'] = float(iter_history['size_x'][i])
            iter_group.attrs['size_y'] = float(iter_history['size_y'][i])
            iter_group.attrs['roundness'] = float(iter_history['roundness'][i])
            iter_group.attrs['score'] = float(iter_history['scores'][i])
            iter_group.attrs['centroid_x'] = float(iter_history['centroid_x'][i])
            iter_group.attrs['centroid_y'] = float(iter_history['centroid_y'][i])
            iter_group.attrs['is_best'] = bool(iter_history['is_best'][i])

        convergence = f.create_group('convergence')
        convergence.create_dataset('iterations', data=np.array(optimization_history['iterations'], dtype=np.int32))
        convergence.create_dataset('scores', data=np.array(iter_history['scores'], dtype=np.float32))
        convergence.create_dataset('physical_sizes', data=np.array(iter_history['physical_sizes'], dtype=np.float32))

        print(f"✓ 优化结果已保存至: {filename}")
        print(f"  总迭代次数: {total_iterations}, 最佳迭代: {optimization_history.get('best_iteration_index', 0) + 1}")


def print_config_summary(config):
    """打印配置摘要

    Args:
        config (dict): 配置字典
    """
    print("=== Beam Optimization Configuration ===")
    if 'camera' in config:
        print(f"Camera: {config['camera'].get('pv', 'N/A')}")
    print("Available devices:")
    total_devices = 0
    if 'devices' in config:
        for device_type, devices in config['devices'].items():
            print(f"  {device_type}: {len(devices)} devices")
            total_devices += len(devices)
    print(f"Total available devices: {total_devices}")
    print("=====================")


def confirm_apply_optimization(best_params, device_pvs, original_params):
    """询问用户是否应用优化结果

    Args:
        best_params: 优化后的最佳参数
        device_pvs: 设备PV列表
        original_params: 优化前的原始参数

    Returns:
        bool: True表示应用优化结果，False表示恢复原始参数
    """
    print("\n" + "="*50)
    print("优化已完成! 请选择下一步操作:")
    print("="*50)

    print("\n参数变化摘要:")
    print("-"*40)
    for i, pv in enumerate(device_pvs):
        change = best_params[i] - original_params[i]
        change_sign = "+" if change >= 0 else ""
        print(f"  {pv}: {original_params[i]:.4f} -> {best_params[i]:.4f} ({change_sign}{change:.4f})")
    print("-"*40)

    while True:
        try:
            choice = input("\n请选择操作:\n"
                          "1. 应用优化结果 (推荐)\n"
                          "2. 恢复原始参数\n"
                          "3. 查看详细参数再决定\n"
                          "请输入 (1/2/3): ").strip()

            if choice == '1':
                print("\n✓ 将应用优化结果到设备")
                return True
            elif choice == '2':
                print("\n✓ 将恢复原始参数")
                return False
            elif choice == '3':
                print("\n详细参数对比:")
                print("-"*60)
                print(f"{'设备PV':<25} {'原始值':<10} {'优化值':<10} {'变化':<10}")
                print("-"*60)
                for i, pv in enumerate(device_pvs):
                    change = best_params[i] - original_params[i]
                    change_sign = "+" if change >= 0 else ""
                    print(f"{pv:<25} {original_params[i]:<10.4f} {best_params[i]:<10.4f} {change_sign}{change:.4f}")
                print("-"*60)
            else:
                print("  无效输入，请输入 1, 2 或 3")
        except KeyboardInterrupt:
            print("\n\n用户中断操作，将恢复原始参数")
            return False
        except Exception as e:
            print(f"  输入错误: {e}，请重新输入")
