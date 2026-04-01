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
score = 0.4 * size_score + 0.4 * non_roundness_penalty + 0.2 * position_penalty
```

- `size_score`: 束流尺寸
- `non_roundness_penalty`: 尺寸 * (1 - 圆度)
- `position_penalty`: 位置偏移惩罚（仅当 `maintain_position: true` 时）

当 `maintain_position: false` 时：
```
score = 0.5 * size_score + 0.5 * non_roundness_penalty
```

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
      "shape": [1392, 1040],
      "num_averages": 3,
      "target_diagonal_size_pixels": 0,
      "maintain_position": true
    }
  },
  "camera": {
    "pv": "LA-BI:PRF22:RAW:ArrayData",
    "shape": [1392, 1040],
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

### 字段说明

| 字段 | 必需 | 说明 |
|------|------|------|
| `objective.type` | 是 | 必须为 `beam_size` |
| `objective.read_pvs` | 是 | 相机图像 PV 列表 |
| `objective.params.shape` | 否 | 图像尺寸 [宽, 高]，默认 [1392, 1040] |
| `objective.params.num_averages` | 否 | 平均帧数，默认 3 |
| `objective.params.target_diagonal_size_pixels` | 否 | 目标尺寸，0 表示最小化 |
| `objective.params.maintain_position` | 否 | 是否维持束流位置，默认 true |
| `camera.pv` | 是 | 相机数据 PV 地址 |
| `camera.shape` | 是 | 相机图像尺寸 |
| `camera.gain_pv` | 否 | 增益控制 PV |
| `optimization.algorithm` | 否 | 算法，默认 Compass |
| `optimization.budget` | 否 | 迭代次数，默认 50 |
| `optimization.early_stopping.*` | 否 | 早停配置 |
| `devices.quadrupoles` | 是 | 四极磁铁设备列表 |
| `devices.correctors` | 否 | 校正子设备列表 |

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
2. 结果自动保存至 `results/beam_optimization_YYYYMMDD_HHMMSS.h5`
3. 可视化图片保存为 `results/optimization_summary.png`

## 安全机制

- **参数边界限制**: 所有参数被限制在配置的 `range` 范围内
- **读回验证**: 设置参数后验证实际值
- **早停机制**: 连续多次无改进时自动停止
- **交互确认**: 优化完成后询问是否应用结果
