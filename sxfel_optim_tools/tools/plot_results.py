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
    iterations = range(1, len(scores) + 1)

    best_idx = history.get('best_iteration_index', 0)
    best_iter = best_idx + 1 if best_idx < len(scores) else 1

    # 动态调整图形大小
    num_devices = len(history.get('device_names', []))
    figsize_width = max(14, 6 + num_devices * 0.3)
    fig_height = 14

    fig = plt.figure(figsize=(figsize_width, fig_height))

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

    # 2. 束流尺寸变化
    ax2 = fig.add_subplot(2, 3, 2)
    physical_sizes = iter_history.get('physical_sizes', [])
    if physical_sizes:
        valid_sizes = [s for s in physical_sizes if s != float('inf')]
        valid_iters = [i+1 for i, s in enumerate(physical_sizes) if s != float('inf')]
        if valid_sizes:
            ax2.plot(valid_iters, valid_sizes, 'r-', linewidth=2, marker='s', markersize=4)
    ax2.set_xlabel('Iteration')
    ax2.set_ylabel('Beam Size (pixels)')
    ax2.set_title('Beam Size Evolution')
    ax2.grid(True, alpha=0.3)

    # 3. 尺寸分量+圆度 (双Y轴)
    ax3 = fig.add_subplot(2, 3, 3)
    size_x = iter_history.get('size_x', [])
    size_y = iter_history.get('size_y', [])
    roundness = iter_history.get('roundness', [])

    ax3.set_xlabel('Iteration')
    ax3.set_ylabel('Size (pixels)', color='blue')
    l1, = ax3.plot(iterations, size_x, 'b-', linewidth=2, label='size_x')
    l2, = ax3.plot(iterations, size_y, 'g-', linewidth=2, label='size_y')
    ax3.tick_params(axis='y', labelcolor='blue')

    ax3_twin = ax3.twinx()
    ax3_twin.set_ylabel('Roundness', color='orange')
    l3, = ax3_twin.plot(iterations, roundness, 'orange', linewidth=2, marker='o', markersize=3, label='roundness')
    ax3_twin.tick_params(axis='y', labelcolor='orange')

    ax3.set_title('Size Components & Roundness')
    ax3.legend([l1, l2, l3], ['size_x', 'size_y', 'roundness'], loc='upper right')
    ax3.grid(True, alpha=0.3)

    # 4. 质心运动轨迹
    ax4 = fig.add_subplot(2, 3, 4)
    centroid_x = iter_history.get('centroid_x', [])
    centroid_y = iter_history.get('centroid_y', [])

    if centroid_x and centroid_y and len(centroid_x) == len(centroid_y):
        # 颜色渐变：冷色到暖色
        colors = plt.cm.viridis(np.linspace(0, 1, len(centroid_x)))
        for i in range(len(centroid_x) - 1):
            ax4.plot(centroid_x[i:i+2], centroid_y[i:i+2],
                    color=colors[i], linewidth=2)
        ax4.scatter(centroid_x[0], centroid_y[0], color='green',
                   s=200, marker='*', zorder=5, label='Start')
        ax4.scatter(centroid_x[-1], centroid_y[-1], color='red',
                   s=200, marker='*', zorder=5, label='End')

    ax4.set_xlabel('Centroid X')
    ax4.set_ylabel('Centroid Y')
    ax4.set_title('Centroid Trajectory')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    ax4.set_aspect('equal', adjustable='box')

    # 5. 校正器参数变化热图 + 最优参数表
    ax5 = fig.add_subplot(2, 3, 5)
    params_array = np.array(iter_history.get('parameters', [[]])).T if iter_history.get('parameters') else np.array([])

    if params_array.size > 0:
        num_its = params_array.shape[1]
        im = ax5.imshow(params_array, aspect='auto', cmap='viridis',
                       extent=[1, num_its, -0.5, params_array.shape[0]-0.5])
        ax5.set_xlabel('Iteration')
        ax5.set_ylabel('Device')
        ax5.set_title('Parameter Evolution')
        plt.colorbar(im, ax=ax5, label='Value')

        # 设置Y轴标签
        device_names = history.get('device_names', [])
        if len(device_names) == params_array.shape[0]:
            ax5.set_yticks(range(len(device_names)))
            ax5.set_yticklabels(device_names, fontsize=8)

        # 在热图上标注最佳迭代
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
            ax3.plot(list(bpm_x_indices), initial_x, 'b--', linewidth=2, label='Initial')

        # 最优轨道 X
        if best_idx < len(bpm_readings) and len(bpm_readings[best_idx]) >= len(bpm_x_indices):
            best_x = [bpm_readings[best_idx][i] for i in bpm_x_indices]
            ax3.plot(list(bpm_x_indices), best_x, 'g-', linewidth=2, label='Best')

        # 参考轨道 X (仅ref模式)
        if orbit_mode == 'ref':
            ref_orbit = history.get('reference_orbit', {})
            ref_x = [ref_orbit.get(history['bpm_pvs'][i], 0) for i in bpm_x_indices]
            ax3.plot(list(bpm_x_indices), ref_x, 'orange', linestyle=':', linewidth=2, label='Reference')

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
            ax4.plot(list(bpm_y_indices), initial_y, 'b--', linewidth=2, label='Initial')

        if best_idx < len(bpm_readings) and len(bpm_readings[best_idx]) >= len(bpm_y_indices):
            best_y = [bpm_readings[best_idx][i] for i in bpm_y_indices]
            ax4.plot(list(bpm_y_indices), best_y, 'g-', linewidth=2, label='Best')

        if orbit_mode == 'ref':
            ref_orbit = history.get('reference_orbit', {})
            ref_y = [ref_orbit.get(history['bpm_pvs'][i], 0) for i in bpm_y_indices]
            ax4.plot(list(bpm_y_indices), ref_y, 'orange', linestyle=':', linewidth=2, label='Reference')

    ax4.set_xlabel('BPM Index')
    ax4.set_ylabel('Y Position')
    ax4.set_title('Orbit Profile Y')
    ax4.legend()
    ax4.grid(True, alpha=0.3)

    # 5. 校正器参数变化热图
    ax5 = fig.add_subplot(2, 3, 5)
    params_array = np.array(iter_history.get('parameters', [[]])).T if iter_history.get('parameters') else np.array([])

    if params_array.size > 0:
        num_its = params_array.shape[1]
        im = ax5.imshow(params_array, aspect='auto', cmap='viridis',
                       extent=[1, num_its, -0.5, params_array.shape[0]-0.5])
        ax5.set_xlabel('Iteration')
        ax5.set_ylabel('Corrector')
        ax5.set_title('Corrector Parameter Evolution')
        plt.colorbar(im, ax=ax5, label='Value')

        device_names = history.get('device_names', [])
        if len(device_names) == params_array.shape[0]:
            ax5.set_yticks(range(len(device_names)))
            ax5.set_yticklabels(device_names, fontsize=8)

        ax5.axvline(x=best_iter, color='red', linestyle='--', linewidth=2)

    # 6. BPM偏差热图
    ax6 = fig.add_subplot(2, 3, 6)

    if deviations_list and len(deviations_list) > 0:
        # 转置：行为迭代，列为BPM
        deviations_array = np.array(deviations_list)
        if deviations_array.size > 0:
            im = ax6.imshow(deviations_array.T, aspect='auto', cmap='RdBu_r',
                           extent=[1, deviations_array.shape[0], -0.5, deviations_array.shape[1]-0.5],
                           vmin=-np.max(np.abs(deviations_array)),
                           vmax=np.max(np.abs(deviations_array)))
            ax6.set_xlabel('Iteration')
            ax6.set_ylabel('BPM')
            ax6.set_title('BPM Deviation Heatmap')
            plt.colorbar(im, ax=ax6, label='Deviation')

            bpm_names_short = [n[:10] for n in bpm_names]  # 缩短名称
            if len(bpm_names_short) == deviations_array.shape[1]:
                ax6.set_yticks(range(len(bpm_names_short)))
                ax6.set_yticklabels(bpm_names_short, fontsize=7)

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
