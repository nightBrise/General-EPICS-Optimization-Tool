#!/usr/bin/env python3
"""SXFEL 通用 EPICS 优化器入口

使用方法:
    python run_optimization.py --config config.json
    python run_optimization.py --config config.json -y        # 跳过确认
    python run_optimization.py --config config.json --simulator
"""
import argparse
import sys
import time
from core.epics_backend import set_backend, caget_many, is_simulator
from core.simulator import set_simulator_config
from core.utils import load_generic_config, validate_generic_config
from core.optimizer import GenericOptimizer
from core.result_recorder import save_results
import custom_scorers.beam_scorer  # noqa: 注册 custom:beam_optimizer 评分器

SEP = "=" * 60


def _read_current_values(optimizer: GenericOptimizer) -> tuple:
    """读取所有变量 PV 和目标 PV 的当前值"""
    var_pvs = optimizer.variable_mgr.pvs
    obj_pvs = optimizer._all_obj_pvs
    var_vals = caget_many(var_pvs) if var_pvs else []
    obj_vals = caget_many(obj_pvs) if obj_pvs else []
    score = None
    group_scores = None
    if obj_vals:
        try:
            score, group_scores = optimizer._compute_score(obj_vals)
        except Exception:
            pass
    return var_vals, obj_vals, score, group_scores


def _print_confirm(config: dict, optimizer: GenericOptimizer, var_vals: list,
                   obj_vals: list, score, group_scores):
    """打印确认信息"""
    var_count = len(optimizer.variable_mgr.pvs)
    obj_count = len(obj_vals)
    name = config.get('name', '未命名任务')
    mode = '模拟器' if is_simulator() else '真实 EPICS'
    opt_cfg = config.get('optimization', {})
    algorithm = opt_cfg.get('algorithm', 'NGOpt')
    budget = opt_cfg.get('budget', 50)
    es = opt_cfg.get('early_stopping', {})

    print(f"\n{SEP}")
    print(f"  优化任务: {name}")
    print(f"  模式: {mode}")
    print()

    # 变量 PV
    print(f"  ── 要调节的设备 ({var_count} 个) ──")
    for pv, val, rng in zip(optimizer.variable_mgr.pvs, var_vals,
                             optimizer.variable_mgr.ranges):
        v_str = f"{val:.4f}" if val is not None else "N/A"
        print(f"  {pv:<30s}  当前= {v_str:>10s}  范围= [{rng[0]}, {rng[1]}]")

    # 目标 PV
    flat_pvs = []
    flat_targets = []
    for g in optimizer.objective_groups:
        for pv, t in zip(g['pvs'], g['targets']):
            flat_pvs.append(pv)
            flat_targets.append(t)

    print(f"\n  ── 要观测的目标 ({obj_count} 个) ──")
    for i, (pv, target, val) in enumerate(zip(flat_pvs, flat_targets, obj_vals)):
        if hasattr(val, 'shape'):                       # ndarray
            v_str = f"image[{val.shape[0]}x{val.shape[1]}]"
        elif isinstance(val, list) and len(val) > 100:  # flat image list
            v_str = f"image[{len(val)} elements]"
        elif val is not None:
            v_str = f"{float(val):.4f}"
        else:
            v_str = "N/A"
        print(f"  {pv:<30s}  当前= {v_str:>18s}  目标= {target:>10.4f}")

    # 优化参数
    print(f"\n  ── 优化参数 ──")
    es_str = f"启用(patience={es.get('patience', 10)})" if es.get('enabled', True) else "关闭"
    print(f"  算法: {algorithm}    预算: {budget} 次    早停: {es_str}")

    # 初始评分
    if score is not None:
        print(f"\n  当前评分: {score:.4f}")
        if group_scores:
            for g, s in zip(optimizer.objective_groups, group_scores):
                print(f"    组 [{g['name']}]: {s:.4f}")

    print(f"{SEP}")


def _print_summary(result: dict, config: dict):
    """打印优化结果摘要"""
    scores = result.get('scores', [])
    if not scores or len(scores) < 2:
        return

    initial_score = scores[0]
    best_score = result.get('best_score', float('inf'))

    # 改善率
    if initial_score > 0 and best_score > 0 and best_score < initial_score:
        pct = (initial_score - best_score) / initial_score * 100
        improve_str = f"(↓ {pct:.1f}%)"
    else:
        improve_str = ""

    print(f"\n{SEP}")
    print(f"  优化完成!")
    print(f"  评分: {initial_score:.4f} → {best_score:.4f}  {improve_str}")

    # 目标改善 Top 5
    init_readings = result.get('readings', [])
    if len(init_readings) > 0:
        best_idx = result.get('best_iteration_index', 0)
        best_readings = init_readings[best_idx] if best_idx < len(init_readings) else init_readings[-1]
        init_r = init_readings[0]

        # 收集每个目标 PV 的改善
        flat_pvs = []
        flat_targets = []
        for g in result.get('_groups', []):
            for pv, t in zip(g.get('pvs', []), g.get('targets', [])):
                flat_pvs.append(pv)
                flat_targets.append(t)

        improvements = []
        for i in range(min(len(init_r), len(best_readings))):
            init_v = init_r[i]
            best_v = best_readings[i]
            if hasattr(init_v, 'shape') or isinstance(init_v, list):
                continue
            if init_v is not None and best_v is not None:
                imp = abs(float(init_v) - float(best_v))
                pv_name = flat_pvs[i] if i < len(flat_pvs) else f"PV[{i}]"
                improvements.append((pv_name, float(init_v), float(best_v), imp))
        improvements.sort(key=lambda x: x[3], reverse=True)

        if improvements:
            print(f"\n  ── 改善最明显的目标 (Top 5) ──")
            for pv, old, new, imp in improvements[:5]:
                print(f"  {pv:<30s}  {old:>8.4f} → {new:>8.4f}  (Δ {imp:.4f})")

    # 设备变化 Top 5
    params_list = result.get('parameters', [])
    if len(params_list) > 1:
        init_params = params_list[0]
        best_params = result.get('best_params', params_list[-1])
        changes = []
        for i, pv in enumerate(result.get('device_pvs', [])):
            if i < len(init_params) and i < len(best_params):
                delta = abs(best_params[i] - init_params[i])
                changes.append((pv, init_params[i], best_params[i], delta))
        changes.sort(key=lambda x: x[3], reverse=True)

        if changes:
            print(f"\n  ── 变化最大的设备 (Top 5) ──")
            for pv, old, new, delta in changes[:5]:
                print(f"  {pv:<30s}  {old:>8.4f} → {new:>8.4f}  (Δ {delta:.4f})")

    print(f"{SEP}")


def main():
    parser = argparse.ArgumentParser(
        description='通用 EPICS 优化器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python run_optimization.py --config configs/orbit_full.json
    python run_optimization.py --config config.json -y
    python run_optimization.py --config config.json --budget 100
    python run_optimization.py --config config.json --simulator
        """
    )
    parser.add_argument('--config', required=True, help='配置文件路径')
    parser.add_argument('--budget', type=int, help='覆盖配置的迭代次数')
    parser.add_argument('--algorithm', help='覆盖配置的算法')
    parser.add_argument('-y', '--yes', action='store_true', default=False,
                        help='跳过确认，直接开始')
    parser.add_argument('--simulator', action='store_true', default=False,
                        help='使用模拟器模式（默认真实 EPICS）')
    args = parser.parse_args()

    set_backend(use_simulator=args.simulator)

    # 加载配置
    config = load_generic_config(args.config)

    errors, warnings = validate_generic_config(config)
    if errors:
        print("\n配置错误（必须修复）:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    if args.budget:
        config.setdefault('optimization', {})['budget'] = args.budget
    if args.algorithm:
        config.setdefault('optimization', {})['algorithm'] = args.algorithm

    # 注入模拟器配置
    if args.simulator:
        set_simulator_config(config)

    # 初始化优化器
    optimizer = GenericOptimizer(config)

    # 读取当前值
    print(f"\n加载配置文件: {args.config}")
    var_vals, obj_vals, score, group_scores = _read_current_values(optimizer)

    # 打印确认
    _print_confirm(config, optimizer, var_vals, obj_vals, score, group_scores)

    # 警告提示
    if warnings:
        print("\n配置建议:")
        for w in warnings:
            print(f"  - {w}")

    # 确认
    if not args.yes:
        try:
            answer = input("\n确认开始优化? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n取消")
            sys.exit(0)
        if answer != 'y':
            print("取消")
            sys.exit(0)

    # 运行优化
    try:
        start = time.time()
        result = optimizer.run()
        elapsed = time.time() - start

        # 打印摘要
        _print_summary(result, config)

        # 保存
        filepath = save_results(result, config)
        print(f"  结果文件: {filepath}")
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n优化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
