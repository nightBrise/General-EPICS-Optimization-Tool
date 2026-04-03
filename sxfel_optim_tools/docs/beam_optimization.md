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
总评分 = beam_mode权重组 + fel_mode权重组
       = w_size × size_score + w_roundness × non_roundness_penalty + w_position × position_penalty
       + w_intensity × intensity_penalty + w_gaussian × gaussian_penalty
```

| 分量 | 含义 |
|------|------|
| `size_score` | 束流尺寸评分（根据目标模式计算） |
| `non_roundness_penalty` | 尺寸 × (1 - 圆度) |
| `position_penalty` | 位置偏移惩罚 |
| `intensity_penalty` | 强度惩罚（1/强度值，越强越低） |
| `gaussian_penalty` | 高斯拟合残差（越小越好） |
| `w_*` | 各分量权重（由 `beam_mode`/`fel_mode` 控制） |

### 目标模式 (`target_mode`)

| 模式 | size_score 计算方式 | 说明 |
|------|---------------------|------|
| `minimize`（默认） | `combined_size` | 最小化束流尺寸 |
| `exact` | `(实际尺寸 - 目标尺寸)² / 目标尺寸²` | 优化到指定目标尺寸 |
| `range` | 范围内为0，范围外惩罚 | 优化到指定尺寸范围内 |

**配置示例**：
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

### 圆度模式 (`beam_mode`)

| 模式 | w_size | w_roundness | w_position | 说明 |
|------|--------|-------------|------------|------|
| `size_focus` | 0.7 | 0.3 | 0.0 | 强尺寸优先 |
| `balanced`（默认） | 0.5 | 0.4 | 0.1 | 平衡模式 |
| `roundness_focus` | 0.3 | 0.6 | 0.1 | 强圆度优先 |

### FEL优化模式 (`fel_mode`)

用于优化FEL辐射光质量，控制强度和高斯符合度指标。

| 模式 | w_intensity | w_gaussian | 说明 |
|------|-------------|------------|------|
| `none` | 0 | 0 | 禁用FEL指标 |
| `intensity` | 0.4 | 0 | 强度优先 |
| `soft`（默认） | 0.25 | 0.15 | 平衡偏强度 |
| `both` | 0.2 | 0.2 | 两者均衡 |

**强度模式 (`intensity_mode`)**：

| 模式 | 说明 |
|------|------|
| `max`（默认） | 最大化峰值强度（beam_mask区域最大值） |
| `sum` | 最大化总强度（beam_mask区域积分） |

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
      "maintain_position": true,
      "fel_mode": "soft",
      "intensity_mode": "max"
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
      {"pv": "LA-PS:Q34:SETI", "range": [-1.04, -0.04], "base_step": 0.05}
    ],
    "correctors": [
      {"pv": "LA-PS:CH20:SETI", "range": [-0.39, 0.29], "base_step": 0.01}
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
| `objective.params.fel_mode` | 否 | FEL优化模式：`none`/`intensity`/`soft`/`both`，默认 `soft` |
| `objective.params.intensity_mode` | 否 | 强度模式：`max`/`sum`，默认 `max` |
| `camera.pv` | 是 | 相机数据 PV 地址 |
| `camera.camera_shape` | 是 | 相机图像尺寸 |
| `camera.gain_pv` | 否 | 增益控制 PV |
| `optimization.algorithm` | 否 | 算法，默认 Compass |
| `optimization.budget` | 否 | 迭代次数，默认 50 |
| `optimization.early_stopping.*` | 否 | 早停配置 |
| `devices.quadrupoles` | 是 | 四极磁铁设备列表 |
| `devices.correctors` | 否 | 校正子设备列表 |
| `devices.quadrupoles[].pv` | 是 | EPICS 过程变量地址 |
| `devices.quadrupoles[].range` | 是 | [最小值, 最大值] - 设备允许的参数范围 |
| `devices.quadrupoles[].base_step` | 否 | 基础步长，默认 0.01 |

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
  "range": [-1.04, -0.04],
  "base_step": 0.05
}
```

| 字段 | 说明 |
|------|------|
| `pv` | EPICS 过程变量地址 |
| `range` | [最小值, 最大值] - 设备允许的参数范围 |
| `base_step` | 基础步长，用于计算实际调整幅度 |

### 自适应步长机制

系统通过 `StepManager` 类实现自适应步长控制，采用**历史平均法**动态确定每个元件的敏感度。

#### 四阶段策略

| 阶段 | 策略 |
|------|------|
| **初始探测** | 大步长(×1.0)快速探测各元件影响，确保信号>噪声 |
| **敏感度确定** | 检测敏感度差异，差异大则延长，差异小则快速跳过 |
| **动态调整** | 敏感元件小步长，不敏感元件大步长 |
| **精准收敛** | 精细搜索最优解 |

#### 自适应决策逻辑

```
初始探测阶段（每次迭代检测所有元件）：
  - 记录各元件影响值
  - 计算影响值的变异系数(CV)

判断是否进入"动态调整"：
  - CV < 0.3（差异小）→ 快速进入动态调整
  - CV > 1.0（差异大）→ 继续细化检测
  - 否则（中等差异）→ 继续细化检测
```

#### 检测指标

| 指标 | 计算方法 | 说明 |
|------|----------|------|
| 中心位置 | `√(dx² + dy²)` 相对对角线百分比 | 光斑移动距离 |
| 圆度变化 | `\|size_x/size_y - 1\|` | 形状变化 |
| 强度变化 | `\|Δ intensity / max\| × 100` | 亮度变化 |

**综合影响** = 位置影响 + 圆度变化×100 + 强度变化×10

#### 历史平均法

```
# 每个元件维护影响历史（滑动窗口 N=3）
device_influence_history[i] = [变化量1, 变化量2, ...]

# 敏感度因子计算
avg_influence = mean(device_influence_history[i])
sensitivity_factor = 1.0 / (1.0 + avg_influence × 0.5)

# 实际步长 = base_step × 阶段因子 × 敏感度因子
# 敏感元件（大影响）→ sensitivity_factor 小 → 步长小
# 不敏感元件（小影响）→ sensitivity_factor 大 → 步长大
```

### CCD 增益控制

模拟器支持通过增益 PV 控制图像强度：
- 增益 PV：`LA-BI:PRF22:CAM:GainRaw`（可通过配置修改）
- 图像强度 = 基础强度 × (增益 / 100)
- 建议范围：[0, 500]

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

### 越界检测与回滚

系统通过 `_check_spot_out_of_bounds()` 方法检测光斑边缘是否越出 CCD：

```
CCD 边界
├── 预警区（边界15%内）：渐进惩罚 ×100
└── 完全越界：惩罚 ×1000 + 回滚参数
```

**惩罚计算**：

| 情况 | 公式 | 示例 |
|------|------|------|
| 边缘在预警区内 | `(预警区宽度 - 边缘距离) / 预警区宽度 × 100` | 左边缘距边界50px，惩罚≈33 |
| 边缘完全越界 | `溢出比例 × 1000` | 左边缘溢出光斑宽度的20%，惩罚=200 |

**触发回滚时**：
1. 参数回滚到上一步有效值
2. 返回高惩罚分数 (500)
3. 优化器会倾向于避开导致越界的参数组合

### 其他保护机制

- **参数边界限制**: 所有参数被限制在配置的 `range` 范围内
- **自适应步长限制**: 每次调整幅度不超过当前步长，防止意外大跳
- **读回验证**: 设置参数后验证实际值，超容差则重试
- **早停机制**: 连续多次无改进时自动停止
- **Ctrl+C 回滚**: 中断优化时自动恢复初始参数
- **交互确认**: 优化完成后询问是否应用结果
