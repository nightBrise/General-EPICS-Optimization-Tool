"""核心工具函数模块

提供配置加载、设备操作、图像处理等通用功能。
"""
import numpy as np
import time
# 使用统一的 EPICS 后端选择器（支持运行时切换模拟器/真实 EPICS）
from .epics_backend import caget, caput, caget_many, caput_many


def load_config(config_file='config.json'):
    """加载配置文件

    Args:
        config_file (str): 配置文件路径

    Returns:
        dict: 配置字典
    """
    import json
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载配置文件 {config_file} 失败: {e}")
        raise


def validate_optimization_config(config, objective_type):
    """验证优化配置是否正确

    Args:
        config: 配置字典
        objective_type: 目标类型 (beam_size, orbit, orbit_zero, orbit_ref)

    Returns:
        list: 警告信息列表（空表示无问题）
    """
    warnings = []

    # 检查 budget
    budget = config.get('optimization', {}).get('budget')
    if not budget:
        warnings.append("未设置 budget，将使用默认值 50")

    # 检查设备
    devices = config.get('devices', {})
    if not devices:
        warnings.append("未配置任何控制设备")

    # 束流优化特定检查
    if objective_type == 'beam_size':
        camera = config.get('camera', {})
        if not camera.get('pv'):
            warnings.append("未配置相机 PV")
        if not camera.get('shape'):
            warnings.append("未配置图像尺寸")

    # 轨道优化特定检查
    if objective_type in ['orbit', 'orbit_zero', 'orbit_ref', 'orbit_zero']:
        bpm_pvs = config.get('bpm_pvs', [])
        if not bpm_pvs:
            warnings.append("未配置 BPM PV 列表")

    return warnings


def get_current_values(device_pvs, timeout=2.0):
    """安全获取当前设备参数值

    Args:
        device_pvs: 设备PV列表
        timeout: 单个PV读取超时时间(秒)

    Returns:
        list: 设备当前值列表
    """
    try:
        values = caget_many(device_pvs, timeout=timeout)

        if None in values:
            print("警告: 批量读取时部分PV返回None，尝试逐个重试")
            values = []
            for pv in device_pvs:
                value = None
                for attempt in range(3):
                    try:
                        value = caget(pv, timeout=timeout)
                        if value is not None:
                            break
                    except Exception:
                        pass
                    time.sleep(0.1)
                if value is None:
                    print(f"警告: {pv} 读取失败")
                values.append(value)

        return values

    except Exception as e:
        print(f"获取设备值失败: {e}")
        return [None] * len(device_pvs)


def safe_clamp_value(value, bounds):
    """安全限制值在边界内

    Args:
        value: 要限制的值
        bounds: (lower, upper)边界元组

    Returns:
        float: 限制后的值
    """
    if value is None:
        return (bounds[0] + bounds[1]) / 2

    lower, upper = bounds
    if value < lower:
        print(f"  值 {value:.4f} 低于下界 {lower:.4f}，限制为 {lower:.4f}")
        return lower
    elif value > upper:
        print(f"  值 {value:.4f} 高于上界 {upper:.4f}，限制为 {upper:.4f}")
        return upper
    return value


def safe_device_operation(pvs, values, config=None, retries=3, tolerance=1e-3):
    """安全地设置设备参数，验证设置结果

    Args:
        pvs: 设备PV列表
        values: 要设置的值列表
        config: 配置字典（可选）
        retries: 设置失败时的重试次数
        tolerance: 值验证的允许误差

    Returns:
        bool: 操作是否成功
    """
    if len(pvs) != len(values):
        print(f"错误: PV数量 ({len(pvs)}) 与值数量 ({len(values)}) 不匹配")
        return False

    values_to_use = values.copy() if isinstance(values, list) else list(values)

    # 获取设备范围
    device_ranges = _get_device_ranges(pvs, config)

    # 应用范围限制
    for i in range(len(values)):
        if i < len(device_ranges):
            bounds = device_ranges[i]
            if not (np.isinf(bounds[0]) and np.isinf(bounds[1])):
                values_to_use[i] = safe_clamp_value(values_to_use[i], bounds)

    # 设置设备参数
    for i, (pv, value) in enumerate(zip(pvs, values_to_use)):
        success = False
        bounds = device_ranges[i]

        for attempt in range(retries + 1):
            try:
                caput(pv, value, wait=True)
                time.sleep(0.1)

                readback = caget(pv)
                if readback is None:
                    print(f"警告: {pv} 设置后无法读取")
                else:
                    error = abs(readback - value)
                    if error <= tolerance:
                        success = True
                        break
                    elif (value <= bounds[0] + tolerance and readback <= bounds[0] + tolerance) or \
                         (value >= bounds[1] - tolerance and readback >= bounds[1] - tolerance):
                        success = True
                        break
                    else:
                        print(f"  警告: {pv} 设置为 {value:.4f} 但读回 {readback:.4f}")

            except Exception as e:
                print(f"  设置 {pv} 失败: {e}")

            if attempt < retries:
                wait_time = 0.3 * (attempt + 1)
                print(f"  {wait_time:.1f}秒后重试 (尝试 {attempt+1}/{retries})")
                time.sleep(wait_time)

        if not success:
            print(f"错误: {pv} 设置失败")
            if attempt > 0 and readback is not None:
                orig_value = caget(pv)
                if orig_value is not None:
                    caput(pv, orig_value, wait=True)
            return False

    # 最终验证
    print("\n验证所有参数...")
    all_verified = True
    for pv, value in zip(pvs, values_to_use):
        try:
            readback = caget(pv)
            if readback is None:
                print(f"  警告: 无法验证 {pv}")
                all_verified = False
            elif abs(readback - value) > tolerance:
                print(f"  警告: {pv} 验证失败 - 设置:{value:.4f}, 读回:{readback:.4f}")
                all_verified = False
        except Exception:
            all_verified = False

    return True


def _get_device_ranges(pvs, config):
    """获取设备参数范围"""
    device_ranges = []

    if config and 'devices' in config:
        for pv in pvs:
            found = False
            for device_type, devices in config['devices'].items():
                for device in devices:
                    if device['pv'] == pv:
                        device_ranges.append(device['range'])
                        found = True
                        break
                if found:
                    break
            if not found:
                current_val = caget(pv, timeout=1.0)
                if current_val is not None and np.abs(current_val) > 1e-6:
                    lower_bound = current_val * 0.5
                    upper_bound = current_val * 1.5
                    if lower_bound > upper_bound:
                        lower_bound, upper_bound = upper_bound, lower_bound
                    device_ranges.append([lower_bound, upper_bound])
                else:
                    device_ranges.append([-10.0, 10.0])
    else:
        for pv in pvs:
            current_val = caget(pv, timeout=1.0)
            if current_val is not None and np.abs(current_val) > 1e-6:
                lower_bound = current_val * 0.5
                upper_bound = current_val * 1.5
                if lower_bound > upper_bound:
                    lower_bound, upper_bound = upper_bound, lower_bound
                device_ranges.append([lower_bound, upper_bound])
            else:
                device_ranges.append([-10.0, 10.0])

    return device_ranges


def select_optimization_devices(config, device_types=None, device_pvs=None, use_default_fallback=True):
    """选择参与优化的设备，从EPICS获取当前值作为初始值

    Args:
        config: 配置字典
        device_types: 要选择的设备类型列表
        device_pvs: 要选择的具体设备PV列表
        use_default_fallback: 当EPICS读取失败时是否使用默认值

    Returns:
        tuple: (设备PV列表, 当前值列表, 边界列表, 设备配置列表)
    """
    selected_devices = []

    # 选择设备
    if device_pvs is not None:
        for pv in device_pvs:
            found = False
            for device_type, devices in config['devices'].items():
                for device in devices:
                    if device['pv'] == pv:
                        selected_devices.append({
                            'pv': pv,
                            'range': device['range'],
                            'base_step': device.get('base_step', 0.01)
                        })
                        found = True
                        break
                if found:
                    break
            if not found:
                print(f"警告: PV {pv} 未在配置中找到")
    elif device_types is not None:
        for device_type in device_types:
            if device_type in config['devices']:
                for device in config['devices'][device_type]:
                    selected_devices.append({
                        'pv': device['pv'],
                        'range': device['range'],
                        'base_step': device.get('base_step', 0.01)
                    })
            else:
                print(f"警告: 设备类型 {device_type} 未在配置中找到")
    else:
        for device_type, devices in config['devices'].items():
            for device in devices:
                selected_devices.append({
                    'pv': device['pv'],
                    'range': device['range'],
                    'base_step': device.get('base_step', 0.01),
                    'sensitivity': device.get('sensitivity', 1.0)
                })

    if not selected_devices:
        raise ValueError("没有选择任何设备进行优化")

    device_pvs = [d['pv'] for d in selected_devices]
    bounds = [d['range'] for d in selected_devices]
    device_configs = [{'base_step': d['base_step']}
                      for d in selected_devices]

    # 获取当前值
    print("\n从EPICS读取当前值...")
    raw_values = get_current_values(device_pvs)

    current_values = []
    for i, (pv, raw_value, bound) in enumerate(zip(device_pvs, raw_values, bounds)):
        if raw_value is None:
            if use_default_fallback:
                fallback_value = (bound[0] + bound[1]) / 2
                print(f"  警告: 无法读取 {pv}，使用默认值: {fallback_value:.4f}")
                current_values.append(fallback_value)
            else:
                raise ValueError(f"无法读取 {pv}")
        else:
            clamped_value = safe_clamp_value(raw_value, bound)
            current_values.append(clamped_value)

    # 打印结果
    print(f"\n已选择 {len(device_pvs)} 个设备进行优化:")
    for i, (pv, current_val, bound, cfg) in enumerate(zip(device_pvs, current_values, bounds, device_configs)):
        print(f"  {i+1}. {pv}: 当前值={current_val:.4f}, 范围={bound}, "
              f"步长={cfg['base_step']:.4f}")

    return device_pvs, current_values, bounds, device_configs


def get_image_from_YAG(camera_pv, shape):
    """从EPICS获取YAG晶体相机图像

    Args:
        camera_pv (str): 相机数据PV地址
        shape (list): 图像尺寸[宽度, 高度]

    Returns:
        numpy.ndarray: 二维图像数组，或None（失败时）
    """
    try:
        img_data = caget(camera_pv)
        if img_data is None or len(img_data) == 0:
            print(f"警告: {camera_pv} 返回空数据")
            return None

        img_shape = (shape[0], shape[1])
        expected_length = img_shape[0] * img_shape[1]

        if len(img_data) != expected_length:
            print(f"警告: 图像数据长度 {len(img_data)} 与预期 {expected_length} 不匹配")

        img = img_data.reshape(img_shape, order="F")
        return img
    except Exception as e:
        print(f"获取YAG图像失败: {e}")
        return None


def calculate_spot_metrics(image, return_intensity=False, return_gaussian=False):
    """计算光斑尺寸和位置 - 使用自适应降噪

    Args:
        image: 二维图像数组
        return_intensity: 是否返回光斑强度
        return_gaussian: 是否返回高斯拟合残差

    Returns:
        tuple: (size_x, size_y, centroid_x, centroid_y, intensity, gaussian_residual)
            - intensity: beam_mask区域总强度（return_intensity=True时）
            - gaussian_residual: 高斯拟合残差（return_gaussian=True时）
            - 若不需要该指标，返回 None
    """
    from scipy.ndimage import uniform_filter, gaussian_filter

    if image is None or np.all(image == 0):
        result = [float('inf'), float('inf'), -1, -1]
        result.append(None if not return_intensity else float('inf'))
        result.append(None if not return_gaussian else float('inf'))
        return tuple(result)

    try:
        # 自适应降噪
        background_pixels = np.sort(image.flatten())[:int(0.2 * image.size)]
        background_std = np.std(background_pixels)
        background_mean = np.mean(background_pixels)

        if background_std < 5:
            denoised = uniform_filter(image, size=3)
        elif background_std < 15:
            denoised = gaussian_filter(image, sigma=1.0)
        else:
            denoised = gaussian_filter(image, sigma=2.0)

        # 背景扣除
        background = np.percentile(denoised, max(5, min(20, background_std * 2)))
        background_subtracted = np.maximum(denoised - background, 0)

        # 检查信号强度
        max_val = np.max(background_subtracted)
        if max_val < background_std * 3:
            result = [float('inf'), float('inf'), -1, -1]
            result.append(None if not return_intensity else float('inf'))
            result.append(None if not return_gaussian else float('inf'))
            return tuple(result)

        # 计算半高宽阈值
        fwhm_threshold = max_val * 0.5
        beam_mask = background_subtracted > fwhm_threshold

        if np.sum(beam_mask) < 5:
            result = [float('inf'), float('inf'), -1, -1]
            result.append(None if not return_intensity else float('inf'))
            result.append(None if not return_gaussian else float('inf'))
            return tuple(result)

        # 计算尺寸
        x_proj = np.sum(beam_mask, axis=0)
        y_proj = np.sum(beam_mask, axis=1)

        x_indices = np.where(x_proj > 0)[0]
        if len(x_indices) < 2:
            result = [float('inf'), float('inf'), -1, -1]
            result.append(None if not return_intensity else float('inf'))
            result.append(None if not return_gaussian else float('inf'))
            return tuple(result)
        size_x = x_indices[-1] - x_indices[0]

        y_indices = np.where(y_proj > 0)[0]
        if len(y_indices) < 2:
            result = [float('inf'), float('inf'), -1, -1]
            result.append(None if not return_intensity else float('inf'))
            result.append(None if not return_gaussian else float('inf'))
            return tuple(result)
        size_y = y_indices[-1] - y_indices[0]

        # 计算质心
        y_coords, x_coords = np.where(beam_mask)
        centroid_x = np.mean(x_coords)
        centroid_y = np.mean(y_coords)

        result = [size_x, size_y, centroid_x, centroid_y]

        # 计算强度
        if return_intensity:
            intensity = np.sum(background_subtracted[beam_mask])
            result.append(intensity)
        else:
            result.append(None)

        # 计算高斯残差
        if return_gaussian:
            gaussian_residual = compute_gaussian_residual(
                background_subtracted, centroid_x, centroid_y, size_x, size_y
            )
            result.append(gaussian_residual)
        else:
            result.append(None)

        return tuple(result)

    except Exception as e:
        print(f"计算光斑指标失败: {e}")
        result = [float('inf'), float('inf'), -1, -1]
        result.append(None if not return_intensity else float('inf'))
        result.append(None if not return_gaussian else float('inf'))
        return tuple(result)


def compute_gaussian_residual(image, centroid_x, centroid_y, size_x, size_y):
    """计算2D高斯拟合残差

    Args:
        image: 背景扣除后的图像数组
        centroid_x: 光斑质心X
        centroid_y: 光斑质心Y
        size_x: 光斑X方向尺寸
        size_y: 光斑Y方向尺寸

    Returns:
        float: 归一化残差 (sum((fitted - actual)²) / n)，越小表示越符合高斯分布
    """
    from scipy.optimize import curve_fit

    if centroid_x < 0 or centroid_y < 0:
        return float('inf')

    try:
        # 定义2D高斯函数
        def gaussian_2d(coords, amplitude, x0, y0, sigma_x, sigma_y, offset):
            x, y = coords
            return offset + amplitude * np.exp(
                -((x - x0)**2 / (2 * sigma_x**2) + (y - y0)**2 / (2 * sigma_y**2))
            )

        # 确定拟合区域（光斑周围3倍尺寸范围）
        margin = max(size_x, size_y) * 2
        x_min = max(0, int(centroid_x - margin))
        x_max = min(image.shape[1], int(centroid_x + margin))
        y_min = max(0, int(centroid_y - margin))
        y_max = min(image.shape[0], int(centroid_y + margin))

        if x_max <= x_min or y_max <= y_min:
            return float('inf')

        # 提取拟合区域
        region = image[y_min:y_max, x_min:x_max]
        y_indices, x_indices = np.indices(region.shape)

        # 初始参数估计
        amplitude = np.max(region)
        offset = np.percentile(region, 10)
        sigma_x = max(1, size_x / 3)
        sigma_y = max(1, size_y / 3)

        # 拟合
        try:
            popt, _ = curve_fit(
                gaussian_2d,
                (x_indices.flatten(), y_indices.flatten()),
                region.flatten(),
                p0=[amplitude, centroid_x - x_min, centroid_y - y_min, sigma_x, sigma_y, offset],
                maxfev=1000
            )

            # 计算残差
            fitted = gaussian_2d((x_indices, y_indices), *popt)
            residual = np.sum((fitted - region)**2) / region.size
            # 归一化残差
            normalized_residual = residual / (amplitude**2 + 1e-10)

            return normalized_residual

        except Exception:
            return float('inf')

    except Exception as e:
        print(f"计算高斯残差失败: {e}")
        return float('inf')


def wait_for_all_devices_settled(device_pvs, target_values, tolerance=0.0001, max_wait=10, poll_interval=0.2):
    """等待所有设备达到设定值

    Args:
        device_pvs: 设备PV列表（包括所有写入元件）
        target_values: 目标值列表
        tolerance: 允许的偏差（默认0.0001）
        max_wait: 最大等待时间（秒，默认10）
        poll_interval: 轮询间隔（秒，默认0.2）

    Returns:
        tuple: (是否全部成功, {pv: {target, current, deviation}} 字典)
    """
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > max_wait:
            readbacks = caget_many(device_pvs)
            failed = {}
            for pv, target, readback in zip(device_pvs, target_values, readbacks):
                if readback is None or abs(readback - target) > tolerance:
                    failed[pv] = {
                        'target': target,
                        'current': readback,
                        'deviation': abs(readback - target) if readback is not None else None
                    }
            return False, failed

        readbacks = caget_many(device_pvs)
        all_settled = True
        deviations = {}

        for pv, target, readback in zip(device_pvs, target_values, readbacks):
            if readback is None:
                all_settled = False
                deviations[pv] = None
                continue
            dev = abs(readback - target)
            deviations[pv] = dev
            if dev > tolerance:
                all_settled = False

        if all_settled:
            return True, deviations

        time.sleep(poll_interval)
