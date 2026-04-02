# 束斑优化系统

## 概述

束斑优化系统通过调整加速器磁铁参数（主要为四极磁铁和校正子），使束流在 YAG 诊断相机上呈现最小且最圆的尺寸。

## 工作原理

### 优化流程

1. **初始化**: 获取初始束流图像，计算初始尺寸、圆度和位置
2. **参数设置**: 通过 Nevergrad 优化算法生成候选参数
3. **图像采集**: 设置设备参数后，等待稳定，采集多帧图像平均
4. **评分计算**: 综合考虑尺寸、圆度和位置偏移计算评分
5. **迭代优化**: 重复步骤 2-4 直到达到预算或触发早停

### 评分公式

```
score = w_size * size_score + w_roundness * non_roundness_penalty + w_position * position_penalty
```

| 分量 | 含义 |
|------|------|
| `size_score` | 束流尺寸评分（根据目标模式计算） |
| `non_roundness_penalty` | 尺寸 × (1 - 圆度) |
| `position_penalty` | 位置偏移惩罚 |
| `w_*` | 各分量权重（由 `beam_mode` 控制） |

### 目标模式 (`target_mode`)

| 模式 | size_score 计算方式 | 说明 |
|------|---------------------|------|
| `minimize`（默认） | `combined_size` | 最小化束流尺寸 |
| `exact` | `(实际尺寸 - 目标尺寸)² / 目标尺寸²` | 优化到指定目标尺寸 |
| `range` | 范围内为0，范围外惩罚 | 优化到指定尺寸范围内 |

### 圆度模式 (`beam_mode`)

| 模式 | w_size | w_roundness | w_position | 说明 |
|------|--------|-------------|------------|------|
| `size_focus` | 0.7 | 0.3 | 0.0 | 强尺寸优先 |
| `balanced`（默认） | 0.5 | 0.4 | 0.1 | 平衡模式 |
| `roundness_focus` | 0.3 | 0.6 | 0.1 | 强圆度优先 |

### 位置维持

`maintain_position` 默认为 `true`，优化过程中会维持束流位置不变。

## 配置参数

### 完整配置示例

```json
{
  "name": "beam_size",
  "description": "束流尺寸优化",
  "objective": {
    "type": "beam_size",
    "read_pvs": ["LA-BI:PRF22:RAW:ArrayData"],
    "params": {
      "camera_shape": [1392, 1040],
      "num_averages": 3,
      "target_diagonal_size_pixels": 0,
      "target_mode": "minimize",
      "target_range": [0, 1000],
      "beam_mode": "balanced",
      "maintain_position": true
    }
  },
  "camera": {
    "pv": "LA-BI:PRF22:RAW:ArrayData",
    "camera_shape": [1392, 1040],
    "gain_pv": "LA-BI:PRF22:CAM:GainRaw",
    "gain_range": [0, 500]
  },
  "optimization": {
    "algorithm": "Compass",
    "budget": 50,
    "early_stopping": {
      "enabled": true,
      "patience": 10,
      "min_relative_improvement": 0.005
    }
  },
  "devices": {
    "quadrupoles": [
      {"pv": "LA-PS:Q34:SETI", "range": [-1.04, -0.04]}
    ],
    "correctors": [
      {"pv": "LA-PS:CH20:SETI", "range": [-0.39, 0.29]}
    ]
  }
}
```

### 不同模式配置示例

**精确目标模式**（优化到指定尺寸）：
```json
{
  "objective": {
    "params": {
      "target_mode": "exact",
      "target_diagonal_size_pixels": 200,
      "beam_mode": "balanced"
    }
  }
}
```

**范围目标模式**（优化到尺寸范围内）：
```json
{
  "objective": {
    "params": {
      "target_mode": "range",
      "target_range": [150, 300],
      "beam_mode": "roundness_focus"
    }
  }
}
```

### 字段说明

| 字段 | 必需 | 说明 |
|------|------|------|
| `objective.type` | 是 | 必须为 `beam_size` |
| `objective.read_pvs` | 是 | 相机图像 PV 列表 |
| `objective.params.camera_shape` | 否 | 相机图像尺寸 [宽, 高]，默认 [1392, 1040] |
| `objective.params.num_averages` | 否 | 平均帧数，默认 3 |
| `objective.params.target_diagonal_size_pixels` | 否 | 目标尺寸，0 表示最小化（精确目标模式） |
| `objective.params.target_mode` | 否 | 目标模式：`minimize`/`exact`/`range`，默认 `minimize` |
| `objective.params.target_range` | 否 | 范围目标 [最小, 最大]，默认 [0, 1000] |
| `objective.params.beam_mode` | 否 | 圆度模式：`size_focus`/`balanced`/`roundness_focus`，默认 `balanced` |
| `objective.params.maintain_position` | 否 | 是否维持束流位置，默认 true |
| `camera.pv` | 是 | 相机数据 PV 地址 |
| `camera.camera_shape` | 是 | 相机图像尺寸 |
| `camera.gain_pv` | 否 | 增益控制 PV |
| `optimization.algorithm` | 否 | 算法，默认 Compass |
| `optimization.budget` | 否 | 迭代次数，默认 50 |
| `optimization.early_stopping.*` | 否 | 早停配置 |
| `devices.quadrupoles` | 是 | 四极磁铁设备列表 |
| `devices.correctors` | 否 | 校正子设备列表 |

### 硬件参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `repetition_rate` | 束团重复频率（Hz），用于计算采样间隔 | 10 |
| `min_adjust_interval` | 校正子最小调整间隔（秒），硬件限制 | 6 |
| `poll_interval` | 轮询间隔（秒） | 0.2 |
| `tolerance` | 设定值容差 | 0.0001 |
| `max_wait` | 最大等待时间（秒） | 10 |

> **注意**：硬件参数通过 `objective.params` 配置。`min_adjust_interval` 是硬件限制，校正子调整后需等待至少指定秒数才能进行下一次调整。

### devices 配置详情

每个设备配置：
```json
{
  "pv": "LA-PS:Q34:SETI",
  "range": [-1.04, -0.04]
}
```

- `pv`: EPICS 过程变量地址
- `range`: [最小值, 最大值] - 设备允许的参数范围

## 使用方法

### 基本用法

```bash
python run_optimization.py --config config_beam.json
```

### 指定迭代次数

```bash
python run_optimization.py --config config_beam.json --budget 100
```

### 指定算法

```bash
python run_optimization.py --config config_beam.json --algorithm NGOpt
```

### 支持的算法

- `Compass` - 适用于低维问题，推荐作为首选
- `NGOpt` - Nevergrad 自适应优化
- `CMA` - 协方差矩阵适应
- `PSO` - 粒子群优化

## 目标函数实现

参考: [core/objectives/beam.py](../../core/objectives/beam.py)

目标函数类 `BeamObjective` 继承自 `BaseObjective`，实现以下核心方法：

- `get_score(params, device_pvs)`: 评估给定参数的评分
- `_get_average_YAG_image()`: 获取并处理束流图像

## 结果输出

优化完成后：
1. 终端显示收敛曲线和最优参数
2. 结果自动保存至 `results/beam_YYYYMMDD_HHMMSS.h5`
3. 可视化图表保存为 `results/beam_optimization_plot.png`

### 可视化结果

使用交互式可视化工具查看详细结果：

```bash
python tools/plot_results.py
```

该工具会生成包含以下内容的图表：
- **收敛曲线**：评分随迭代次数的变化
- **束流尺寸变化**：size_x、size_y 及组合尺寸的演化
- **尺寸分量与圆度**：双 Y 轴显示尺寸和圆度的关系
- **质心轨迹**：束流中心在图像上的移动路径
- **参数演化热图**：各磁铁/校正器参数的变化过程
- **最优束流图像**：最佳迭代时的束流图像

### 查看历史结果

结果文件为 HDF5 格式（`.h5`），可通过以下方式加载：

```python
from core.results import load_beam

history = load_beam('results/beam_20260402_120000.h5')
print(history.keys())
# ['device_pvs', 'device_names', 'iterations', 'best_params', 'best_score', ...]
```

## 安全机制

- **参数边界限制**: 所有参数被限制在配置的 `range` 范围内
- **读回验证**: 设置参数后验证实际值
- **早停机制**: 连续多次无改进时自动停止
- **交互确认**: 优化完成后询问是否应用结果
