"""轨道目标函数模块

优化目标：使所有BPM的读数接近0或参考轨道
评分公式：score = sqrt(sum((x_i - x_ref_i)^2))
"""
import numpy as np
import time

from .base import BaseObjective
from .registry import register_objective
from .metrics import metrics
from ..epics_backend import caget_many
from ..utils import safe_device_operation


@register_objective("orbit")
class OrbitObjective(BaseObjective):
    """轨道优化目标函数

    支持两种模式：
    - 不提供 reference_orbit：优化到全0轨道
    - 提供 reference_orbit：优化到指定参考轨道
    """

    def __init__(self, config):
        """初始化轨道目标函数

        Args:
            config: 配置字典，可包含：
                - objective.read_pvs: BPM PV列表
                - objective.params.reference_orbit: 参考轨道字典（可选）
                - objective.params.repetition_rate: 束团重复频率（Hz）
                - objective.params.num_bpm_averages: BPM采样平均次数
                - objective.params.min_adjust_interval: 最小调整间隔（秒）
                - objective.params.poll_interval: 轮询间隔（秒）
                - objective.params.tolerance: 设定值容差
                - objective.params.max_wait: 最大等待时间（秒）
        """
        super().__init__(config)
        self.bpm_pvs = self.read_pvs
        self.reference_orbit = self.params.get('reference_orbit', {})

        # 参数配置
        self.repetition_rate = self.params.get('repetition_rate', 10)
        self.num_bpm_averages = self.params.get('num_bpm_averages', 5)
        self.min_adjust_interval = self.params.get('min_adjust_interval', 6)
        self.poll_interval = self.params.get('poll_interval', 0.2)
        self.tolerance = self.params.get('tolerance', 0.0001)
        self.max_wait = self.params.get('max_wait', 10)

        self._last_adjust_time = 0

    def get_score(self, params, device_pvs):
        """评估轨道偏移程度

        Args:
            params: 校正器参数列表
            device_pvs: 校正器PV列表

        Returns:
            float: 轨道偏移评分（越小越好）
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

        # 4. 获取BPM读数（多次采样平均）
        bpm_readings = self._get_bpm_readings()

        # 计算与参考轨道的偏差
        ref_values = [self.reference_orbit.get(pv, 0.0) for pv in self.bpm_pvs]
        diff = np.array(bpm_readings) - np.array(ref_values)
        score = np.sqrt(np.sum(diff**2))

        # 更新指标
        current_metrics = {
            'orbit_score': score,
            'bpm_readings': bpm_readings,
            'ref_values': ref_values,
            'deviations': diff.tolist(),
            'params': params.copy()
        }
        metrics.update(current_metrics, score)

        return score

    def _get_bpm_readings(self):
        """获取所有BPM的轨道读数（多次采样平均）"""
        if not self.bpm_pvs:
            return [0.0] * 10

        # 采样间隔 = 1/重复频率
        sample_interval = 1.0 / self.repetition_rate

        all_readings = []
        for _ in range(self.num_bpm_averages):
            readings = caget_many(self.bpm_pvs)
            all_readings.append([r if r is not None else 0.0 for r in readings])
            time.sleep(sample_interval)

        return np.mean(all_readings, axis=0).tolist()

    def save_results(self, history, config, results_dir='results'):
        """保存优化结果到HDF5文件

        Args:
            history: 优化历史字典
            config: 配置字典
            results_dir: 结果保存目录

        Returns:
            str: 保存的文件路径
        """
        from ..results import save_orbit
        # 根据是否有参考轨道决定模式
        reference_orbit = config.get('objective', {}).get('params', {}).get('reference_orbit', {})
        orbit_mode = 'ref' if reference_orbit else 'zero'
        return save_orbit(history, config, results_dir, orbit_mode=orbit_mode)


# 兼容旧名称
@register_objective("orbit_zero")
class OrbitZeroObjective(OrbitObjective):
    """轨道零点优化目标函数（兼容旧接口）"""
    pass
