"""优化结果可视化工具

将优化过程和结果保存为一张图片。
"""
import os
import time
import numpy as np
import matplotlib.pyplot as plt


def plot_optimization_summary(history, output_path=None):
    """将优化过程和结果保存为一张图

    Args:
        history: 优化历史字典，包含:
            - device_pvs: 设备PV列表
            - device_names: 设备名称列表
            - iterations: 迭代序号列表
            - algorithm: 算法名称
            - budget: 预算
            - early_stop: 是否早停
            - best_score: 最佳评分
            - best_params: 最佳参数
            - initial_score: 初始评分
            - iteration_history: 详细历史
        output_path: 输出图片路径，默认在 results/ 目录生成
    """
    if output_path is None:
        os.makedirs('results', exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = f'results/optimization_{timestamp}.png'

    fig = plt.figure(figsize=(16, 10))
    fig.suptitle(f'Optimization Results - {history.get("algorithm", "N/A")}', fontsize=14, fontweight='bold')

    # 1. 收敛曲线 (左上)
    ax1 = fig.add_subplot(2, 2, 1)
    scores = history['iteration_history']['scores']
    iterations = range(1, len(scores) + 1)
    ax1.plot(iterations, scores, 'b-', linewidth=2, marker='o', markersize=4)
    best_idx = np.argmin(scores)
    ax1.axhline(y=scores[best_idx], color='r', linestyle='--', alpha=0.7,
                label=f'Best: {scores[best_idx]:.4f}')
    ax1.scatter([best_idx + 1], [scores[best_idx]], color='red', s=100, zorder=5)
    ax1.set_xlabel('Iteration')
    ax1.set_ylabel('Score')
    ax1.set_title('Convergence Curve')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 2. 参数变化热图 (右上)
    ax2 = fig.add_subplot(2, 2, 2)
    params = np.array(history['iteration_history']['parameters'])
    im = ax2.imshow(params.T, aspect='auto', cmap='viridis')
    ax2.set_xlabel('Iteration')
    ax2.set_ylabel('Parameter')
    ax2.set_yticks(range(len(history['device_names'])))
    ax2.set_yticklabels(history['device_names'], fontsize=8)
    ax2.set_title('Parameter Evolution')
    plt.colorbar(im, ax=ax2, label='Value')

    # 3. 束流尺寸变化 (左下，beam优化)
    physical_sizes = history['iteration_history'].get('physical_sizes')
    if physical_sizes and any(p != float('inf') and p == p for p in physical_sizes):
        ax3 = fig.add_subplot(2, 2, 3)
        valid_sizes = []
        valid_iters = []
        for idx, size in enumerate(physical_sizes):
            if size != float('inf') and size == size:  # 排除inf和nan
                valid_sizes.append(size)
                valid_iters.append(idx + 1)
        if valid_sizes:
            ax3.plot(valid_iters, valid_sizes, 'r-', linewidth=2, marker='s', markersize=4)
            ax3.set_xlabel('Iteration')
            ax3.set_ylabel('Beam Size (pixels)')
            ax3.set_title('Beam Size Evolution')
            ax3.grid(True, alpha=0.3)

    # 4. 总结信息 (右下)
    ax4 = fig.add_subplot(2, 2, 4)
    ax4.axis('off')

    summary_text = f"""Optimization Summary
{'-' * 40}
Algorithm: {history.get('algorithm', 'N/A')}
Budget: {history.get('budget', 'N/A')}
Early Stop: {'Yes' if history.get('early_stop', False) else 'No'}
{'-' * 40}
Initial Score: {history.get('initial_score', 'N/A'):.4f}
Best Score: {history.get('best_score', 'N/A'):.4f}
Improvement: {((history.get('initial_score', 1) - history.get('best_score', 0)) / history.get('initial_score', 1) * 100):.1f}%
{'-' * 40}
Best Parameters:
"""
    for name, val in zip(history['device_names'], history.get('best_params', [])):
        summary_text += f"  {name}: {val:.4f}\n"

    ax4.text(0.05, 0.95, summary_text, transform=ax4.transAxes,
             fontsize=10, verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"结果图已保存至: {output_path}")
    return output_path


if __name__ == '__main__':
    import argparse
    import h5py

    parser = argparse.ArgumentParser(description='可视化优化结果')
    parser.add_argument('h5_file', help='HDF5结果文件路径')
    parser.add_argument('-o', '--output', help='输出图片路径')
    args = parser.parse_args()

    # 从HDF5加载数据
    with h5py.File(args.h5_file, 'r') as f:
        history = {
            'algorithm': f['metadata'].attrs.get('algorithm', 'N/A'),
            'budget': int(f['metadata'].attrs.get('budget', 0)),
            'early_stop': bool(f['metadata'].attrs.get('early_stop', False)),
            'device_pvs': [pv.decode() for pv in f['metadata']['device_pvs'][:]],
            'device_names': [name.decode() for name in f['metadata']['device_names'][:]],
            'best_score': float(f['summary'].attrs.get('best_score', float('inf'))),
            'best_params': list(f['summary'].attrs.get('best_params', [])),
            'initial_score': float(f['summary'].attrs.get('initial_score', float('inf'))),
        }

        # 加载收敛数据
        convergence = f['convergence']
        history['iteration_history'] = {
            'scores': list(convergence['scores'][:]),
            'parameters': [],
            'physical_sizes': list(convergence['physical_sizes'][:]) if 'physical_sizes' in convergence else None,
        }

        # 加载每次迭代的参数
        if 'iterations' in f:
            for key in f['iterations'].keys():
                iter_group = f[f'iterations/{key}']
                if 'parameters' in iter_group:
                    history['iteration_history']['parameters'].append(list(iter_group['parameters'][:]))

    plot_optimization_summary(history, args.output)