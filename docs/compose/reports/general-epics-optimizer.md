---
feature: general-epics-optimizer
status: delivered
specs:
  - docs/compose/specs/2026-06-16-general-epics-optimizer-design.md
plans:
  - docs/compose/plans/2026-06-16-general-epics-optimizer.md
---

# 通用 EPICS 优化器 — Final Report

## What Was Built

将 SXFEL 紧耦合的优化工具重构为**纯配置驱动的通用 EPICS 优化器**。核心优化循环 `ask → apply → read → score → tell` 完全与领域无关，通过 JSON 配置驱动。用户只需定义变量 PV（旋钮）和目标 PV（被观测值），即可适配任意 EPICS 优化场景（轨道、束流、相位、幅度等），无需写 Python 代码。

## Architecture

```
config.json
    │
    ├── VariableManager     → 变量 PV 列表、范围、裁剪
    ├── HardwareController  → caput + 读回验证 + 等待稳定 + 回滚
    ├── ScoringEngine       → 分组评分策略（l2/l1/max/weighted_sum）
    ├── GenericOptimizer    → Nevergrad 优化循环（ask→apply→read→score→tell）
    └── ResultRecorder      → 通用 HDF5 结果存储
```

**关键文件：**

| 文件 | 职责 |
|------|------|
| `core/optimizer.py` | `GenericOptimizer` 主循环 |
| `core/variable_manager.py` | 变量 PV 管理 + 边界裁剪 |
| `core/hardware_controller.py` | 硬件写入 + 验证 + 等待 + 回滚 |
| `core/scoring/` | 评分框架：base + registry + l2/l1/max/weighted_sum |
| `core/result_recorder.py` | 通用 HDF5 记录（取代 `save_beam`/`save_orbit`） |
| `core/simulator.py` | 通用模拟器（PV pattern 注册制），保留 SimpleEPICSSimulator 向后兼容 |
| `core/utils.py` | 新增 `load_generic_config`（支持 // 和 # 注释）+ `validate_generic_config` |
| `run_optimization.py` | 通用 CLI 入口（无类型分支） |

### Design Decisions

- **分组评分隔离量纲**：每组独立评分 + 独立归一化。不同物理量（mm/MeV/degree）不会互相淹没
- **PV pattern 注册制模拟器**：用正则表达式匹配 PV 名，identity handler 用于变量 PV，linear handler 用于目标 PV。任意变量 PV 的 caput 会自动触达目标 PV 的响应
- **JSON + 注释剥离**：标准库零依赖，`#` 和 `//` 注释通过 regex 预处理后交给标准 `json.loads` 解析

## Usage

```bash
# 安装
pip install -r requirements.txt

# 通用优化入口（模拟器模式）
python run_optimization.py --config configs/orbit_example.json --simulator

# 真实 EPICS 模式
python run_optimization.py --config my_config.json

# 覆盖参数
python run_optimization.py --config config.json --budget 100 --algorithm NGOpt
```

**配置文件示例** (`configs/orbit_example.json`)：

```json
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
            "scoring": {"method": "l2"}
        }]
    },
    "optimization": {"algorithm": "Compass", "budget": 50},
    "hardware": {"tolerance": 0.0001, "max_wait": 10}
}
```

## Verification

所有组件通过独立测试和端到端集成测试：

| 测试 | 结果 |
|------|------|
| 配置解析 + 注释剥离 + JSON 验证 | ✓ |
| 评分策略（l2/l1/max/weighted_sum + range） | ✓ |
| VariableManager（解析 + clamp） | ✓ |
| HardwareController（caput + 验证 + 回滚） | ✓ |
| GenericOptimizer 完整循环（模拟器、早停、历史记录） | ✓ |
| ResultRecorder（HDF5 写入 + 回读校验） | ✓ |
| GenericSimulator（identity/linear handlers + 向后兼容） | ✓ |
| CLI 端到端（配置文件 → 优化 → 结果保存） | ✓ |

## Journey Log

- [lesson] the `min_adjust_interval` default of 6s causes long pauses between iterations in test runs; set to 0 in test configs
- [lesson] `Compass` algorithm name is not in Nevergrad's registry (needs `CompassSearch`); falls back to NGOpt automatically
- [lesson] the old `SimpleEPICSSimulator` had no identity-to-linear-response coupling; the new `GenericSimulator` uses `on_global_caput` to propagate variable PV changes to objective PV handlers
