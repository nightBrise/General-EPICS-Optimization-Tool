# beam_simulation_tool.py
"""EPICS模拟器模块

提供简化的EPICS PV模拟，用于无硬件测试。
支持束流图像模拟和BPM轨道模拟。
"""
import numpy as np
import time
import random
import re


class SimpleEPICSSimulator:
    """
    简化的EPICS模拟器，用于测试目的
    支持相机图像和BPM轨道模拟
    """
    def __init__(self, seed=42):
        """初始化模拟器"""
        self.random = random.Random(seed)
        np.random.seed(seed)
        self.pv_values = {}
        self._initialize_default_values()

    def _initialize_default_values(self):
        """设置默认PV值"""
        # ========== 相机参数 ==========
        # PRF22 (config_beam.json 使用)
        self.pv_values['LA-BI:PRF22:RAW:ArrayData'] = self._generate_beam_image(shape=(1040, 1392))
        self.pv_values['LA-BI:PRF22:CAM:GainRaw'] = 100
        # PRF29
        self.pv_values['LA-BI:PRF29:RAW:ArrayData'] = self._generate_beam_image(shape=(1040, 1392))
        self.pv_values['LA-BI:PRF29:CAM:GainRaw'] = 100

        # ========== 四极磁铁 Q34-Q40 (config_beam.json 使用) ==========
        for q in ['Q34', 'Q35', 'Q36', 'Q37', 'Q38', 'Q39', 'Q40']:
            self.pv_values[f'LA-PS:{q}:SETI'] = 0.0

        # ========== 校正器 (config_beam.json: CH20-22, CV20-22) ==========
        for c in ['CH20', 'CH21', 'CH22']:
            self.pv_values[f'LA-PS:{c}:SETI'] = 0.0
        for c in ['CV20', 'CV21', 'CV22']:
            self.pv_values[f'LA-PS:{c}:SETI'] = 0.0

        # ========== 校正器 (config_orbit.json: CH00-09, CV00-09) ==========
        for i in range(10):
            self.pv_values[f'LA-PS:CH{i:02d}:SETI'] = 0.0
            self.pv_values[f'LA-PS:CV{i:02d}:SETI'] = 0.0

        # ========== BPM轨道初始值（单位mm，config_orbit.json 使用） ==========
        # 格式: LA-BI:SBPM{index}:POS_X 或 POS_Y
        self._initialize_bpm_values()

        # ========== 其他设备 ==========
        self.pv_values['SUD-BI:SERV14:REBOOT'] = 0

    def _initialize_bpm_values(self):
        """初始化BPM PV值

        模拟BPM读数，根据校正器值和初始偏移计算
        """
        # 支持的BPM数量
        num_bpms = 10
        for i in range(1, num_bpms + 1):
            # 初始偏移（模拟真实束流位置）
            x_offset = self.random.uniform(-0.5, 0.5)
            y_offset = self.random.uniform(-0.5, 0.5)
            self.pv_values[f'LA-BI:SBPM{i}:POS_X'] = x_offset
            self.pv_values[f'LA-BI:SBPM{i}:POS_Y'] = y_offset
        
    def _generate_beam_image(self, shape=(1040, 1392)):
        """生成简单的高斯束流图像，使用配置中的尺寸(1040, 1392)"""
        height, width = shape
        # 随机生成光斑中心位置（在图像中心附近）
        x_center = width // 2 + np.random.randint(-width//10, width//10)
        y_center = height // 2 + np.random.randint(-height//10, height//10)

        # 限制中心位置在图像内
        x_center = np.clip(x_center, width//10, width-width//10)
        y_center = np.clip(y_center, height//10, height-height//10)

        # 随机生成光斑大小
        sigma_base = min(width, height) * np.random.uniform(0.03, 0.08)

        # 生成网格
        y, x = np.ogrid[:height, :width]

        # 生成高斯束流
        gaussian = np.exp(-0.5 * ((x - x_center)**2 + (y - y_center)**2) / sigma_base**2)
        img = gaussian * np.random.uniform(3000, 6000)  # 随机强度

        # 添加少量背景噪声
        img += np.random.normal(10, 5, shape)

        # 确保没有负值
        img = np.maximum(img, 0)

        return img

    def _update_beam_image(self, shape=(1040, 1392)):
        """根据设备参数更新束流图像，使用配置中的尺寸(1040, 1392)"""
        height, width = shape

        # 从参数中提取四极磁铁Q34-Q40的值（取平均效果）
        q_values = []
        for q in ['Q34', 'Q35', 'Q36', 'Q37', 'Q38', 'Q39', 'Q40']:
            q_values.append(self.pv_values.get(f'LA-PS:{q}:SETI', 0.0))
        q_avg = np.mean(q_values)

        # 从参数中提取校正器CH20-22, CV20-22的值
        ch_values = [self.pv_values.get(f'LA-PS:CH{c}:SETI', 0.0) for c in ['20', '21', '22']]
        cv_values = [self.pv_values.get(f'LA-PS:CV{c}:SETI', 0.0) for c in ['20', '21', '22']]
        ch_avg = np.mean(ch_values) if ch_values else 0.0
        cv_avg = np.mean(cv_values) if cv_values else 0.0

        # 计算光斑中心位置（受校正器影响）
        x_center = width // 2 + int(ch_avg * width * 0.1)  # CH影响水平位置
        y_center = height // 2 + int(cv_avg * height * 0.1)  # CV影响垂直位置

        # 限制中心位置在图像内
        margin = min(width, height) // 10
        x_center = np.clip(x_center, margin, width - margin)
        y_center = np.clip(y_center, margin, height - margin)

        # 四极磁铁影响束流尺寸
        sigma_base = min(width, height) * 0.06
        sigma_x = sigma_base * (1 - q_avg * 0.3)  # Q平均值影响水平尺寸
        sigma_y = sigma_base * (1 - q_avg * 0.3)  # Q平均值影响垂直尺寸

        # 随机光斑强度
        intensity = np.random.uniform(3000, 6000)

        # 生成网格
        y, x = np.ogrid[:height, :width]

        # 生成椭圆高斯束流
        gaussian = np.exp(-0.5 * ((x - x_center)**2 / sigma_x**2 + (y - y_center)**2 / sigma_y**2))
        img = gaussian * intensity

        # 添加少量旋转效果
        if abs(q_avg) > 0.2:
            rotation_angle = q_avg * 0.1  # 弧度
            x_rot = (x - x_center) * np.cos(rotation_angle) - (y - y_center) * np.sin(rotation_angle) + x_center
            y_rot = (x - x_center) * np.sin(rotation_angle) + (y - y_center) * np.cos(rotation_angle) + y_center
            gaussian_rot = np.exp(-0.5 * ((x_rot - x_center)**2 / sigma_x**2 + (y_rot - y_center)**2 / sigma_y**2))
            img = img * 0.7 + gaussian_rot * intensity * 0.3

        # 添加背景噪声
        img += np.random.normal(10, 5, (height, width))

        # 添加随机火花（10%概率）
        if np.random.random() < 0.1:
            spark_x = np.random.randint(margin, width-margin)
            spark_y = np.random.randint(margin, height-margin)
            spark_sigma = np.random.uniform(3, 8)
            spark_intensity = np.random.uniform(intensity * 0.5, intensity * 1.5)

            spark_gaussian = np.exp(-0.5 * ((x - spark_x)**2 + (y - spark_y)**2) / spark_sigma**2)
            img += spark_gaussian * spark_intensity

        # 确保没有负值
        img = np.maximum(img, 0)

        return img
    def caget(self, pv, timeout=1.0):
        """模拟caget函数"""
        time.sleep(0.01)  # 模拟网络延迟

        # 特殊处理图像PV（支持PRF22和PRF29）
        if pv in ('LA-BI:PRF22:RAW:ArrayData', 'LA-BI:PRF29:RAW:ArrayData'):
            # 使用配置中指定的尺寸 (1040, 1392) = (height, width)
            return self._update_beam_image(shape=(1040, 1392)).flatten('F')

        # 处理BPM PV
        if self._is_bpm_pv(pv):
            return self._get_bpm_reading(pv)

        # 模拟随机故障 (1%概率)
        if self.random.random() < 0.01:
            return None

        return self.pv_values.get(pv, 0.0)

    def _is_bpm_pv(self, pv):
        """检查是否是BPM PV"""
        # 匹配 LA-BI:SBPM{index}:POS_X 或 POS_Y 格式
        pattern = r'^LA-BI:SBPM\d+:(POS_X|POS_Y)$'
        return re.match(pattern, pv) is not None

    def _get_bpm_reading(self, pv):
        """获取BPM读数

        BPM读数由以下因素决定：
        1. 初始偏移（束流固有位置）
        2. 校正器的影（通过线性传递矩阵模拟）
        """
        # 获取初始偏移
        initial_value = self.pv_values.get(pv, 0.0)

        # 获取当前校正器值
        corrector_effect = self._calculate_corrector_effect(pv)

        # 添加噪声
        noise = self.random.uniform(-0.01, 0.01)

        return initial_value + corrector_effect + noise

    def _calculate_corrector_effect(self, pv):
        """计算校正器对BPM的影响（单位mm）

        使用简化的线性传递矩阵模型
        支持两套校正器:
        - config_orbit.json: CH00-09, CV00-09
        - config_beam.json: CH20-22, CV20-22
        """
        # 提取BPM索引和方向
        match = re.match(r'^LA-BI:SBPM(\d+):(POS_X|POS_Y)$', pv)
        bpm_index = int(match.group(1))
        direction = match.group(2)

        effect = 0.0

        # 获取所有校正器值
        corrector_pvs = []

        # CH00-09, CV00-09 (config_orbit.json)
        for ci in range(10):
            corrector_pvs.append((f'LA-PS:CH{ci:02d}:SETI', 'H', ci))
            corrector_pvs.append((f'LA-PS:CV{ci:02d}:SETI', 'V', ci))

        # CH20-22, CV20-22 (config_beam.json)
        for ci in ['20', '21', '22']:
            corrector_pvs.append((f'LA-PS:CH{ci}:SETI', 'H', int(ci)))
            corrector_pvs.append((f'LA-PS:CV{ci}:SETI', 'V', int(ci)))

        for corrector_pv, corrector_type, corrector_index in corrector_pvs:
            corrector_value = self.pv_values.get(corrector_pv, 0.0)

            # 简化的传递矩阵：校正器到BPM的影响
            # 距离越远，影响越小
            # 这里使用一个简化的线性模型
            distance_factor = 1.0 / (abs(bpm_index - corrector_index) + 1)

            if corrector_type == 'H' and direction == 'POS_X':
                # 水平校正器主要影响X方向
                effect += corrector_value * distance_factor * 0.5
            elif corrector_type == 'V' and direction == 'POS_Y':
                # 垂直校正器主要影响Y方向
                effect += corrector_value * distance_factor * 0.5

        return effect
    
    def caput(self, pv, value, wait=False, timeout=1.0):
        """模拟caput函数"""
        time.sleep(0.01)  # 模拟网络延迟

        # BPM PV是只读的，不能设置
        if self._is_bpm_pv(pv):
            print(f"警告: BPM PV {pv} 是只读的")
            return False

        # 简单的边界限制
        quadrupoles = ['Q34', 'Q35', 'Q36', 'Q37', 'Q38', 'Q39', 'Q40']
        if any(q in pv for q in quadrupoles):
            value = np.clip(value, -1.0, 1.0)
        elif ':CH' in pv or ':CV' in pv:
            # 通用校正器限制 (CH20-22, CV20-22)
            value = np.clip(value, -0.5, 0.5)

        # 处理相机重启
        if pv == 'SUD-BI:SERV14:REBOOT' and value == 1:
            time.sleep(0.3)  # 模拟重启时间
            self.pv_values[pv] = 0
            return True

        self.pv_values[pv] = value

        if wait:
            time.sleep(0.1)

        return True
        
    def caget_many(self, pvs, timeout=1.0):
        """批量获取PV值"""
        return [self.caget(pv, timeout) for pv in pvs]
        
    def caput_many(self, pvs, values, wait=False, timeout=1.0):
        """批量设置PV值"""
        for pv, value in zip(pvs, values):
            self.caput(pv, value, wait=False, timeout=timeout)
        if wait:
            time.sleep(0.1 * len(pvs))
        return True

# 创建全局模拟器实例
_simulator = SimpleEPICSSimulator()

# 导出与真实EPICS API兼容的函数
def caget(pv, timeout=1.0):
    return _simulator.caget(pv, timeout)
    
def caput(pv, value, wait=False, timeout=1.0):
    return _simulator.caput(pv, value, wait, timeout)
    
def caget_many(pvs, timeout=1.0):
    return _simulator.caget_many(pvs, timeout)
    
def caput_many(pvs, values, wait=False, timeout=1.0):
    return _simulator.caput_many(pvs, values, wait, timeout)

def test_simulation():
    """简单的测试函数"""
    print("=== 测试简化版EPICS模拟器 ===")
    print("配置: 10个BPM (SBPM1-SBPM10), 10对校正器 (CH00-C09, CV00-CV09)")

    # 测试校正器初始化
    print("\n1. 测试校正器初始化:")
    test_correctors = ['LA-PS:CH00:SETI', 'LA-PS:CV00:SETI',
                       'LA-PS:CH05:SETI', 'LA-PS:CV05:SETI',
                       'LA-PS:CH09:SETI', 'LA-PS:CV09:SETI']
    for pv in test_correctors:
        value = caget(pv)
        print(f"  {pv}: {value:.4f}")

    # 测试BPM读取
    print("\n2. 测试BPM轨道读取:")
    bpm_pvs = [f'LA-BI:SBPM{i}:POS_X' for i in range(1, 11)]
    bpm_values_x = caget_many(bpm_pvs)
    for pv, val in zip(bpm_pvs, bpm_values_x):
        print(f"  {pv}: {val:.4f}")

    # 测试校正器对BPM的影响
    print("\n3. 测试校正器对BPM的影响:")
    print("  设置CH00=0.5, CV00=0.3, CH05=0.2, CV05=-0.1")
    caput('LA-PS:CH00:SETI', 0.5)
    caput('LA-PS:CV00:SETI', 0.3)
    caput('LA-PS:CH05:SETI', 0.2)
    caput('LA-PS:CV05:SETI', -0.1)

    bpm_pvs_x = [f'LA-BI:SBPM{i}:POS_X' for i in range(1, 11)]
    bpm_pvs_y = [f'LA-BI:SBPM{i}:POS_Y' for i in range(1, 11)]
    bpm_values_x = caget_many(bpm_pvs_x)
    bpm_values_y = caget_many(bpm_pvs_y)

    print("  BPM X读数:")
    for pv, val in zip(bpm_pvs_x, bpm_values_x):
        print(f"    {pv}: {val:.4f}")
    print("  BPM Y读数:")
    for pv, val in zip(bpm_pvs_y, bpm_values_y):
        print(f"    {pv}: {val:.4f}")

    # 测试图像获取
    print("\n4. 测试图像获取:")
    img = caget('LA-BI:PRF29:RAW:ArrayData')
    if img is not None:
        img_2d = img.reshape((1040, 1392), order='F')
        print(f"  图像形状: {img_2d.shape}")
        print(f"  像素值范围: [{img_2d.min():.1f}, {img_2d.max():.1f}]")
        print(f"  平均像素值: {img_2d.mean():.1f}")
    else:
        print("  无法获取图像")

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_simulation()