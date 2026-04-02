#!/usr/bin/env python3
"""SXFEL优化工具统一入口

通过配置文件指定优化任务，支持束流优化、轨道优化等多种优化任务。

使用方法:
    python run_optimization.py --config config.json
    python run_optimization.py --config config.json --budget 100
    python run_optimization.py --config config.json --algorithm NGOpt
"""
import argparse
import sys
import time

from core.utils import load_config
from core.objectives.registry import create_objective
from core.optimizer import Optimizer
from tools.visualize import plot_optimization_summary


def main():
    parser = argparse.ArgumentParser(
        description='SXFEL优化工具 - 统一优化入口',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python run_optimization.py --config config_beam.json
    python run_optimization.py --config config_orbit.json --mode zero
    python run_optimization.py --config config_orbit.json --mode ref
    python run_optimization.py --config my_custom.json --budget 100
        """
    )
    parser.add_argument(
        '--config',
        required=True,
        help='配置文件路径'
    )
    parser.add_argument(
        '--budget',
        type=int,
        help='覆盖配置的迭代次数'
    )
    parser.add_argument(
        '--algorithm',
        help='覆盖配置的算法 (Compass, NGOpt, CMA, PSO)'
    )
    parser.add_argument(
        '--mode',
        choices=['zero', 'ref'],
        help='轨道优化模式: zero=优化到全0, ref=优化到参考轨道'
    )
    args = parser.parse_args()

    # 加载配置
    print(f"加载配置文件: {args.config}")
    config = load_config(args.config)

    # 处理轨道优化模式
    if args.mode is not None:
        obj_type = config.get('objective', {}).get('type', '')
        if obj_type in ['orbit', 'orbit_zero']:
            if args.mode == 'zero':
                # 清空参考轨道，优化到全0
                if 'params' not in config['objective']:
                    config['objective']['params'] = {}
                config['objective']['params']['reference_orbit'] = {}
                print("模式: 全0轨道优化")
            elif args.mode == 'ref':
                # 检查是否配置了参考轨道
                reference_orbit = config.get('objective', {}).get('params', {}).get('reference_orbit', {})
                if not reference_orbit:
                    print("错误: 参考轨道模式需要配置 reference_orbit")
                    print("请在配置文件的 objective.params.reference_orbit 中设置参考轨道值")
                    sys.exit(1)
                print("模式: 参考轨道优化")

    # 显示配置信息
    name = config.get('name', '未命名任务')
    description = config.get('description', '')
    print(f"\n任务: {name}")
    print(f"描述: {description}")

    obj_type = config.get('objective', {}).get('type', 'unknown')
    print(f"目标类型: {obj_type}")

    # 创建目标函数
    print("\n初始化目标函数...")
    objective_fn = create_objective(config)

    # 创建优化器
    optimizer = Optimizer(config, objective_fn)

    # 可选：覆盖配置
    if args.budget is not None:
        if 'optimization' not in config:
            config['optimization'] = {}
        config['optimization']['budget'] = args.budget
        print(f"覆盖迭代次数: {args.budget}")

    if args.algorithm is not None:
        if 'optimization' not in config:
            config['optimization'] = {}
        config['optimization']['algorithm'] = args.algorithm
        print(f"覆盖算法: {args.algorithm}")

    # 运行优化
    print("\n" + "=" * 60)
    print("开始优化...")
    print("=" * 60)

    start_time = time.time()
    try:
        best_params, best_score, device_pvs, history = optimizer.run()
        elapsed_time = time.time() - start_time

        print("\n" + "=" * 60)
        print("优化完成!")
        print("=" * 60)
        print(f"总耗时: {elapsed_time:.2f} 秒")
        print(f"最佳评分: {best_score:.6f}")

        # 保存结果
        result_file = objective_fn.save_results(history, config)
        print(f"结果已保存至: {result_file}")

        # 保存可视化图片
        plot_optimization_summary(history)

    except KeyboardInterrupt:
        print("\n\n用户中断优化")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n优化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
