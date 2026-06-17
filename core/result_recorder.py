"""通用优化结果记录器（HDF5）"""
import os
import time
import numpy as np
import h5py


def save_results(history: dict, config: dict, results_dir: str = 'results') -> str:
    """保存优化结果到 HDF5 文件

    Args:
        history: 优化历史（GenericOptimizer.run 的返回值）
        config: 配置字典
        results_dir: 结果保存目录

    Returns:
        str: 文件路径
    """
    os.makedirs(results_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    name = config.get('name', 'optimization')
    filename = os.path.join(results_dir, f"{name}_{timestamp}.h5")

    with h5py.File(filename, 'w') as f:
        meta = f.create_group('metadata')
        meta.attrs['name'] = config.get('name', '')
        meta.attrs['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
        meta.attrs['algorithm'] = history.get('algorithm', 'Unknown')
        meta.attrs['budget'] = history.get('budget', 0)
        meta.attrs['early_stop'] = history.get('early_stop', False)
        meta.attrs['stop_iteration'] = history.get('stop_iteration',
                                                    history.get('budget', 0))
        meta.attrs['best_iteration_index'] = history.get('best_iteration_index', 0)

        dev = f.create_group('devices')
        device_pvs = history.get('device_pvs', [])
        dev.create_dataset('pvs', data=np.array(device_pvs, dtype='S'))
        dev.attrs['count'] = len(device_pvs)

        obj = f.create_group('objectives')
        objectives_config = config.get('objectives', {})
        groups = objectives_config.get('groups', [])
        for gi, g in enumerate(groups):
            grp = obj.create_group(f'group_{gi}')
            grp.attrs['name'] = g.get('name', f'group_{gi}')
            grp.attrs['weight'] = g.get('weight', 1.0)
            pvs_in = g.get('pvs', [])
            pv_names = [item['pv'] if isinstance(item, dict) else item
                        for item in pvs_in]
            grp.create_dataset('pvs', data=np.array(pv_names, dtype='S'))

        scores = f.create_group('scores')
        scores.create_dataset('all',
            data=np.array(history.get('scores', []), dtype=np.float32))
        group_scores = history.get('group_scores', [])
        if group_scores:
            scores.create_dataset('groups',
                data=np.array(group_scores, dtype=np.float32))

        params_list = history.get('parameters', [])
        if params_list:
            f.create_dataset('parameters',
                data=np.array(params_list, dtype=np.float32))

        readings_list = history.get('readings', [])
        if readings_list:
            f.create_dataset('readings',
                data=np.array(readings_list, dtype=np.float32))

        best = f.create_group('best')
        best.attrs['score'] = history.get('best_score', float('inf'))
        best_params = history.get('best_params', [])
        if best_params:
            best.create_dataset('params',
                data=np.array(best_params, dtype=np.float32))

    print(f"✓ 结果已保存至: {filename}")
    return filename
