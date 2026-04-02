# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本代码仓库中工作时提供指导。

## 对话语言限制

**与用户的所有对话必须使用中文。**

## 项目概述

**SXFEL 优化工具箱** - 通用加速器优化框架，支持束流尺寸优化、轨道优化等多种优化任务。

- 统一入口：`python run_optimization.py --config <config_file>`
- 配置驱动：新增优化任务只需提供配置文件，无需修改代码
- EPICS/模拟器双模式：测试时使用模拟器，生产环境切换到真实 EPICS

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 束流尺寸优化
python run_optimization.py --config config_beam.json --budget 50

# 轨道优化（全0模式）
python run_optimization.py --config config_orbit.json --mode zero --budget 50

# 轨道优化（参考轨道模式）
python run_optimization.py --config config_orbit.json --mode ref --budget 50

# 指定算法
python run_optimization.py --config config_beam.json --algorithm NGOpt
```

## 项目结构

```
sxfel_optim_tools/
├── run_optimization.py          # 统一入口
├── config_beam.json             # 束流优化配置
├── config_orbit.json            # 轨道优化配置
├── requirements.txt             # Python 依赖
├── core/                        # 核心模块
│   ├── objectives/              # 目标函数（注册机制）
│   │   ├── base.py             # 基类 BaseObjective
│   │   ├── registry.py         # @register_objective 注册表
│   │   ├── beam.py             # 束流目标 (beam_size)
│   │   ├── orbit_zero.py       # 零点轨道 (orbit_zero)
│   │   ├── orbit_ref.py        # 参考轨道 (orbit_ref)
│   │   └── metrics.py          # 线程安全指标追踪器
│   ├── optimizer.py            # Nevergrad 封装
│   ├── simulator.py            # EPICS 模拟器
│   └── utils.py               # 通用工具函数
├── tools/                      # 辅助工具
│   └── visualize.py           # 结果可视化
└── docs/                       # 详细文档
```

## 架构

### 核心流程

```
run_optimization.py → create_objective(config) → Optimizer.run() → objective.get_score()
```

### 目标函数注册机制

```python
# 注册新目标函数
@register_objective("my_objective")
class MyObjective(BaseObjective):
    def get_score(self, params, device_pvs):
        # 评分逻辑
        return score

# 使用配置文件
{
  "objective": {"type": "my_objective", ...}
}
```

### EPICS/模拟器切换

默认使用模拟器（用于测试）。切换到真实 EPICS 需修改 `core/utils.py` 导入：

```python
# 当前（模拟器）
from .simulator import caget, caput, caget_many, caput_many

# 切换到真实 EPICS
from epics import caget, caput, caget_many, caput_many
```

## 配置格式

### 统一配置字段

| 字段 | 说明 |
|------|------|
| `name` | 任务名称 |
| `objective.type` | 目标函数类型（beam_size, orbit_zero, orbit_ref） |
| `objective.read_pvs` | 读取的 EPICS PV 列表 |
| `devices` | 设备配置（quadrupoles, correctors 等） |
| `optimization.algorithm` | 算法（Compass, NGOpt, CMA, PSO） |
| `optimization.budget` | 迭代次数 |

### 束流优化配置

```json
{
  "objective": {
    "type": "beam_size",
    "params": {"shape": [1392, 1040], "num_averages": 3}
  },
  "devices": {"quadrupoles": [...], "correctors": [...]}
}
```

### 轨道优化配置

```json
{
  "objective": {
    "type": "orbit",
    "params": {"reference_orbit": {...}}
  },
  "devices": {"correctors": [...]}
}
```

## 关键模块

- **`core/objectives/registry.py`**：`@register_objective` 装饰器，`create_objective()` 工厂函数
- **`core/optimizer.py`**：`Optimizer` 类封装 Nevergrad 优化循环，支持早停
- **`core/simulator.py`**：`SimpleEPICSSimulator` 模拟 EPICS PV，支持相机图像和 BPM 轨道
- **`core/utils.py`**：`load_config`, `safe_device_operation`, `select_optimization_devices`

## 评分公式

**束流优化**：
```
score = 0.5 * size_score + 0.5 * non_roundness_penalty
```

**轨道优化**：
```
score = sqrt(sum((bpm_reading - target)^2))
```

## 新增目标函数

1. 在 `core/objectives/` 下编写类，使用 `@register_objective` 注册
2. 继承 `BaseObjective`，实现 `get_score(params, device_pvs)`
3. 创建配置文件
4. 运行 `python run_optimization.py --config <your_config.json>`

## 开发规范

- 代码注释使用中文
- 遵循 Google Python 代码风格
- 导入顺序：标准库 → 第三方库 → 本地模块
