# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本代码仓库中工作时提供指导。

## 对话语言限制

**与用户的所有对话必须使用中文。**

## 项目概述

这是一个**束流优化系统**，包含两个独立模块：
1. **束流尺寸优化**：通过调整四极磁铁使束流在YAG相机上呈现最小尺寸
2. **轨道优化**：通过调整校正器使BPM读数最小化或接近参考轨道

系统使用Nevergrad无梯度优化算法，支持真实EPICS控制和模拟器测试。

## 常用命令

```bash
# 束流优化（使用模拟器测试）
python beam_size_optimization.py

# 轨道优化
python orbit_optimization.py                  # 交互式选择模式
python orbit_optimization.py --mode zero      # 零点模式
python orbit_optimization.py --mode reference # 参考轨道模式

# 模拟器测试
python beam_simulation_tool.py

# 可视化
python visualization.py [结果文件.h5]

# GUI查看结果
python gui_results.py [结果文件.h5]
```

## 项目结构

```
beam_size_optimization/
├── beam_size_optimization.py    # 束流优化入口
├── orbit_optimization.py        # 轨道优化入口
├── config_beam.json            # 束流优化配置
├── config_orbit.json           # 轨道优化配置
├── optimization/               # 优化框架
│   ├── __init__.py
│   ├── optimizer.py           # 通用优化器（Nevergrad封装）
│   ├── objectives.py          # 三种目标函数
│   └── utils.py               # 通用工具（配置加载、设备操作）
├── beam_objectives.py          # 束流优化目标函数和工具
├── beam_simulation_tool.py     # EPICS模拟器（支持BPM轨道）
├── visualization.py            # 可视化工具
├── gui_results.py              # GUI结果查看
└── results/                    # 优化结果目录
```

## 架构

### 核心流程

**束流优化**：`beam_size_optimization.py` → `optimize_beam()` → Nevergrad → `objective_function()` → EPICS/模拟器 → YAG相机

**轨道优化**：`orbit_optimization.py` → `Optimizer.run()` → `OrbitZeroObjective/OrbitRefObjective` → EPICS/模拟器 → BPM

### 关键模块

- **`optimization/optimizer.py`**：`Optimizer`类封装Nevergrad优化循环，支持任意目标函数
- **`optimization/objectives.py`**：三种目标函数
  - `BeamObjective` - 束流尺寸优化
  - `OrbitZeroObjective` - 轨道零点优化（score = √Σ(xᵢ² + yᵢ²)）
  - `OrbitRefObjective` - 轨道参考优化（score = √Σ(xᵢ - xᵣᵢₒᵦ)²）
- **`beam_objectives.py`**：束流优化专用函数（图像处理、`optimize_beam()`等）
- **`beam_simulation_tool.py`**：`SimpleEPICSSimulator`模拟EPICS PV，支持相机图像和BPM轨道
- **`optimization/utils.py`**：`load_config`, `safe_device_operation`, `select_optimization_devices`等

### EPICS/模拟器切换机制

**重要设计**：所有EPICS操作通过 `beam_simulation_tool.py` 模拟，切换时只需修改各文件的导入语句。

**模拟模式**（当前默认）：
```python
from beam_simulation_tool import caget, caput, caget_many, caput_many
```

**真实EPICS模式**：
```python
from epics import caget, caput, caget_many, caput_many
```

需要切换的文件：
- `beam_objectives.py`
- `optimization/objectives.py`
- `optimization/utils.py`

### 结果存储

- 束流优化：`results/optimization_YYYYMMDD_HHMMSS.h5`
- 轨道优化：`results/orbit_optimization_YYYYMMDD_HHMMSS.h5`

HDF5结构：
- `/metadata` - 算法、预算、设备PV列表
- `/iterations/iter_N` - 每次迭代的参数、评分
- `/summary` - 初始值和最优值
- `/convergence` - 收敛数据

## 配置

### config_beam.json（束流优化）
```json
{
  "camera": {"pv": "LA-BI:PRF22:RAW:ArrayData", "shape": [1392, 1040]},
  "image_processing": {"num_averages": 3},
  "optimization": {"algorithm": "Compass", "budget": 50, "early_stopping": {...}},
  "target_diagonal_size_pixels": 0,
  "maintain_position": true,
  "devices": {"quadrupoles": [...], "correctors": [...]}
}
```

### config_orbit.json（轨道优化）
```json
{
  "bpm_pvs": ["LA-BI:SBPM30:POS_X", "LA-BI:SBPM30:POS_Y"],
  "reference_orbit": {"LA-BI:SBPM30:POS_X": 0.0, "LA-BI:SBPM30:POS_Y": 0.0},
  "optimization": {"algorithm": "Compass", "budget": 50, ...},
  "devices": {"correctors": [...]}
}
```

## 重要代码备注

### EPICS与模拟器切换
在需要使用真实EPICS时，修改以下文件的导入：
- `beam_objectives.py`：`from epics import caget, caput, caget_many, caput_many`
- `optimization/objectives.py`：`from epics import caget, caput, caget_many, caput_many`
- `optimization/utils.py`：`from epics import caget, caput, caget_many, caput_many`

### 模拟器支持
- `beam_simulation_tool.py` 提供 `SimpleEPICSSimulator` 类，支持：
  - 相机图像模拟（`LA-BI:PRF22:RAW:ArrayData` / `LA-BI:PRF29:RAW:ArrayData`）
  - BPM轨道模拟（`LA-BI:SBPM{index}:POS_X/POS_Y`）
  - 四极磁铁、校正器等设备模拟

### BPM PV格式
- 格式：`LA-BI:SBPM{index}:POS_X` 或 `LA-BI:SBPM{index}:POS_Y`
- 模拟器中BPM读数由初始偏移和校正器传递矩阵共同决定

### 相机图像
- 配置中shape为`[宽, 高]`，但EPICS数据reshape使用F-order（列优先）
- 模拟器支持PRF22和PRF29两种相机PV

## 开发规范

### 代码风格
遵循 [Google Python 代码风格指南](https://google.github.io/styleguide/pyguide.html)：

- **命名规范**：
  - 函数/变量：`snake_case`
  - 类名：`CapWords`
  - 常量：`ALL_CAPS`
  - 私有成员：前导下划线

- **导入顺序**：标准库 → 第三方库 → 本地模块

- **行长度**：最大100字符

- **文档字符串**：公共模块/函数/类需包含docstring

### 中文注释
所有代码注释使用中文。
