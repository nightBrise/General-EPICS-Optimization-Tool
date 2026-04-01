# 轨道优化系统

## 概述

轨道优化系统通过调整校正子（corrector）磁铁参数，使所有 BPM（束流位置监视器）的读数接近零或指定的参考轨道值。

## 两种模式

### 全0轨道优化 (`--mode zero`)

使所有 BPM 的 X/Y 位置读数接近 0。

### 参考轨道优化 (`--mode ref`)

使所有 BPM 的 X/Y 位置读数接近配置文件中指定的 `reference_orbit` 值。

## 工作原理

### 优化流程

1. **初始化**: 从 EPICS 读取所有 BPM 的初始轨道位置
2. **参数设置**: Nevergrad 算法生成候选校正子参数
3. **轨道读取**: 设置校正子后，等待稳定，读取所有 BPM 数据
4. **评分计算**: 计算所有 BPM 读数与目标值的偏差平方和
5. **迭代优化**: 重复直到达到预算或触发早停

### 评分公式

```
score = sqrt(sum((bpm_reading_i - target_i)^2))
```

- `bpm_reading_i`: 第 i 个 BPM 的读数
- `target_i`: 目标值（全0时为 0.0，参考模式时为 `reference_orbit` 中配置的值）

## 配置参数

### 完整配置示例

```json
{
  "name": "orbit",
  "description": "轨道优化",
  "objective": {
    "type": "orbit",
    "read_pvs": [
      "LA-BI:SBPM1:POS_X",
      "LA-BI:SBPM1:POS_Y",
      "LA-BI:SBPM2:POS_X",
      "LA-BI:SBPM2:POS_Y"
    ],
    "params": {}
  },
  "reference_orbit": {
    "LA-BI:SBPM1:POS_X": 0.0,
    "LA-BI:SBPM1:POS_Y": 0.0,
    "LA-BI:SBPM2:POS_X": 0.0,
    "LA-BI:SBPM2:POS_Y": 0.0
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
    "correctors": [
      {"pv": "LA-PS:CH00:SETI", "range": [-0.5, 0.5]},
      {"pv": "LA-PS:CV00:SETI", "range": [-0.5, 0.5]}
    ]
  }
}
```

### 字段说明

| 字段 | 必需 | 说明 |
|------|------|------|
| `objective.type` | 是 | 必须为 `orbit` |
| `objective.read_pvs` | 是 | BPM PV 列表（X 和 Y 分别列出） |
| `reference_orbit` | 全0模式: 否<br/>参考模式: **是** | BPM 目标值字典 |
| `optimization.algorithm` | 否 | 算法，默认 Compass |
| `optimization.budget` | 否 | 迭代次数，默认 50 |
| `devices.correctors` | 是 | 校正子设备列表 |

### reference_orbit 特殊说明

- **全0模式**: 可以不提供此字段，或提供空字典 `{}`
- **参考模式**: 必须提供完整的 BPM 目标值映射

### 设备配置详情

```json
{
  "pv": "LA-PS:CH00:SETI",
  "range": [-0.5, 0.5]
}
```

- `pv`: EPICS 过程变量地址
- `range`: [最小值, 最大值] - 设备电流范围

## 使用方法

### 全0轨道优化

```bash
python run_optimization.py --config config_orbit.json --mode zero --budget 50
```

### 参考轨道优化

```bash
python run_optimization.py --config config_orbit.json --mode ref --budget 50
```

**注意**: 参考模式要求配置文件中存在非空的 `reference_orbit` 字段。

### 错误处理

如果使用 `--mode ref` 但未配置 `reference_orbit`：

```
错误: 参考轨道模式需要配置 reference_orbit
请在配置文件的 objective.params.reference_orbit 中设置参考轨道值
```

## 模式判断逻辑

```python
if args.mode is not None:
    if obj_type in ['orbit', 'orbit_zero']:
        if args.mode == 'zero':
            # 清空参考轨道，优化到全0
            config['objective']['params']['reference_orbit'] = {}
        elif args.mode == 'ref':
            # 检查是否配置了参考轨道
            reference_orbit = config.get('objective', {}).get('params', {}).get('reference_orbit', {})
            if not reference_orbit:
                print("错误: 参考轨道模式需要配置 reference_orbit")
                sys.exit(1)
```

## 目标函数实现

参考: [core/objectives/orbit_zero.py](../../core/objectives/orbit_zero.py)

`OrbitObjective` 类核心逻辑：

```python
def get_score(self, params, device_pvs):
    # 设置校正子参数
    success = safe_device_operation(device_pvs, params, self.config)
    if not success:
        return float('inf')

    time.sleep(0.5)  # 等待稳定

    # 获取BPM读数
    bpm_readings = self._get_bpm_readings()

    # 计算与参考轨道的偏差
    ref_values = [self.reference_orbit.get(pv, 0.0) for pv in self.bpm_pvs]
    diff = np.array(bpm_readings) - np.array(ref_values)
    score = np.sqrt(np.sum(diff**2))

    return score
```

## 统一配置文件

`config_orbit.json` 同时支持两种模式：

- 使用 `--mode zero` 时：`reference_orbit` 被清空，优化到全0
- 使用 `--mode ref` 时：使用配置文件中的 `reference_orbit` 值

## BPM PV 命名规范

| 设备 | PV 模式 | 示例 |
|------|---------|------|
| SBPM | `{name}:POS_X`, `{name}:POS_Y` | `LA-BI:SBPM1:POS_X` |
| 设备编号 | 1-10 | SBPM1 - SBPM10 |
| 坐标 | X (水平), Y (垂直) | POS_X, POS_Y |

## 安全机制

- **参数边界限制**: 所有校正子电流限制在配置范围内
- **读回验证**: 设置后验证实际值
- **早停机制**: 无显著改进时自动停止
