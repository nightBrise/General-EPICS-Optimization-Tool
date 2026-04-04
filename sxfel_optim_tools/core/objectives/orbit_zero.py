"""轨道目标函数模块

优化目标：使所有BPM的读数接近0或参考轨道
评分公式：score = RMS + α×Peak + β×Roughness + γ×Coupling + δ×Skew
"""
import numpy as np
import time

from .base import BaseObjective
from .registry import register_objective
from .metrics import metrics
from ..epics_backend import caget_many
from ..utils import safe_device_operation


# 模式权重配置
MODE_WEIGHTS = {
    'smooth':     {'alpha': 0.2, 'beta': 0.4, 'gamma': 0.2, 'delta': 0.2},  # 强平滑
    'balanced':   {'alpha': 0.3, 'beta': 0.2, 'gamma': 0.1, 'delta': 0.1},  # 平衡（默认）
    'aggressive': {'alpha': 0.5, 'beta': 0.0, 'gamma': 0.0, 'delta': 0.0},  # 极简
}


@register_objective("orbit")
class OrbitObjective(BaseObjective):
    """轨道优化目标函数

    支持两种模式：
    - 不提供 reference_orbit：优化到全0轨道
    - 提供 reference_orbit：优化到指定参考轨道

    评分公式：
    score = RMS + α×Peak + β×Roughness + γ×Coupling + δ×Skew

    分量说明：
    - RMS: 整体偏差均方根
    - Peak: 最大偏差
    - Roughness: 轨道空间平滑性
    - Coupling: XY耦合度
    - Skew: 轨道倾斜度
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
        # 保存初始值用于回滚（首次调用时）
        if not self._params_saved:
            from ..utils import get_current_values
            self._initial_device_pvs = device_pvs.copy()
            self._initial_device_values = get_current_values(device_pvs)
            self._params_saved = True

        try:
            # 1. 安全设置设备参数
            success = safe_device_operation(device_pvs, params, self.config, tolerance=self.tolerance)
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

            # 5. 计算增强评分
            score = self._compute_enhanced_score(bpm_readings)

            # 更新指标
            current_metrics = {
                'orbit_score': score,
                'bpm_readings': bpm_readings,
                'params': params.copy()
            }
            metrics.update(current_metrics, score)

            return score

        except KeyboardInterrupt:
            self.rollback_to_initial()
            raise

    def _compute_enhanced_score(self, bpm_readings):
        """计算增强评分

        score = RMS + α×Peak + β×Roughness + γ×Coupling + δ×Skew

        Args:
            bpm_readings: BPM读数列表

        Returns:
            float: 增强评分
        """
        ref_values = [self.reference_orbit.get(pv, 0.0) for pv in self.bpm_pvs]
        diff = np.array(bpm_readings) - np.array(ref_values)

        # RMS：整体偏差均方根
        rms = np.sqrt(np.mean(diff**2))

        # Peak：最大偏差
        peak = np.max(np.abs(diff))

        # Roughness：相邻BPM偏差变化的标准差（空间平滑性）
        roughness = np.std(np.diff(diff)) if len(diff) > 1 else 0.0

        # Coupling：X和Y偏差的相关系数
        x_devs = diff[::2]   # X偏差
        y_devs = diff[1::2]  # Y偏差
        if len(x_devs) > 1 and len(y_devs) > 1:
            coupling = abs(np.corrcoef(x_devs, y_devs)[0, 1])
        else:
            coupling = 0.0

        # Skew：入口到出口的线性倾斜
        skew = abs(diff[-1] - diff[0]) if len(diff) > 1 else 0.0

        # 获取模式权重
        mode = self.params.get('mode', 'balanced')
        w = MODE_WEIGHTS.get(mode, MODE_WEIGHTS['balanced'])

        # 综合评分
        score = (rms
                 + w['alpha'] * peak
                 + w['beta'] * roughness
                 + w['gamma'] * coupling * rms  # coupling乘以rms归一化
                 + w['delta'] * skew)

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
