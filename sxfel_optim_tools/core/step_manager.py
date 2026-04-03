"""自适应步长管理器

根据迭代阶段和收敛状态动态调整优化步长。
- 初始阶段：使用大步长探测各元件影响
- 根据历史平均法动态计算敏感度因子
- 自适应阶段转换：检测到敏感度差异后进入动态调整
"""
import numpy as np
from collections import deque


class StepManager:
    """自适应步长管理器

    根据元件对光斑的实际影响动态调整步长。
    采用历史平均法计算敏感度因子，支持自适应阶段转换。
    """

    def __init__(self, device_pvs, device_configs, ewma_alpha=0.5,
                 min_window=2, max_window=5):
        """初始化步长管理器

        Args:
            device_pvs: 设备PV列表
            device_configs: 设备配置列表（含base_step）
            ewma_alpha: 指数加权移动平均衰减因子 [0,1]，越大越重视近期
            min_window: 滑动窗口最小大小
            max_window: 滑动窗口最大大小
        """
        self.device_pvs = device_pvs
        self.base_steps = []
        self.device_sensitivity_factors = []  # 动态敏感度因子

        # EWMA 参数
        self.ewma_alpha = ewma_alpha

        # 自适应窗口参数
        self.min_window_size = min_window
        self.max_window_size = max_window
        self.current_window_size = 3

        for cfg in device_configs:
            # base_step: 基础步长
            base_step = cfg.get('base_step', 0.01)
            self.base_steps.append(base_step)
            self.device_sensitivity_factors.append(1.0)  # 默认1.0

        # 每个元件的影响历史（带方向的动态窗口）
        self.device_influence_history = {
            i: {
                'increase': deque(maxlen=self.current_window_size),
                'decrease': deque(maxlen=self.current_window_size)
            }
            for i in range(len(device_pvs))
        }

        # 步长阶段: detection -> refinement -> adjustment -> convergence
        self.phase = 'detection'

        self.iteration = 0
        self.consecutive_improvements = 0
        self.last_scores = []

    def get_adjusted_steps(self):
        """获取当前迭代的实际步长

        Returns:
            list: 每个设备的实际步长列表
        """
        factor = self._get_iteration_factor()
        return [base * factor * sens
                for base, sens in zip(self.base_steps, self.device_sensitivity_factors)]

    def _get_iteration_factor(self):
        """根据迭代阶段计算步长因子"""
        if self.phase == 'detection':
            # 初始探测阶段：使用100%步长，确保信号>噪声
            return 1.0
        elif self.phase == 'refinement':
            # 敏感度确定阶段：缩小步长细化检测
            return 0.5
        elif self.phase == 'adjustment':
            # 动态调整阶段：正常步长
            return 1.0
        elif self.phase == 'convergence':
            # 精准收敛阶段：精细搜索
            return 0.5
        return 1.0

    def record_influence(self, device_index, influence_value, param_change_direction=0):
        """记录元件影响，滑动窗口更新

        Args:
            device_index: 元件索引
            influence_value: 影响值
            param_change_direction: 参数变化方向，1=增大，-1=减小，0=无方向信息
        """
        if 0 <= device_index < len(self.device_influence_history):
            if param_change_direction == 0:
                # 无方向信息，存入 increase（向后兼容）
                self.device_influence_history[device_index]['increase'].append(influence_value)
            elif param_change_direction > 0:
                self.device_influence_history[device_index]['increase'].append(influence_value)
            else:
                self.device_influence_history[device_index]['decrease'].append(influence_value)

    def record_influence_with_direction(self, device_index, influence_value, param_change_direction):
        """记录带方向的影响值

        Args:
            device_index: 元件索引
            influence_value: 影响值大小
            param_change_direction: 1=增大, -1=减小
        """
        if 0 <= device_index < len(self.device_influence_history):
            direction = 'increase' if param_change_direction > 0 else 'decrease'
            self.device_influence_history[device_index][direction].append(influence_value)

    def _compute_cv(self):
        """计算变异系数（标准差/均值），反映敏感度差异程度

        Returns:
            float: 变异系数CV
        """
        if len(self.device_influence_history) < 2:
            return 0.0

        avg_influences = []
        for i, h in self.device_influence_history.items():
            # 使用EWMA计算平均影响
            increase_ewma = self._compute_ewma(list(h['increase']))
            decrease_ewma = self._compute_ewma(list(h['decrease']))
            avg = (increase_ewma + decrease_ewma) / 2
            avg_influences.append(avg)

        if len(avg_influences) < 2:
            return 0.0

        std_dev = np.std(avg_influences)
        mean_influence = np.mean(avg_influences)

        if mean_influence < 1e-6:
            return 0.0

        return std_dev / mean_influence

    def should_transition_to_adjustment(self):
        """判断是否应进入动态调整阶段

        Returns:
            tuple: (should_transition: bool, reason: str)
        """
        # 检查数据是否足够（每个方向至少2个数据点）
        for h in self.device_influence_history.values():
            if len(h['increase']) < 2 or len(h['decrease']) < 2:
                return False, "数据不足"

        cv = self._compute_cv()

        # 自适应调整窗口大小
        self._adapt_window_size(cv)

        if cv < 0.3:  # 低差异
            return True, f"敏感度差异小(cv={cv:.2f})，快速进入动态调整"
        elif cv > 1.0:  # 高差异
            return False, f"敏感度差异大(cv={cv:.2f})，继续细化检测"
        else:
            return False, f"中等差异(cv={cv:.2f})，继续检测"

    def _compute_ewma(self, history):
        """计算指数加权移动平均

        Args:
            history: 历史数据列表（按时间顺序）

        Returns:
            float: EWMA 值
        """
        if len(history) == 0:
            return 0.0
        ewma = history[0]
        for value in history[1:]:
            ewma = self.ewma_alpha * value + (1 - self.ewma_alpha) * ewma
        return ewma

    def _adapt_window_size(self, cv):
        """根据变异系数自适应调整窗口大小

        Args:
            cv: 当前变异系数
        """
        old_size = self.current_window_size

        if cv < 0.3:  # 低差异 -> 较小窗口足够
            self.current_window_size = max(self.min_window_size,
                                           self.current_window_size - 1)
        elif cv > 1.0:  # 高差异 -> 需要更多数据
            self.current_window_size = min(self.max_window_size,
                                           self.current_window_size + 1)

        # 如果窗口大小变化，重建历史窗口
        if self.current_window_size != old_size:
            new_history = {}
            for i, hist in self.device_influence_history.items():
                new_history[i] = {
                    'increase': deque(maxlen=self.current_window_size),
                    'decrease': deque(maxlen=self.current_window_size)
                }
                # 保留旧数据（截断到新窗口大小）
                for d in ['increase', 'decrease']:
                    new_history[i][d].extend(list(hist[d]))
            self.device_influence_history = new_history

    def compute_sensitivity_factors(self):
        """根据历史平均计算敏感度因子（使用EWMA）

        敏感元件（大影响）→ sensitivity_factor 小 → 步长小
        不敏感元件（小影响）→ sensitivity_factor 大 → 步长大
        """
        for i, history in self.device_influence_history.items():
            increase_ewma = self._compute_ewma(list(history['increase']))
            decrease_ewma = self._compute_ewma(list(history['decrease']))

            # 根据有数据的方向计算平均值
            has_increase = len(history['increase']) > 0
            has_decrease = len(history['decrease']) > 0

            if has_increase and has_decrease:
                avg = (increase_ewma + decrease_ewma) / 2
            elif has_increase:
                avg = increase_ewma
            elif has_decrease:
                avg = decrease_ewma
            else:
                avg = 0.0

            # 影响越大，敏感度因子越小
            if avg > 0:
                self.device_sensitivity_factors[i] = 1.0 / (1.0 + avg * 0.5)
            else:
                self.device_sensitivity_factors[i] = 1.0

    def set_phase(self, new_phase):
        """设置阶段

        Args:
            new_phase: 新阶段 ('detection', 'refinement', 'adjustment', 'convergence')
        """
        if new_phase != self.phase:
            print(f"  步长阶段转换: {self.phase} -> {new_phase}")
            self.phase = new_phase

    def update_phase(self, new_score):
        """根据得分变化更新步长阶段

        Args:
            new_score: 当前迭代的评分
        """
        self.iteration += 1
        self.last_scores.append(new_score)

        if len(self.last_scores) > 5:
            self.last_scores.pop(0)

        # 检测是否连续改善
        if len(self.last_scores) >= 2:
            improvements = sum(
                1 for i in range(1, len(self.last_scores))
                if self.last_scores[i] < self.last_scores[i - 1]
            )
            if improvements >= 3:
                self.consecutive_improvements += 1
            else:
                self.consecutive_improvements = 0

        # 自适应阶段转换
        if self.phase == 'detection':
            # 在detection阶段，检查是否应进入adjustment
            should_trans, reason = self.should_transition_to_adjustment()
            if should_trans:
                self.set_phase('adjustment')
            else:
                self.set_phase('refinement')
        elif self.phase == 'refinement':
            # 在refinement阶段，也检查是否应进入adjustment
            should_trans, reason = self.should_transition_to_adjustment()
            if should_trans:
                self.set_phase('adjustment')
        elif self.consecutive_improvements >= 3:
            self.set_phase('convergence')

    def adjust_device_step(self, device_index, factor):
        """根据光斑移动速度动态调整特定元件的步长

        Args:
            device_index: 元件索引
            factor: 调整因子（<1减小步长，>1增大步长）

        Returns:
            bool: 是否进行了调整
        """
        if device_index < 0 or device_index >= len(self.base_steps):
            return False

        old_step = self.base_steps[device_index]
        self.base_steps[device_index] *= factor

        # 限制步长范围 [1e-6, 1.0]
        self.base_steps[device_index] = max(1e-6, min(1.0, self.base_steps[device_index]))

        new_step = self.base_steps[device_index]
        if abs(new_step - old_step) > 1e-9:
            print(f"  步长调整: {self.device_pvs[device_index]}: "
                  f"{old_step:.6f} -> {new_step:.6f} (因子={factor})")
            return True
        return False

    def clamp_params(self, params, current_values):
        """限制参数调整幅度不超过计算出的步长

        只有当目标参数在有效范围内时，才应用步长限制。
        如果目标参数会导致超出边界，则限制在边界内。

        Args:
            params: 目标参数列表（来自优化器）
            current_values: 当前参数列表（从设备读取）

        Returns:
            list: 调整后的参数列表
        """
        adjusted = []
        steps = self.get_adjusted_steps()
        for param, current, step in zip(params, current_values, steps):
            change = param - current

            # 如果没有变化，不需要调整
            if abs(change) < 1e-9:
                adjusted.append(param)
                continue

            # 如果变化在步长范围内，直接使用目标参数
            if abs(change) <= step:
                adjusted.append(param)
                continue

            # 变化超过步长，限制调整幅度
            max_change = step
            adjusted_change = np.sign(change) * max_change
            new_value = current + adjusted_change

            adjusted.append(new_value)

        return adjusted

    def get_phase_info(self):
        """获取当前阶段信息用于调试

        Returns:
            dict: 包含阶段、迭代次数、步长因子等信息
        """
        return {
            'phase': self.phase,
            'iteration': self.iteration,
            'factor': self._get_iteration_factor(),
            'consecutive_improvements': self.consecutive_improvements,
            'steps': self.get_adjusted_steps(),
            'sensitivity_factors': self.device_sensitivity_factors,
        }

    def reset(self):
        """重置步长管理器状态"""
        self.iteration = 0
        self.consecutive_improvements = 0
        self.last_scores = []
        self.phase = 'detection'
        self.device_influence_history = {
            i: {
                'increase': deque(maxlen=self.current_window_size),
                'decrease': deque(maxlen=self.current_window_size)
            }
            for i in range(len(self.device_pvs))
        }
        self.device_sensitivity_factors = [1.0] * len(self.device_pvs)