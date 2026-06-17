# SXFEL 优化工具箱 ![version](https://img.shields.io/badge/version-v3.0-brightgreen) ![python](https://img.shields.io/badge/python-3.10+-blue)

通用加速器优化框架，通过 JSON 配置驱动 EPICS PV 优化，开箱即用。

## 快速开始

```bash
pip install -r requirements.txt

# 模拟器模式（无需真实 EPICS）
python run_optimization.py --config configs/orbit_example.json --simulator

# 真实 EPICS 模式
python run_optimization.py --config configs/orbit_full.json
```

CLI 流程：确认 → 运行 → 摘要。`-y` 跳过确认，`--simulator` 切换模拟器，`--budget N` 覆盖迭代次数。

## 工作原理

```
设置变量 PV → 等待稳定 → 读取目标 PV → 计算评分 → 启发式搜索 → 重复
```

用户只需在 JSON 中声明**变量 PV**（旋钮）和**目标 PV**（观测值），无需写 Python。

```jsonc
{
    "name": "轨道优化",
    "variables": [
        {"pv": "LA-PS:CH00:SETI", "range": [-0.5, 0.5]}
    ],
    "objectives": {
        "groups": [{
            "name": "orbit",
            "weight": 1.0,
            "pvs": [
                {"pv": "LA-BI:SBPM1:POS_X", "target": 0.0}
            ],
            "scoring": {"method": "l2"}    // l2 | l1 | max | weighted_sum
        }]
    },
    "optimization": {"algorithm": "NGOpt", "budget": 50},
    "hardware": {"tolerance": 0.001, "max_wait": 10}
}
```

## 架构

```
config.json
    ├── VariableManager     → 变量 PV + 边界裁剪
    ├── HardwareController  → caput + 读回验证 + 等待 + 回滚
    ├── ScoringEngine       → 分组评分 (l2/l1/max/weighted_sum)
    ├── GenericOptimizer    → Nevergrad 优化循环
    └── ResultRecorder      → HDF5 结果存储
```

## 评分策略

| 方法 | 公式 | 何时用 |
|------|------|--------|
| `l2` | √(Σwᵢ·(rᵢ−tᵢ)² / Σwᵢ) | 默认，平滑收敛 |
| `l1` | Σwᵢ·\|rᵢ−tᵢ\| / Σwᵢ | 抗离群点 |
| `max` | max(wᵢ·\|rᵢ−tᵢ\|) | 压制最大偏差 |
| `weighted_sum` | Σwᵢ·(rᵢ−tᵢ) / Σwᵢ | 简单加权和 |

## 数据变换

| 变换 | 用途 |
|------|------|
| `reshape` | 1D 数组重组 |
| `average` | 连续读 N 次取平均（**须放在链首位**） |
| `combine` | 多维合并 (rms/max/sum) |
| `custom:beam_optimizer` | CCD 图像 → 束斑尺寸评分 |

变换可以链式组合：先平均降噪，再算束斑：

```jsonc
"transform": [
    {"type": "average", "params": {"n": 3}},
    {"type": "custom:beam_optimizer", "params": {"shape": [256,256], "order": "F"}}
]
```

## 推荐算法

| 场景 | 算法 |
|------|------|
| 默认，不确定 | `NGOpt` |
| 中等预算 (50-200) | `CMA` |
| 多局部极值 | `TwoPointsDE` |
| 极度昂贵 (< 20) | `BO` |
| 测量噪声大 | `TBPSA` |
| 局部精调 | `SQP` |

## CLI

```bash
python run_optimization.py --config config.json                # 基础用法
python run_optimization.py --config config.json -y             # 跳过确认
python run_optimization.py --config config.json --budget 100   # 覆盖迭代次数
python run_optimization.py --config config.json --algorithm CMA # 覆盖算法
python run_optimization.py --config config.json --simulator    # 模拟器模式
```

## 模拟器与算法测试

添加 `--simulator` 切换到算法测试台。内置 4 个基准函数（sphere/rosenbrock/rastrigin/ackley），3 种输出模式（scalar/vector/image），已知极值。

```bash
python run_optimization.py --config configs/test_bench_scalar.json --simulator -y
python run_optimization.py --config configs/test_bench_vector.json --simulator -y
python run_optimization.py --config configs/beam_example.json --simulator -y
```

## 配置文件

| 文件 | 用途 |
|------|------|
| `orbit_full.json` | 全零轨道（20 校正子 + 20 BPM） |
| `orbit_ref.json` | 参考轨道（非零 target） |
| `orbit_example.json` | 快速入门 + 完整注释 |
| `beam_example.json` | 束流尺寸优化 |
| `test_bench_scalar.json` | 标量算法测试 |
| `test_bench_vector.json` | 向量算法测试 |
| `transform_example.json` | **完整字段参考手册** |

## 详细文档

- [配置文件完整参考](configs/transform_example.json) — 每个字段的说明和示例
- [AGENTS.md](AGENTS.md) — 开发指引

## 支持

zhangny@sari.ac.cn, zhangbw@sari.ac.cn
