#!/usr/bin/env python3
"""优化结果交互式可视化工具

使用方法:
    python tools/plot_results.py
"""
import os
import sys
import glob
import re

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import numpy as np

from core.results import load_beam, load_orbit


def save_report(report_text, output_path):
    """保存报告文本到文件

    Args:
        report_text: 报告文本内容
        output_path: 输出文件路径

    Returns:
        str: 保存的文件路径
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"报告已保存至: {output_path}")
    return output_path


def generate_orbit_report(history, orbit_mode, filepath=None):
    """生成轨道优化结果报告 (Markdown 格式)

    Args:
        history: 加载的历史数据字典
        orbit_mode: 'zero' 或 'ref'
        filepath: 文件路径（用于提取时间戳）

    Returns:
        str: Markdown 格式的报告文本
    """
    import time

    # 提取时间戳
    timestamp = history.get('timestamp', '')
    if not timestamp and filepath:
        match = re.search(r'(\d{8}_\d{6})', filepath)
        if match:
            ts = match.group(1)
            timestamp = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"

    # 基本信息
    algorithm = history.get('algorithm', 'Unknown')
    budget = history.get('budget', 0)
    early_stop = history.get('early_stop', False)
    stop_iteration = history.get('stop_iteration', budget)

    # 初始和最优值
    initial_score = history.get('initial_score', float('inf'))
    best_score = history.get('best_score', float('inf'))
    best_idx = history.get('best_iteration_index', 0)

    # 计算 RMS 和 Peak
    # 注意: 在 zero 模式下, deviations 可能为空但 bpm_readings 有数据
    initial_devs = history.get('initial_deviations', [])
    best_devs = history.get('best_deviations', [])

    # 如果 deviations 为空但 bpm_readings 有数据，使用 bpm_readings 作为偏差
    if not initial_devs:
        initial_bpm = history.get('initial_bpm_readings', [])
        if initial_bpm:
            initial_devs = initial_bpm
    if not best_devs:
        best_bpm = history.get('best_bpm_readings', [])
        if best_bpm:
            best_devs = best_bpm

    def calc_rms(devs):
        if devs:
            return np.sqrt(np.mean(np.array(devs)**2))
        return 0.0

    def calc_peak(devs):
        if devs:
            return np.max(np.abs(np.array(devs)))
        return 0.0

    initial_rms = calc_rms(initial_devs) if initial_devs else 0.0
    best_rms = calc_rms(best_devs) if best_devs else 0.0
    initial_peak = calc_peak(initial_devs) if initial_devs else 0.0
    best_peak = calc_peak(best_devs) if best_devs else 0.0

    # 改善率计算
    def improvement_rate(initial, best):
        if initial == 0:
            return 0.0
        return (best - initial) / initial * 100

    score_imp = improvement_rate(initial_score, best_score)
    rms_imp = improvement_rate(initial_rms, best_rms)
    peak_imp = improvement_rate(initial_peak, best_peak)

    # BPM 信息
    bpm_names = history.get('bpm_names', [])
    bpm_pvs = history.get('bpm_pvs', [])
    num_bpms = history.get('num_bpms', len(bpm_names))

    # 校正器信息
    device_names = history.get('device_names', [])
    device_pvs = history.get('device_pvs', [])
    best_params = history.get('best_params', [])
    iter_history = history.get('iteration_history', {})
    params_list = iter_history.get('parameters', [])
    initial_params = params_list[0] if params_list else []

    # 总调节幅度
    total_adjustment = 0.0
    if len(initial_params) == len(best_params):
        for init_p, best_p in zip(initial_params, best_params):
            total_adjustment += abs(best_p - init_p)

    # 收敛评价
    if early_stop:
        convergence_eval = f"已早停 (在 {stop_iteration} 次迭代后)"
    elif stop_iteration < budget:
        convergence_eval = f"已早停 (在 {stop_iteration} 次迭代后)"
    elif stop_iteration >= budget * 0.9:
        convergence_eval = "未完全收敛 (使用全部预算)"
    else:
        convergence_eval = f"良好 (在 {stop_iteration}/{budget} 预算内收敛)"

    # ========== 生成 Markdown 报告 ==========
    lines = []
    lines.append("# SXFEL 轨道优化结果报告\n")

    # 任务概述
    lines.append("## 任务概述\n")
    lines.append("| 项目 | 内容 |")
    lines.append("|------|------|")
    lines.append(f"| 算法 | {algorithm} |")
    lines.append(f"| 预算 | {budget} 次迭代 |")
    lines.append(f"| 轨道模式 | {'全0模式 (zero)' if orbit_mode == 'zero' else '参考轨道模式 (ref)'} |")
    lines.append(f"| 运行时间 | {timestamp} |")
    lines.append(f"| 是否早停 | {'是' if early_stop else '否'} |\n")

    # 优化结果摘要
    lines.append("## 优化结果摘要\n")
    lines.append("| 指标 | 初始值 | 最优值 | 改善率 |")
    lines.append("|------|--------|--------|--------|")
    lines.append(f"| Score | {initial_score:.4f} | {best_score:.4f} | {score_imp:+.2f}% |")
    lines.append(f"| RMS (mm) | {initial_rms:.4f} | {best_rms:.4f} | {rms_imp:+.2f}% |")
    lines.append(f"| Peak (mm) | {initial_peak:.4f} | {best_peak:.4f} | {peak_imp:+.2f}% |\n")

    # 收敛分析
    lines.append("## 收敛分析\n")
    lines.append(f"- **实际迭代次数**: {stop_iteration} / {budget}")
    lines.append(f"- **早停原因**: {'无' if not early_stop else '见收敛评价'}")
    lines.append(f"- **最优迭代点**: 第 {best_idx + 1} 次")
    lines.append(f"- **收敛评价**: {convergence_eval}\n")

    # 轨道质量详情
    lines.append("## 轨道质量详情 (BPM 偏差)\n")
    if bpm_names and len(bpm_names) > 0:
        lines.append("| BPM 名称 | 初始偏差 (mm) | 最优偏差 (mm) | 改善率 |")
        lines.append("|----------|---------------|---------------|--------|")
        # X方向和Y方向交替的BPM
        for i, bpm_name in enumerate(bpm_names):
            if i < len(initial_devs) and i < len(best_devs):
                init_dev = abs(initial_devs[i]) if initial_devs[i] is not None else 0.0
                best_dev = abs(best_devs[i]) if best_devs[i] is not None else 0.0
                imp = improvement_rate(init_dev, best_dev)
                lines.append(f"| {bpm_name} | ±{init_dev:.4f} | ±{best_dev:.4f} | {imp:+.2f}% |")
            else:
                lines.append(f"| {bpm_name} | - | - | - |")
    else:
        lines.append("*无 BPM 数据*\n")

    # 设备调节记录
    lines.append("\n## 设备调节记录\n")
    lines.append(f"- **校正器数量**: {len(device_names)}\n")
    lines.append("| 校正器名称 | 初始值 | 最优值 | 调节幅度 |")
    lines.append("|-----------|--------|--------|----------|")
    for i, name in enumerate(device_names):
        init_p = initial_params[i] if i < len(initial_params) else 0.0
        best_p = best_params[i] if i < len(best_params) else 0.0
        adj = abs(best_p - init_p)
        lines.append(f"| {name} | {init_p:.4f} | {best_p:+.4f} | {adj:.4f} |")
    lines.append(f"\n- **总调节幅度**: {total_adjustment:.4f} mm\n")

    # 配置信息
    lines.append("## 配置信息\n")
    lines.append("### BPM 配置")
    lines.append(f"- **BPM 数量**: {num_bpms}")
    lines.append("- **BPM PVs**:")
    for pv in bpm_pvs:
        lines.append(f"  - {pv}")

    lines.append("\n### 校正器配置")
    lines.append(f"- **校正器数量**: {len(device_pvs)}")
    lines.append("- **校正器 PVs**:")
    for pv in device_pvs:
        lines.append(f"  - {pv}")

    # 页脚
    lines.append(f"\n---\n")
    lines.append(f"*报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n")

    return '\n'.join(lines)


def generate_beam_report(history):
    """生成束流优化结果报告 (Markdown 格式)

    Args:
        history: 加载的历史数据字典

    Returns:
        str: Markdown 格式的报告文本
    """
    import time

    # 基本信息
    algorithm = history.get('algorithm', 'Unknown')
    budget = history.get('budget', 0)
    early_stop = history.get('early_stop', False)
    stop_iteration = history.get('stop_iteration', budget)

    # 初始和最优值
    initial_score = history.get('initial_score', float('inf'))
    best_score = history.get('best_score', float('inf'))
    best_idx = history.get('best_iteration_index', 0)

    iter_history = history.get('iteration_history', {})
    initial_physical_size = iter_history.get('physical_sizes', [float('inf')])[0] if iter_history.get('physical_sizes') else float('inf')
    best_physical_size = history.get('best_physical_size', 0)

    initial_roundness = history.get('initial_roundness', 0)
    best_roundness = history.get('best_roundness', 0)

    # 改善率计算
    def improvement_rate(initial, best):
        if initial == 0:
            return 0.0
        return (best - initial) / initial * 100

    score_imp = improvement_rate(initial_score, best_score)
    size_imp = improvement_rate(initial_physical_size, best_physical_size)
    round_imp = improvement_rate(initial_roundness, best_roundness)

    # 设备信息
    device_names = history.get('device_names', [])
    device_pvs = history.get('device_pvs', [])
    best_params = history.get('best_params', [])
    params_list = iter_history.get('parameters', [])
    initial_params = params_list[0] if params_list else []

    # 总调节幅度
    total_adjustment = 0.0
    if len(initial_params) == len(best_params):
        for init_p, best_p in zip(initial_params, best_params):
            total_adjustment += abs(best_p - init_p)

    # 收敛评价
    if early_stop:
        convergence_eval = f"已早停 (在 {stop_iteration} 次迭代后)"
    elif stop_iteration < budget:
        convergence_eval = f"已早停 (在 {stop_iteration} 次迭代后)"
    elif stop_iteration >= budget * 0.9:
        convergence_eval = "未完全收敛 (使用全部预算)"
    else:
        convergence_eval = f"良好 (在 {stop_iteration}/{budget} 预算内收敛)"

    # ========== 生成 Markdown 报告 ==========
    lines = []
    lines.append("# SXFEL 束流优化结果报告\n")

    # 任务概述
    lines.append("## 任务概述\n")
    lines.append("| 项目 | 内容 |")
    lines.append("|------|------|")
    lines.append(f"| 算法 | {algorithm} |")
    lines.append(f"| 预算 | {budget} 次迭代 |")
    lines.append(f"| 是否早停 | {'是' if early_stop else '否'} |\n")

    # 优化结果摘要
    lines.append("## 优化结果摘要\n")
    lines.append("| 指标 | 初始值 | 最优值 | 改善率 |")
    lines.append("|------|--------|--------|--------|")
    lines.append(f"| Score | {initial_score:.4f} | {best_score:.4f} | {score_imp:+.2f}% |")
    lines.append(f"| 束斑尺寸 (pixels) | {initial_physical_size:.2f} | {best_physical_size:.2f} | {size_imp:+.2f}% |")
    lines.append(f"| 圆度 | {initial_roundness:.4f} | {best_roundness:.4f} | {round_imp:+.2f}% |\n")

    # 收敛分析
    lines.append("## 收敛分析\n")
    lines.append(f"- **实际迭代次数**: {stop_iteration} / {budget}")
    lines.append(f"- **早停原因**: {'无' if not early_stop else '见收敛评价'}")
    lines.append(f"- **最优迭代点**: 第 {best_idx + 1} 次")
    lines.append(f"- **收敛评价**: {convergence_eval}\n")

    # 配置信息
    lines.append("## 配置信息\n")
    lines.append("### 相机配置")
    lines.append(f"- **Camera PV**: {history.get('camera_pv', 'N/A')}")
    lines.append(f"- **图像尺寸**: {history.get('image_width', 1392)} x {history.get('image_height', 1040)}")
    lines.append(f"- **平均次数**: {history.get('num_averages', 3)}\n")

    # 设备调节记录
    lines.append("### 设备调节记录\n")
    lines.append(f"- **设备数量**: {len(device_names)}\n")
    lines.append("| 设备名称 | 初始值 | 最优值 | 调节幅度 |")
    lines.append("|---------|--------|--------|----------|")
    for i, name in enumerate(device_names):
        init_p = initial_params[i] if i < len(initial_params) else 0.0
        best_p = best_params[i] if i < len(best_params) else 0.0
        adj = abs(best_p - init_p)
        lines.append(f"| {name} | {init_p:.4f} | {best_p:+.4f} | {adj:.4f} |")
    lines.append(f"\n- **总调节幅度**: {total_adjustment:.4f}\n")

    # 页脚
    lines.append(f"---\n")
    lines.append(f"*报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n")

    return '\n'.join(lines)


def scan_results(results_dir='results'):
    """扫描results目录，返回分类的结果文件列表

    Returns:
        tuple: (beam_files, orbit_files)
    """
    os.makedirs(results_dir, exist_ok=True)

    beam_files = sorted(glob.glob(os.path.join(results_dir, 'beam_*.h5')))
    orbit_files = sorted(glob.glob(os.path.join(results_dir, 'orbit_*.h5')))

    return beam_files, orbit_files


def select_optimization_type():
    """让用户选择优化类型"""
    print("\n请选择优化类型：")
    print("  1. 束流优化 (beam)")
    print("  2. 轨道优化 (orbit)")

    while True:
        try:
            choice = input("\n请输入序号 (1/2): ").strip()
            if choice == '1':
                return 'beam'
            elif choice == '2':
                return 'orbit'
            else:
                print("无效输入，请重新输入")
        except KeyboardInterrupt:
            print("\n\n已退出")
            sys.exit(0)


def select_file(filepath_list):
    """让用户从文件列表中选择一个文件

    Args:
        filepath_list: 文件路径列表

    Returns:
        str: 选择的文件路径
    """
    if not filepath_list:
        print("没有找到结果文件")
        return None

    print("\n可用结果文件：")
    for i, filepath in enumerate(filepath_list):
        filename = os.path.basename(filepath)
        # 提取时间戳 (格式: YYYYMMDD_HHMMSS，14位数字)
        match = re.search(r'(\d{8}_\d{6})', filename)
        if match:
            timestamp = match.group(1)
        else:
            timestamp = filename.replace('.h5', '')
        print(f"  {i+1}. {timestamp}")

    while True:
        try:
            choice = input("\n请输入序号选择文件: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(filepath_list):
                return filepath_list[idx]
            else:
                print("无效序号，请重新输入")
        except KeyboardInterrupt:
            print("\n\n已退出")
            sys.exit(0)
        except ValueError:
            print("无效输入，请输入数字")


def plot_beam_results(history, output_path=None):
    """绘制束流优化结果图表

    Args:
        history: 加载的历史数据字典
        output_path: 输出图片路径
    """
    if output_path is None:
        output_path = 'results/beam_optimization_plot.png'

    iter_history = history.get('iteration_history', {})
    scores = iter_history.get('scores', [])
    num_scores = len(scores)

    # 数据对齐：iteration_history 中的 scores 包含所有评估结果，
    # 但 size_x 等指标只在评估成功（未早停）时记录
    # 因此需要对其他数据进行截断或填充
    size_x = iter_history.get('size_x', [])
    size_y = iter_history.get('size_y', [])
    roundness = iter_history.get('roundness', [])
    centroid_x = iter_history.get('centroid_x', [])
    centroid_y = iter_history.get('centroid_y', [])
    physical_sizes = iter_history.get('physical_sizes', [])
    images = iter_history.get('images', [])

    # 确保所有列表与 scores 长度一致（用 NaN 填充缺失的）
    def pad_or_truncate(arr, target_len, fill_value=np.nan):
        if not arr:
            return [fill_value] * target_len
        if len(arr) < target_len:
            return arr + [fill_value] * (target_len - len(arr))
        return arr[:target_len]

    iterations_for_plot = range(1, num_scores + 1)

    best_idx = history.get('best_iteration_index', 0)
    best_iter = best_idx + 1 if best_idx < num_scores else 1

    # 动态调整图形大小
    num_devices = len(history.get('device_names', []))
    figsize_width = max(14, 6 + num_devices * 0.3)
    fig_height = 14

    fig = plt.figure(figsize=(figsize_width, fig_height))

    # 1. 收敛曲线
    ax1 = fig.add_subplot(2, 3, 1)
    ax1.plot(iterations_for_plot, scores, 'b-', linewidth=2)
    ax1.axvline(x=best_iter, color='r', linestyle='--', alpha=0.7, label=f'Best: iter {best_iter}')
    ax1.scatter([best_iter], [scores[best_idx] if best_idx < num_scores else scores[-1]],
                color='red', s=100, zorder=5)
    ax1.set_xlabel('Iteration')
    ax1.set_ylabel('Score')
    ax1.set_title('Convergence Curve')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 2. 束流尺寸变化
    ax2 = fig.add_subplot(2, 3, 2)
    # physical_sizes 可能比 scores 短，需要对齐
    padded_sizes = pad_or_truncate(physical_sizes, num_scores)
    valid_pairs = [(i+1, s) for i, s in enumerate(padded_sizes) if s != float('inf') and not np.isnan(s)]
    if valid_pairs:
        valid_iters, valid_sizes = zip(*valid_pairs)
        ax2.plot(valid_iters, valid_sizes, 'r-', linewidth=2, marker='s', markersize=4)
    ax2.set_xlabel('Iteration')
    ax2.set_ylabel('Beam Size (pixels)')
    ax2.set_title('Beam Size Evolution')
    ax2.grid(True, alpha=0.3)

    # 3. 尺寸分量+圆度 (双Y轴)
    ax3 = fig.add_subplot(2, 3, 3)
    padded_size_x = pad_or_truncate(size_x, num_scores)
    padded_size_y = pad_or_truncate(size_y, num_scores)
    padded_roundness = pad_or_truncate(roundness, num_scores)

    ax3.set_xlabel('Iteration')
    ax3.set_ylabel('Size (pixels)', color='blue')
    l1, = ax3.plot(iterations_for_plot, padded_size_x, 'b-', linewidth=2, label='size_x')
    l2, = ax3.plot(iterations_for_plot, padded_size_y, 'g-', linewidth=2, label='size_y')
    ax3.tick_params(axis='y', labelcolor='blue')

    ax3_twin = ax3.twinx()
    ax3_twin.set_ylabel('Roundness', color='orange')
    l3, = ax3_twin.plot(iterations_for_plot, padded_roundness, 'orange', linewidth=2, marker='o', markersize=3, label='roundness')
    ax3_twin.tick_params(axis='y', labelcolor='orange')

    ax3.set_title('Size Components & Roundness')
    ax3.legend([l1, l2, l3], ['size_x', 'size_y', 'roundness'], loc='upper right')
    ax3.grid(True, alpha=0.3)

    # 4. 质心运动轨迹
    ax4 = fig.add_subplot(2, 3, 4)
    # 使用已提取的 centroid_x, centroid_y 数据，并进行填充对齐
    padded_cx = pad_or_truncate(centroid_x, num_scores)
    padded_cy = pad_or_truncate(centroid_y, num_scores)

    # 过滤掉 NaN 值用于绘图
    valid_mask = ~(np.isnan(padded_cx) | np.isnan(padded_cy))
    valid_cx = np.array(padded_cx)[valid_mask]
    valid_cy = np.array(padded_cy)[valid_mask]

    if len(valid_cx) > 0 and len(valid_cy) > 0 and len(valid_cx) == len(valid_cy):
        # 颜色渐变：冷色到暖色表示迭代顺序
        scatter = ax4.scatter(valid_cx, valid_cy, c=range(len(valid_cx)),
                            cmap='viridis', s=50, zorder=3)
        # 添加颜色条表示迭代顺序
        plt.colorbar(scatter, ax=ax4, label='Iteration')

        # 设置相等的坐标范围和比例尺
        all_coords = np.concatenate([valid_cx, valid_cy])
        data_min = np.min(all_coords)
        data_max = np.max(all_coords)
        margin = (data_max - data_min) * 0.1
        ax4.set_xlim(data_min - margin, data_max + margin)
        ax4.set_ylim(data_min - margin, data_max + margin)

    ax4.set_xlabel('Centroid X')
    ax4.set_ylabel('Centroid Y')
    ax4.set_title('Centroid Trajectory')
    ax4.grid(True, alpha=0.3)
    ax4.set_aspect('equal', adjustable='box')

    # 5. 校正器参数变化热图
    ax5 = fig.add_subplot(2, 3, 5)
    params_list = iter_history.get('parameters', [])
    if params_list and len(params_list) > 0:
        params_array = np.array(params_list).T  # 转置：行=设备, 列=迭代
        num_its = params_array.shape[1]
        device_names = history.get('device_names', [])

        im = ax5.imshow(params_array, aspect='auto', cmap='viridis',
                       extent=[1, num_its, -0.5, params_array.shape[0]-0.5])
        ax5.set_xlabel('Iteration')
        ax5.set_ylabel('Device')
        ax5.set_title('Parameter Evolution')
        plt.colorbar(im, ax=ax5, label='Value')

        # 添加数值标注
        for i in range(params_array.shape[0]):
            for j in range(params_array.shape[1]):
                value = params_array[i, j]
                text_color = 'white' if j < num_its // 2 else 'black'
                ax5.text(j + 0.5, i + 0.5, f'{value:.1f}',
                        ha='center', va='center', fontsize=5, color=text_color)

        if len(device_names) == params_array.shape[0]:
            ax5.set_yticks(range(len(device_names)))
            ax5.set_yticklabels(device_names, fontsize=8)

        ax5.axvline(x=best_iter, color='red', linestyle='--', linewidth=2)

    # 6. 初始/最优图像对比
    images = iter_history.get('images', [])
    initial_image = images[0] if images else None
    best_image = images[best_idx] if best_idx < len(images) else None

    ax6 = fig.add_subplot(2, 3, 6)
    if best_image is not None:
        ax6.imshow(best_image, cmap='gray')
        ax6.set_title(f'Best Beam (iter {best_iter})')
        # 标注质心等信息
        cx = iter_history.get('centroid_x', [0])[best_idx] if best_idx < len(centroid_x) else 0
        cy = iter_history.get('centroid_y', [0])[best_idx] if best_idx < len(centroid_y) else 0
        sx = iter_history.get('size_x', [0])[best_idx] if best_idx < len(size_x) else 0
        sy = iter_history.get('size_y', [0])[best_idx] if best_idx < len(size_y) else 0
        r = iter_history.get('roundness', [0])[best_idx] if best_idx < len(roundness) else 0

        info_text = f"iter: {best_iter}\nsize_x: {sx:.1f}\nsize_y: {sy:.1f}\nroundness: {r:.3f}"
        ax6.text(0.05, 0.95, info_text, transform=ax6.transAxes,
                verticalalignment='top', fontsize=9,
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        ax6.plot([cx], [cy], 'r+', markersize=15, markeredgewidth=2)

    # 在图下方添加最优参数表
    plt.figtext(0.5, 0.02, f"Best Params: {history.get('best_params', [])}",
               ha='center', fontsize=8, style='italic')

    plt.tight_layout(rect=[0, 0.03, 1, 0.97])
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n图表已保存至: {output_path}")
    plt.close()

    # ========== 自动生成报告 ==========
    report_text = generate_beam_report(history)
    report_path = output_path.replace('.png', '_report.md')
    save_report(report_text, report_path)


def plot_orbit_results(history, orbit_mode, filepath=None, output_path=None):
    """绘制轨道优化结果图表

    Args:
        history: 加载的历史数据字典
        orbit_mode: 'zero' 或 'ref'
        output_path: 输出图片路径
    """
    if output_path is None:
        output_path = 'results/orbit_optimization_plot.png'

    iter_history = history.get('iteration_history', {})
    scores = iter_history.get('scores', [])
    iterations = range(1, len(scores) + 1)

    best_idx = history.get('best_iteration_index', 0)
    best_iter = best_idx + 1 if best_idx < len(scores) else 1

    # 获取元数据
    algorithm = history.get('algorithm', 'Unknown')
    budget = history.get('budget', 0)
    timestamp = history.get('timestamp', '')
    # 如果 timestamp 为空，尝试从 filepath 提取
    if not timestamp and filepath:
        match = re.search(r'(\d{8}_\d{6})', filepath)
        if match:
            ts = match.group(1)
            timestamp = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"

    # 动态调整图形大小
    num_bpms = history.get('num_bpms', len(history.get('bpm_names', [])))
    num_correctors = len(history.get('device_names', []))

    fig_width = max(14, 6 + num_bpms * 0.5)
    fig_height = 12

    fig = plt.figure(figsize=(fig_width, fig_height))

    # 添加总标题
    fig.suptitle(f'Orbit Optimization | {algorithm} | Budget: {budget} | {orbit_mode} mode | {timestamp}',
                 fontsize=14, fontweight='bold', y=0.98)

    # 1. 收敛曲线
    ax1 = fig.add_subplot(2, 3, 1)
    ax1.plot(iterations, scores, 'b-', linewidth=2)
    ax1.axvline(x=best_iter, color='r', linestyle='--', alpha=0.7, label=f'Best: iter {best_iter}')
    ax1.scatter([best_iter], [scores[best_idx] if best_idx < len(scores) else scores[-1]],
                color='red', s=100, zorder=5)
    ax1.set_xlabel('Iteration')
    ax1.set_ylabel('Score')
    ax1.set_title('Convergence Curve')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 2. 偏差RMS变化
    deviations_list = iter_history.get('deviations', [])
    ax2 = fig.add_subplot(2, 3, 2)
    if deviations_list:
        rms_values = []
        for devs in deviations_list:
            if devs:
                rms = np.sqrt(np.mean(np.array(devs)**2))
                rms_values.append(rms)
            else:
                rms_values.append(0)
        if rms_values:
            ax2.plot(range(1, len(rms_values)+1), rms_values, 'r-', linewidth=2, marker='s')
            # 自动设置 y 轴范围
            y_min, y_max = min(rms_values), max(rms_values)
            y_range = y_max - y_min
            if y_range > 0:
                # 使用更智能的边距：数据范围的10%，但最小0.5%，最大20%
                margin_ratio = max(0.005, min(0.1, 0.1 * (1 - y_range / max(y_max, 0.1))))
                margin = y_range * margin_ratio
                ax2.set_ylim(y_min - margin, y_max + margin)
            else:
                # 所有值相同，设为固定范围
                ax2.set_ylim(y_max * 0.9, y_max * 1.1) if y_max != 0 else ax2.set_ylim(-0.1, 0.1)
    ax2.set_xlabel('Iteration')
    ax2.set_ylabel('RMS (mm)')
    ax2.set_title('RMS Deviation Evolution')
    ax2.grid(True, alpha=0.3)

    # 3. Peak 偏差变化曲线
    ax3 = fig.add_subplot(2, 3, 3)
    if deviations_list:
        peak_values = []
        for devs in deviations_list:
            if devs:
                peak = np.max(np.abs(np.array(devs)))
                peak_values.append(peak)
            else:
                peak_values.append(0)
        if peak_values:
            ax3.plot(range(1, len(peak_values)+1), peak_values, 'm-', linewidth=2, marker='s')
            # 自动设置 y 轴范围
            y_min, y_max = min(peak_values), max(peak_values)
            y_range = y_max - y_min
            if y_range > 0:
                margin_ratio = max(0.005, min(0.1, 0.1 * (1 - y_range / max(y_max, 0.1))))
                margin = y_range * margin_ratio
                ax3.set_ylim(y_min - margin, y_max + margin)
            else:
                ax3.set_ylim(y_max * 0.9, y_max * 1.1) if y_max != 0 else ax3.set_ylim(-0.1, 0.1)
    ax3.set_xlabel('Iteration')
    ax3.set_ylabel('Peak (mm)')
    ax3.set_title('Peak Deviation Evolution')
    ax3.grid(True, alpha=0.3)

    # 4. 轨道轮廓X
    bpm_readings = iter_history.get('bpm_readings', [])
    bpm_names = history.get('bpm_names', [])
    bpm_x_names = [bpm_names[i] for i in range(0, len(bpm_names), 2)]  # X方向BPM名字
    bpm_x_indices = list(range(0, len(bpm_names), 2))  # X方向BPM索引

    ax4 = fig.add_subplot(2, 3, 4)
    if bpm_readings and len(bpm_readings) > 0:
        # 初始轨道 X
        if len(bpm_readings[0]) >= len(bpm_x_indices):
            initial_x = [bpm_readings[0][i] for i in bpm_x_indices]
            ax4.plot(bpm_x_indices, initial_x, 'b--', linewidth=2, marker='o', markersize=5, label='Initial')

        # 最优轨道 X
        if best_idx < len(bpm_readings) and len(bpm_readings[best_idx]) >= len(bpm_x_indices):
            best_x = [bpm_readings[best_idx][i] for i in bpm_x_indices]
            ax4.plot(bpm_x_indices, best_x, 'g-', linewidth=2, marker='o', markersize=5, label='Best')

        # 参考轨道 X (仅ref模式)
        if orbit_mode == 'ref':
            ref_orbit = history.get('reference_orbit', {})
            ref_x = [ref_orbit.get(history['bpm_pvs'][i], 0) for i in bpm_x_indices]
            ax4.plot(bpm_x_indices, ref_x, 'orange', linestyle=':', linewidth=2, marker='o', markersize=5, label='Reference')

    # 设置 x 轴标签为所有 BPM 名字
    ax4.set_xticks(bpm_x_indices)
    ax4.set_xticklabels([n[:10] for n in bpm_x_names], rotation=45, fontsize=8, ha='right')
    ax4.set_xlabel('BPM')
    ax4.set_ylabel('X (mm)')
    ax4.set_title('Orbit Profile X')
    ax4.legend(fontsize=8)
    ax4.grid(True, alpha=0.3)

    # 5. 轨道轮廓Y
    bpm_y_names = [bpm_names[i] for i in range(1, len(bpm_names), 2)]  # Y方向BPM名字
    bpm_y_indices = list(range(1, len(bpm_names), 2))  # Y方向BPM索引

    ax5 = fig.add_subplot(2, 3, 5)
    if bpm_readings and len(bpm_readings) > 0:
        if len(bpm_readings[0]) >= len(bpm_y_indices):
            initial_y = [bpm_readings[0][i] for i in bpm_y_indices]
            ax5.plot(bpm_y_indices, initial_y, 'b--', linewidth=2, marker='o', markersize=5, label='Initial')

        if best_idx < len(bpm_readings) and len(bpm_readings[best_idx]) >= len(bpm_y_indices):
            best_y = [bpm_readings[best_idx][i] for i in bpm_y_indices]
            ax5.plot(bpm_y_indices, best_y, 'g-', linewidth=2, marker='o', markersize=5, label='Best')

        if orbit_mode == 'ref':
            ref_orbit = history.get('reference_orbit', {})
            ref_y = [ref_orbit.get(history['bpm_pvs'][i], 0) for i in bpm_y_indices]
            ax5.plot(bpm_y_indices, ref_y, 'orange', linestyle=':', linewidth=2, marker='o', markersize=5, label='Reference')

    # 设置 x 轴标签为所有 BPM 名字
    ax5.set_xticks(bpm_y_indices)
    ax5.set_xticklabels([n[:10] for n in bpm_y_names], rotation=45, fontsize=8, ha='right')
    ax5.set_xlabel('BPM')
    ax5.set_ylabel('Y (mm)')
    ax5.set_title('Orbit Profile Y')
    ax5.legend(fontsize=8)
    ax5.grid(True, alpha=0.3)

    # 6. 校正器参数变化热图
    params_list = iter_history.get('parameters', [])
    ax6 = fig.add_subplot(2, 3, 6)
    if params_list and len(params_list) > 0:
        params_array = np.array(params_list).T  # 转置：行=校正器, 列=迭代
        num_its = params_array.shape[1]
        device_names = history.get('device_names', [])

        # 使用 pcolormesh 替代 imshow，更精确
        extent = [0.5, num_its + 0.5, -0.5, params_array.shape[0] - 0.5]
        im = ax6.pcolormesh(params_array, cmap='viridis', shading='auto')
        ax6.set_xlim(0.5, num_its + 0.5)
        ax6.set_xlabel('Iteration')
        ax6.set_ylabel('Corrector')
        ax6.set_title('Corrector Parameter Evolution')
        plt.colorbar(im, ax=ax6, label='Value')

        if len(device_names) == params_array.shape[0]:
            ax6.set_yticks(range(len(device_names)))
            ax6.set_yticklabels(device_names, fontsize=8)

        ax6.axvline(x=best_iter, color='red', linestyle='--', linewidth=2)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n图表已保存至: {output_path}")
    plt.close()

    # ========== 自动生成报告 ==========
    report_text = generate_orbit_report(history, orbit_mode, filepath)
    report_path = output_path.replace('.png', '_report.md')
    save_report(report_text, report_path)


def main():
    """主函数"""
    print("=" * 60)
    print("SXFEL 优化结果可视化工具")
    print("=" * 60)

    # 扫描结果文件
    beam_files, orbit_files = scan_results()

    print(f"\n找到 {len(beam_files)} 个束流优化结果文件")
    print(f"找到 {len(orbit_files)} 个轨道优化结果文件")

    if not beam_files and not orbit_files:
        print("\n错误: 没有找到任何结果文件")
        print("请先运行优化: python run_optimization.py --config config_xxx.json --budget 20")
        sys.exit(1)

    # 选择优化类型
    opt_type = select_optimization_type()

    # 选择文件
    if opt_type == 'beam':
        filepath = select_file(beam_files)
        if filepath is None:
            sys.exit(1)
        print(f"\n加载文件: {filepath}")
        history = load_beam(filepath)
        plot_beam_results(history)
    else:
        filepath = select_file(orbit_files)
        if filepath is None:
            sys.exit(1)
        print(f"\n加载文件: {filepath}")
        history, orbit_mode = load_orbit(filepath)
        print(f"轨道模式: {orbit_mode}")
        plot_orbit_results(history, orbit_mode, filepath=filepath)

    print("\n可视化完成!")


if __name__ == "__main__":
    main()
