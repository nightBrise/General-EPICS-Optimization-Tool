"""优化结果保存与加载模块

提供统一的接口保存和加载束流优化、轨道优化的结果到HDF5文件。
"""
import os
import time
import numpy as np
import h5py


def save_beam(history, config, results_dir='results'):
    """保存束流优化结果到HDF5文件

    Args:
        history: 优化历史字典
        config: 配置字典
        results_dir: 结果保存目录

    Returns:
        str: 保存的文件路径
    """
    os.makedirs(results_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(results_dir, f"beam_{timestamp}.h5")

    with h5py.File(filename, 'w') as f:
        # ========== metadata ==========
        metadata = f.create_group('metadata')
        metadata.attrs['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
        metadata.attrs['algorithm'] = history.get('algorithm', 'Unknown')
        metadata.attrs['budget'] = history.get('budget', 0)
        metadata.attrs['early_stop'] = history.get('early_stop', False)
        metadata.attrs['stop_iteration'] = history.get('stop_iteration', history.get('budget', 0))
        metadata.attrs['best_iteration_index'] = history.get('best_iteration_index', 0)

        # ========== devices ==========
        devices = f.create_group('devices')
        device_pvs = history.get('device_pvs', [])

        devices.create_dataset('all_device_pvs', data=np.array(device_pvs, dtype='S'))
        # device_names 在加载时统一从 device_pvs 提取，保存时只存 PV

        # ========== config ==========
        cfg = f.create_group('config')
        camera_config = config.get('camera', {})
        cfg.attrs['camera_pv'] = camera_config.get('pv', '')
        shape = camera_config.get('shape', [1392, 1040])
        cfg.attrs['image_width'] = shape[0]
        cfg.attrs['image_height'] = shape[1]
        objective_params = config.get('objective', {}).get('params', {})
        cfg.attrs['num_averages'] = objective_params.get('num_averages', 3)

        # ========== initial ==========
        initial = f.create_group('initial')
        iter_history = history.get('iteration_history', {})
        initial.attrs['score'] = history.get('initial_score', float('inf'))
        initial.attrs['physical_size'] = iter_history.get('physical_sizes', [float('inf')])[0]
        initial.attrs['size_x'] = iter_history.get('size_x', [0])[0]
        initial.attrs['size_y'] = iter_history.get('size_y', [0])[0]
        initial.attrs['roundness'] = iter_history.get('roundness', [0])[0]
        initial.attrs['centroid_x'] = iter_history.get('centroid_x', [0])[0]
        initial.attrs['centroid_y'] = iter_history.get('centroid_y', [0])[0]

        # ========== best ==========
        best = f.create_group('best')
        best.attrs['score'] = history.get('best_score', float('inf'))
        best.attrs['iteration'] = history.get('best_iteration_index', 0)
        best.attrs['physical_size'] = history.get('best_physical_size', 0)
        best.attrs['roundness'] = history.get('best_roundness', 0)
        best.attrs['size_x'] = iter_history.get('size_x', [0])[history.get('best_iteration_index', 0)]
        best.attrs['size_y'] = iter_history.get('size_y', [0])[history.get('best_iteration_index', 0)]
        best.attrs['centroid_x'] = iter_history.get('centroid_x', [0])[history.get('best_iteration_index', 0)]
        best.attrs['centroid_y'] = iter_history.get('centroid_y', [0])[history.get('best_iteration_index', 0)]
        best_params = history.get('best_params', [])
        best.create_dataset('params', data=np.array(best_params, dtype=np.float32))

        # ========== convergence ==========
        convergence = f.create_group('convergence')
        iterations = history.get('iterations', list(range(len(iter_history.get('scores', [])))))
        convergence.create_dataset('iterations', data=np.array(iterations, dtype=np.int32))
        convergence.create_dataset('scores', data=np.array(iter_history.get('scores', []), dtype=np.float32))
        convergence.create_dataset('physical_sizes', data=np.array(iter_history.get('physical_sizes', []), dtype=np.float32))

        # ========== iterations ==========
        iterations_group = f.create_group('iterations')

        # 获取各历史数据列表，添加边界保护
        scores_list = iter_history.get('scores', [])
        physical_sizes_list = iter_history.get('physical_sizes', [])
        size_x_list = iter_history.get('size_x', [])
        size_y_list = iter_history.get('size_y', [])
        roundness_list = iter_history.get('roundness', [])
        centroid_x_list = iter_history.get('centroid_x', [])
        centroid_y_list = iter_history.get('centroid_y', [])
        params_list = iter_history.get('parameters', [])
        images_list = iter_history.get('images', [])
        is_best_list = iter_history.get('is_best', [])

        total_iters = len(scores_list)

        for i in range(total_iters):
            iter_group = iterations_group.create_group(f'iter_{i+1}')

            # params
            params = params_list[i] if i < len(params_list) else []
            if params:
                iter_group.create_dataset('params', data=np.array(params, dtype=np.float32))

            iter_group.attrs['score'] = scores_list[i] if i < len(scores_list) else float('inf')
            iter_group.attrs['physical_size'] = physical_sizes_list[i] if i < len(physical_sizes_list) else 0
            iter_group.attrs['size_x'] = size_x_list[i] if i < len(size_x_list) else 0
            iter_group.attrs['size_y'] = size_y_list[i] if i < len(size_y_list) else 0
            iter_group.attrs['roundness'] = roundness_list[i] if i < len(roundness_list) else 0
            iter_group.attrs['centroid_x'] = centroid_x_list[i] if i < len(centroid_x_list) else 0
            iter_group.attrs['centroid_y'] = centroid_y_list[i] if i < len(centroid_y_list) else 0
            iter_group.attrs['is_best'] = is_best_list[i] if i < len(is_best_list) else False

            # image
            if i < len(images_list) and images_list[i] is not None:
                img = images_list[i]
                if img.dtype != np.uint16:
                    img = img.astype(np.uint16)
                iter_group.create_dataset('image', data=img,
                                        compression="gzip", compression_opts=6,
                                        chunks=(img.shape[0], img.shape[1]))

    print(f"✓ 束流优化结果已保存至: {filename}")
    return filename


def save_orbit(history, config, results_dir='results', orbit_mode='zero'):
    """保存轨道优化结果到HDF5文件

    Args:
        history: 优化历史字典
        config: 配置字典
        results_dir: 结果保存目录
        orbit_mode: 'zero' 或 'ref'

    Returns:
        str: 保存的文件路径
    """
    os.makedirs(results_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(results_dir, f"orbit_{timestamp}.h5")

    with h5py.File(filename, 'w') as f:
        # ========== metadata ==========
        metadata = f.create_group('metadata')
        metadata.attrs['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
        metadata.attrs['algorithm'] = history.get('algorithm', 'Unknown')
        metadata.attrs['budget'] = history.get('budget', 0)
        metadata.attrs['early_stop'] = history.get('early_stop', False)
        metadata.attrs['stop_iteration'] = history.get('stop_iteration', history.get('budget', 0))
        metadata.attrs['orbit_mode'] = orbit_mode

        # ========== devices ==========
        devices = f.create_group('devices')
        device_pvs = history.get('device_pvs', [])
        devices.create_dataset('corrector_pvs', data=np.array(device_pvs, dtype='S'))
        # corrector_names 在加载时从 corrector_pvs 提取

        # ========== bpm ==========
        bpm_group = f.create_group('bpm')
        objective_config = config.get('objective', {})
        bpm_pvs = objective_config.get('read_pvs', config.get('bpm_pvs', []))
        bpm_group.create_dataset('bpm_pvs', data=np.array(bpm_pvs, dtype='S'))
        # bpm_names 在加载时从 bpm_pvs 提取
        bpm_group.attrs['num_bpms'] = len(bpm_pvs)

        # ========== reference_orbit ==========
        ref_orbit = f.create_group('reference_orbit')
        reference_orbit = config.get('objective', {}).get('params', {}).get('reference_orbit', {})
        if not reference_orbit:
            reference_orbit = config.get('reference_orbit', {})
        for pv, value in reference_orbit.items():
            ref_orbit.attrs[pv] = value

        # ========== initial ==========
        iter_history = history.get('iteration_history', {})
        initial = f.create_group('initial')
        initial.attrs['score'] = history.get('initial_score', float('inf'))

        # 从iteration_history提取initial数据
        if iter_history:
            initial_readings = iter_history.get('bpm_readings', [[]])[0] if iter_history.get('bpm_readings') else []
            initial_deviations = iter_history.get('deviations', [[]])[0] if iter_history.get('deviations') else []
            initial.create_dataset('bpm_readings', data=np.array(initial_readings, dtype=np.float32))
            initial.create_dataset('deviations', data=np.array(initial_deviations, dtype=np.float32))

        # ========== best ==========
        best = f.create_group('best')
        best.attrs['score'] = history.get('best_score', float('inf'))
        best.attrs['iteration'] = history.get('best_iteration_index', 0)
        best_params = history.get('best_params', [])
        best.create_dataset('params', data=np.array(best_params, dtype=np.float32))

        # best BPM readings
        best_idx = history.get('best_iteration_index', 0)
        if iter_history and best_idx < len(iter_history.get('bpm_readings', [])):
            best_readings = iter_history.get('bpm_readings', [])[best_idx]
            best_deviations = iter_history.get('deviations', [])[best_idx] if best_idx < len(iter_history.get('deviations', [])) else []
            best.create_dataset('bpm_readings', data=np.array(best_readings, dtype=np.float32))
            best.create_dataset('deviations', data=np.array(best_deviations, dtype=np.float32))

        # ========== convergence ==========
        convergence = f.create_group('convergence')
        iterations = history.get('iterations', list(range(len(iter_history.get('scores', [])))))
        convergence.create_dataset('iterations', data=np.array(iterations, dtype=np.int32))
        convergence.create_dataset('scores', data=np.array(iter_history.get('scores', []), dtype=np.float32))

        # ========== iterations ==========
        iterations_group = f.create_group('iterations')

        # 获取各历史数据列表，添加边界保护
        scores_list = iter_history.get('scores', [])
        params_list = iter_history.get('parameters', [])
        bpm_readings_list = iter_history.get('bpm_readings', [])
        ref_values_list = iter_history.get('ref_values', [])
        deviations_list = iter_history.get('deviations', [])

        total_iters = len(scores_list)

        for i in range(total_iters):
            iter_group = iterations_group.create_group(f'iter_{i+1}')

            # params
            params = params_list[i] if i < len(params_list) else []
            if params:
                iter_group.create_dataset('params', data=np.array(params, dtype=np.float32))

            iter_group.attrs['score'] = scores_list[i] if i < len(scores_list) else float('inf')

            # bpm readings for this iteration
            if i < len(bpm_readings_list) and bpm_readings_list[i]:
                iter_group.create_dataset('bpm_readings',
                    data=np.array(bpm_readings_list[i], dtype=np.float32))

            # ref values for this iteration
            if i < len(ref_values_list) and ref_values_list[i]:
                iter_group.create_dataset('ref_values',
                    data=np.array(ref_values_list[i], dtype=np.float32))

            # deviations for this iteration
            if i < len(deviations_list) and deviations_list[i]:
                iter_group.create_dataset('deviations',
                    data=np.array(deviations_list[i], dtype=np.float32))

    print(f"✓ 轨道优化结果已保存至: {filename}")
    return filename


def load_beam(filepath):
    """加载束流优化结果

    Args:
        filepath: HDF5文件路径

    Returns:
        dict: 加载的历史数据
    """
    history = {}

    with h5py.File(filepath, 'r') as f:
        # metadata
        metadata = f['metadata']
        history['algorithm'] = metadata.attrs.get('algorithm', 'Unknown')
        history['budget'] = int(metadata.attrs.get('budget', 0))
        history['early_stop'] = bool(metadata.attrs.get('early_stop', False))
        history['stop_iteration'] = int(metadata.attrs.get('stop_iteration', 0))

        # devices - device_names 从 device_pvs 统一提取
        devices = f['devices']
        history['device_pvs'] = [pv.decode() for pv in devices['all_device_pvs'][:]]
        # 设备名从 PV 的第二段提取（如 Q34, CH20, KLY1），用于绘图显示
        history['device_names'] = [pv.split(':')[1] for pv in history['device_pvs']]

        # config
        cfg = f['config']
        history['camera_pv'] = cfg.attrs.get('camera_pv', '')
        history['image_width'] = cfg.attrs.get('image_width', 1392)
        history['image_height'] = cfg.attrs.get('image_height', 1040)
        history['num_averages'] = cfg.attrs.get('num_averages', 3)

        # initial
        initial = f['initial']
        history['initial_score'] = initial.attrs.get('score', float('inf'))
        history['initial_physical_size'] = initial.attrs.get('physical_size', 0)
        history['initial_size_x'] = initial.attrs.get('size_x', 0)
        history['initial_size_y'] = initial.attrs.get('size_y', 0)
        history['initial_roundness'] = initial.attrs.get('roundness', 0)
        history['initial_centroid_x'] = initial.attrs.get('centroid_x', 0)
        history['initial_centroid_y'] = initial.attrs.get('centroid_y', 0)

        # best
        best = f['best']
        history['best_score'] = best.attrs.get('score', float('inf'))
        history['best_iteration_index'] = int(best.attrs.get('iteration', 0))
        history['best_physical_size'] = best.attrs.get('physical_size', 0)
        history['best_roundness'] = best.attrs.get('roundness', 0)
        history['best_params'] = list(best['params'][:]) if 'params' in best else []

        # convergence
        convergence = f['convergence']
        history['iterations'] = list(convergence['iterations'][:])
        history['iteration_history'] = {
            'scores': list(convergence['scores'][:]),
            'physical_sizes': list(convergence['physical_sizes'][:]) if 'physical_sizes' in convergence else [],
        }

        # iterations detail
        iterations_group = f['iterations']
        history['iteration_history']['parameters'] = []
        history['iteration_history']['size_x'] = []
        history['iteration_history']['size_y'] = []
        history['iteration_history']['roundness'] = []
        history['iteration_history']['centroid_x'] = []
        history['iteration_history']['centroid_y'] = []
        history['iteration_history']['images'] = []

        for key in sorted(iterations_group.keys(), key=lambda x: int(x.split('_')[1])):
            iter_group = iterations_group[key]
            if 'params' in iter_group:
                history['iteration_history']['parameters'].append(list(iter_group['params'][:]))
            else:
                history['iteration_history']['parameters'].append([])
            history['iteration_history']['size_x'].append(iter_group.attrs.get('size_x', 0))
            history['iteration_history']['size_y'].append(iter_group.attrs.get('size_y', 0))
            history['iteration_history']['roundness'].append(iter_group.attrs.get('roundness', 0))
            history['iteration_history']['centroid_x'].append(iter_group.attrs.get('centroid_x', 0))
            history['iteration_history']['centroid_y'].append(iter_group.attrs.get('centroid_y', 0))
            if 'image' in iter_group:
                history['iteration_history']['images'].append(iter_group['image'][:])
            else:
                history['iteration_history']['images'].append(None)

    return history


def load_orbit(filepath):
    """加载轨道优化结果

    Args:
        filepath: HDF5文件路径

    Returns:
        tuple: (history字典, orbit_mode字符串)
    """
    history = {}

    with h5py.File(filepath, 'r') as f:
        # metadata
        metadata = f['metadata']
        history['algorithm'] = metadata.attrs.get('algorithm', 'Unknown')
        history['budget'] = int(metadata.attrs.get('budget', 0))
        history['early_stop'] = bool(metadata.attrs.get('early_stop', False))
        history['stop_iteration'] = int(metadata.attrs.get('stop_iteration', 0))
        history['timestamp'] = metadata.attrs.get('timestamp', '')
        orbit_mode = metadata.attrs.get('orbit_mode', 'zero')

        # devices - device_names 从 device_pvs 统一提取
        devices = f['devices']
        history['device_pvs'] = [pv.decode() for pv in devices['corrector_pvs'][:]]
        history['device_names'] = [pv.split(':')[1] for pv in history['device_pvs']]

        # bpm - bpm_names 从 bpm_pvs 统一提取
        bpm_group = f['bpm']
        history['bpm_pvs'] = [pv.decode() for pv in bpm_group['bpm_pvs'][:]]
        history['bpm_names'] = [pv.split(':')[1] for pv in history['bpm_pvs']]
        history['num_bpms'] = bpm_group.attrs.get('num_bpms', 0)

        # reference_orbit
        ref_orbit = f['reference_orbit']
        history['reference_orbit'] = {k: ref_orbit.attrs[k] for k in ref_orbit.attrs.keys()}

        # initial
        initial = f['initial']
        history['initial_score'] = initial.attrs.get('score', float('inf'))
        if 'bpm_readings' in initial:
            history['initial_bpm_readings'] = list(initial['bpm_readings'][:])
        if 'deviations' in initial:
            history['initial_deviations'] = list(initial['deviations'][:])

        # best
        best = f['best']
        history['best_score'] = best.attrs.get('score', float('inf'))
        history['best_iteration_index'] = int(best.attrs.get('iteration', 0))
        history['best_params'] = list(best['params'][:]) if 'params' in best else []
        if 'bpm_readings' in best:
            history['best_bpm_readings'] = list(best['bpm_readings'][:])
        if 'deviations' in best:
            history['best_deviations'] = list(best['deviations'][:])

        # convergence
        convergence = f['convergence']
        history['iterations'] = list(convergence['iterations'][:])
        history['iteration_history'] = {
            'scores': list(convergence['scores'][:]),
        }

        # iterations detail
        iterations_group = f['iterations']
        history['iteration_history']['parameters'] = []
        history['iteration_history']['bpm_readings'] = []
        history['iteration_history']['ref_values'] = []
        history['iteration_history']['deviations'] = []

        for key in sorted(iterations_group.keys(), key=lambda x: int(x.split('_')[1])):
            iter_group = iterations_group[key]
            if 'params' in iter_group:
                history['iteration_history']['parameters'].append(list(iter_group['params'][:]))
            else:
                history['iteration_history']['parameters'].append([])
            if 'bpm_readings' in iter_group:
                history['iteration_history']['bpm_readings'].append(list(iter_group['bpm_readings'][:]))
            else:
                history['iteration_history']['bpm_readings'].append([])
            if 'ref_values' in iter_group:
                history['iteration_history']['ref_values'].append(list(iter_group['ref_values'][:]))
            else:
                history['iteration_history']['ref_values'].append([])
            if 'deviations' in iter_group:
                history['iteration_history']['deviations'].append(list(iter_group['deviations'][:]))
            else:
                history['iteration_history']['deviations'].append([])

    return history, orbit_mode
