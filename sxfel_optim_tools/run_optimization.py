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

from core.epics_backend import set_backend, is_simulator
from core.utils import load_config, validate_optimization_config
from core.objectives.registry import create_objective
from core.optimizer import Optimizer
from tools.plot_results import plot_beam_results, plot_orbit_results


# ============ 配置信息显示函数 ============

def print_beam_optimization_info(config, args):
    """打印束流优化配置详细信息"""
    print("\n" + "=" * 60)
    print("束流优化配置信息")
    print("=" * 60)

    # 任务信息
    print(f"任务名称: {config.get('name', '束流尺寸优化')}")
    print(f"目标: 最小化束流尺寸同时优化圆度")

    # 相机配置
    camera = config.get('camera', {})
    print(f"\n相机配置:")
    print(f"  图像 PV: {camera.get('pv', 'N/A')}")
    shape = camera.get('shape', ['N/A', 'N/A'])
    print(f"  图像尺寸: {shape[0]} x {shape[1]}")
    print(f"  增益 PV: {camera.get('gain_pv', 'N/A')}")

    # 图像处理参数
    obj_params = config.get('objective', {}).get('params', {})
    print(f"\n图像处理:")
    print(f"  平均次数: {obj_params.get('num_averages', 3)}")
    print(f"  目标对角线尺寸: {obj_params.get('target_diagonal_size_pixels', 0)} 像素")
    print(f"  位置维持模式: {'开启' if obj_params.get('maintain_position', False) else '关闭'}")

    # 算法信息
    algorithm = args.algorithm or config.get('optimization', {}).get('algorithm', 'NGOpt')
    print(f"\n优化算法: {algorithm}")
    print(f"  (如需查看算法参数说明，请参阅 README.md)")

    # 设备信息
    devices = config.get('devices', {})
    print(f"\n控制设备:")
    total_devices = 0
    for device_type, device_list in devices.items():
        print(f"  [{device_type}] ({len(device_list)} 个):")
        for dev in device_list:
            pv = dev.get('pv', 'N/A')
            rng = dev.get('range', ['N/A', 'N/A'])
            print(f"    - {pv}")
            print(f"      范围: [{rng[0]}, {rng[1]}]")
        total_devices += len(device_list)
    print(f"  总计: {total_devices} 个设备")

    # 优化参数
    opt_config = config.get('optimization', {})
    print(f"\n优化参数:")
    print(f"  迭代次数: {args.budget or opt_config.get('budget', 50)}")
    early_stop = opt_config.get('early_stopping', {})
    print(f"  早停: {'开启' if early_stop.get('enabled', True) else '关闭'}")
    if early_stop.get('enabled', True):
        print(f"    耐心值: {early_stop.get('patience', 10)}")
        print(f"    最小改进: {early_stop.get('min_relative_improvement', 0.005) * 100}%")

    # EPICS 模式
    print(f"\nEPICS 模式: {'模拟器' if args.simulator else '真实 EPICS'}")

    # 硬件参数
    obj_params = config.get('objective', {}).get('params', {})
    rep_rate = obj_params.get('repetition_rate', 10)
    min_interval = obj_params.get('min_adjust_interval', 6)
    poll_interval = obj_params.get('poll_interval', 0.2)
    tolerance = obj_params.get('tolerance', 0.0001)
    max_wait = obj_params.get('max_wait', 10)

    print(f"\n硬件参数:")
    print(f"  最小调整间隔: {min_interval} 秒")
    print(f"  轮询间隔: {poll_interval} 秒")
    print(f"  设定值容差: {tolerance}")
    print(f"  最大等待时间: {max_wait} 秒")

    print("=" * 60 + "\n")


def print_orbit_optimization_info(config, args, orbit_mode):
    """打印轨道优化配置详细信息"""
    print("\n" + "=" * 60)
    print("轨道优化配置信息")
    print("=" * 60)

    # 任务信息
    print(f"任务名称: {config.get('name', '轨道优化')}")
    mode_desc = "全0轨道" if orbit_mode == 'zero' else "参考轨道"
    print(f"目标: 使所有 BPM 读数接近 {mode_desc}")

    # BPM 配置
    bpm_pvs = config.get('bpm_pvs', [])
    bpm_count = len(bpm_pvs) // 2 if bpm_pvs else 0
    print(f"\nBPM 配置:")
    print(f"  BPM 数量: {bpm_count} 个")
    if bpm_pvs:
        print(f"  读取 PV 示例: {bpm_pvs[0]}")

    # 参考轨道（如果有）
    reference_orbit = config.get('objective', {}).get('params', {}).get('reference_orbit', {})
    if reference_orbit:
        print(f"\n参考轨道: 已配置 ({len(reference_orbit)} 个 PV)")
    else:
        print(f"\n参考轨道: 未配置 (优化到全0)")

    # 算法信息
    algorithm = args.algorithm or config.get('optimization', {}).get('algorithm', 'NGOpt')
    print(f"\n优化算法: {algorithm}")

    # 校正器设备
    devices = config.get('devices', {})
    correctors = devices.get('correctors', [])
    print(f"\n校正器设备: {len(correctors)} 个")
    for dev in correctors:
        pv = dev.get('pv', 'N/A')
        rng = dev.get('range', ['N/A', 'N/A'])
        print(f"  - {pv}")
        print(f"    范围: [{rng[0]}, {rng[1]}]")

    # 优化参数
    opt_config = config.get('optimization', {})
    print(f"\n优化参数:")
    print(f"  迭代次数: {args.budget or opt_config.get('budget', 50)}")
    early_stop = opt_config.get('early_stopping', {})
    print(f"  早停: {'开启' if early_stop.get('enabled', True) else '关闭'}")

    # EPICS 模式
    print(f"\nEPICS 模式: {'模拟器' if args.simulator else '真实 EPICS'}")

    # 硬件参数
    obj_params = config.get('objective', {}).get('params', {})
    rep_rate = obj_params.get('repetition_rate', 10)
    num_avg = obj_params.get('num_bpm_averages', 5)
    sample_interval = 1.0 / rep_rate
    min_interval = obj_params.get('min_adjust_interval', 6)
    poll_interval = obj_params.get('poll_interval', 0.2)
    tolerance = obj_params.get('tolerance', 0.0001)
    max_wait = obj_params.get('max_wait', 10)

    print(f"\n束流参数:")
    print(f"  重复频率: {rep_rate} Hz")
    print(f"  BPM采样次数: {num_avg} 次")
    print(f"  BPM采样间隔: {sample_interval:.3f} 秒")

    print(f"\n硬件参数:")
    print(f"  最小调整间隔: {min_interval} 秒")
    print(f"  轮询间隔: {poll_interval} 秒")
    print(f"  设定值容差: {tolerance}")
    print(f"  最大等待时间: {max_wait} 秒")

    print("=" * 60 + "\n")


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
    parser.add_argument(
        '--simulator',
        action='store_true',
        default=False,
        help='使用模拟器模式（默认使用真实 EPICS）'
    )
    args = parser.parse_args()

    # 设置 EPICS 后端模式
    if args.simulator:
        set_backend(use_simulator=True)
        print("模式: 模拟器模式")
    else:
        set_backend(use_simulator=False)
        print("模式: 真实 EPICS 模式")

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

    # 显示配置信息（根据目标类型差异化显示）
    obj_type = config.get('objective', {}).get('type', 'unknown')
    if obj_type == 'beam_size':
        print_beam_optimization_info(config, args)
    elif obj_type in ['orbit', 'orbit_zero', 'orbit_ref']:
        reference_orbit = config.get('objective', {}).get('params', {}).get('reference_orbit', {})
        orbit_mode = 'ref' if (reference_orbit and args.mode == 'ref') else 'zero'
        print_orbit_optimization_info(config, args, orbit_mode)
    else:
        # 默认简单显示
        name = config.get('name', '未命名任务')
        description = config.get('description', '')
        print(f"\n任务: {name}")
        print(f"描述: {description}")
        print(f"目标类型: {obj_type}")

    # 验证配置
    config_warnings = validate_optimization_config(config, obj_type)
    if config_warnings:
        print("\n配置警告:")
        for warning in config_warnings:
            print(f"  - {warning}")

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
        if obj_type == 'beam_size':
            plot_beam_results(history)
        elif obj_type in ['orbit', 'orbit_zero', 'orbit_ref']:
            reference_orbit = config.get('objective', {}).get('params', {}).get('reference_orbit', {})
            orbit_mode = 'ref' if reference_orbit else 'zero'
            plot_orbit_results(history, orbit_mode)

    except KeyboardInterrupt:
        print("\n\n用户中断优化")
        print("正在回滚到初始参数...")
        optimizer.rollback()
        sys.exit(1)
    except Exception as e:
        print(f"\n\n优化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
