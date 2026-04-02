#!/usr/bin/env python3
"""优化结果交互式可视化工具

使用方法:
    python tools/plot_results.py
"""
import os
import sys
import glob

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import numpy as np

from core.results import load_beam, load_orbit


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
        # 提取时间戳
        timestamp = filename.split('_')[1] + '_' + filename.split('_')[2].replace('.h5', '')
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


def plot_orbit_results(history, orbit_mode, output_path=None):
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

    # 动态调整图形大小
    num_bpms = history.get('num_bpms', len(history.get('bpm_names', [])))
    num_correctors = len(history.get('device_names', []))

    fig_width = max(14, 6 + num_bpms * 0.5)
    fig_height = 12

    fig = plt.figure(figsize=(fig_width, fig_height))

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
    ax2 = fig.add_subplot(2, 3, 2)
    deviations_list = iter_history.get('deviations', [])
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
    ax2.set_xlabel('Iteration')
    ax2.set_ylabel('RMS Deviation')
    ax2.set_title('RMS Deviation Evolution')
    ax2.grid(True, alpha=0.3)

    # 3. 轨道轮廓X
    ax3 = fig.add_subplot(2, 3, 3)
    bpm_readings = iter_history.get('bpm_readings', [])
    bpm_names = history.get('bpm_names', [])
    bpm_x_indices = range(0, len(bpm_names), 2)  # X方向BPM

    if bpm_readings and len(bpm_readings) > 0:
        # 初始轨道 X
        if len(bpm_readings[0]) >= len(bpm_x_indices):
            initial_x = [bpm_readings[0][i] for i in bpm_x_indices]
            ax3.plot(list(bpm_x_indices), initial_x, 'b--', linewidth=2, marker='o', markersize=5, label='Initial')

        # 最优轨道 X
        if best_idx < len(bpm_readings) and len(bpm_readings[best_idx]) >= len(bpm_x_indices):
            best_x = [bpm_readings[best_idx][i] for i in bpm_x_indices]
            ax3.plot(list(bpm_x_indices), best_x, 'g-', linewidth=2, marker='o', markersize=5, label='Best')

        # 参考轨道 X (仅ref模式)
        if orbit_mode == 'ref':
            ref_orbit = history.get('reference_orbit', {})
            ref_x = [ref_orbit.get(history['bpm_pvs'][i], 0) for i in bpm_x_indices]
            ax3.plot(list(bpm_x_indices), ref_x, 'orange', linestyle=':', linewidth=2, marker='o', markersize=5, label='Reference')

    ax3.set_xlabel('BPM Index')
    ax3.set_ylabel('X Position')
    ax3.set_title('Orbit Profile X')
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # 4. 轨道轮廓Y
    ax4 = fig.add_subplot(2, 3, 4)
    bpm_y_indices = range(1, len(bpm_names), 2)  # Y方向BPM

    if bpm_readings and len(bpm_readings) > 0:
        if len(bpm_readings[0]) >= len(bpm_y_indices):
            initial_y = [bpm_readings[0][i] for i in bpm_y_indices]
            ax4.plot(list(bpm_y_indices), initial_y, 'b--', linewidth=2, marker='o', markersize=5, label='Initial')

        if best_idx < len(bpm_readings) and len(bpm_readings[best_idx]) >= len(bpm_y_indices):
            best_y = [bpm_readings[best_idx][i] for i in bpm_y_indices]
            ax4.plot(list(bpm_y_indices), best_y, 'g-', linewidth=2, marker='o', markersize=5, label='Best')

        if orbit_mode == 'ref':
            ref_orbit = history.get('reference_orbit', {})
            ref_y = [ref_orbit.get(history['bpm_pvs'][i], 0) for i in bpm_y_indices]
            ax4.plot(list(bpm_y_indices), ref_y, 'orange', linestyle=':', linewidth=2, marker='o', markersize=5, label='Reference')

    ax4.set_xlabel('BPM Index')
    ax4.set_ylabel('Y Position')
    ax4.set_title('Orbit Profile Y')
    ax4.legend()
    ax4.grid(True, alpha=0.3)

    # 5. 校正器参数变化热图
    ax5 = fig.add_subplot(2, 3, 5)
    params_list = iter_history.get('parameters', [])
    if params_list and len(params_list) > 0:
        params_array = np.array(params_list).T  # 转置：行=校正器, 列=迭代
        num_its = params_array.shape[1]
        device_names = history.get('device_names', [])

        im = ax5.imshow(params_array, aspect='auto', cmap='viridis',
                        extent=[1, num_its, -0.5, params_array.shape[0]-0.5])
        ax5.set_xlabel('Iteration')
        ax5.set_ylabel('Corrector')
        ax5.set_title('Corrector Parameter Evolution')
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

    # 6. BPM偏差变化折线图
    ax6 = fig.add_subplot(2, 3, 6)

    if deviations_list and len(deviations_list) > 0:
        deviations_array = np.array(deviations_list)
        if deviations_array.size > 0:
            num_iters = deviations_array.shape[0]
            num_bpms = deviations_array.shape[1] if deviations_array.ndim > 1 else 1
            bpm_names_short = [n[:10] for n in bpm_names]

            for i in range(num_bpms):
                label = bpm_names_short[i] if i < len(bpm_names_short) else f'BPM {i}'
                ax6.plot(range(1, num_iters + 1), deviations_array[:, i], linewidth=1, label=label)

            ax6.set_xlabel('Iteration')
            ax6.set_ylabel('Deviation')
            ax6.set_title('BPM Deviation Evolution')
            ax6.legend(loc='upper right', fontsize=6, ncol=2)
            ax6.grid(True, alpha=0.3)
            ax6.axvline(x=best_iter, color='red', linestyle='--', linewidth=2)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n图表已保存至: {output_path}")
    plt.close()


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
        plot_orbit_results(history, orbit_mode)

    print("\n可视化完成!")


if __name__ == "__main__":
    main()
