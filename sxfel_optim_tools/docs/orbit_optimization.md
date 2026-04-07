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
score = RMS + α×Peak + β×Roughness + δ×Skew
```

| 分量 | 含义 | 说明 |
|------|------|------|
| RMS | 整体偏差均方根 | `sqrt(mean((bpm_reading - target)²))`，反映整体轨道质量 |
| Peak | 最大偏差 | `max(\|bpm_reading - target\|)`，防止局部最差点失控 |
| Roughness | 轨道平滑性 | 相邻 BPM 偏差变化的标准差，避免轨道剧烈振荡 |
| Skew | 轨道倾斜度 | 入口到出口 BPM 偏差的线性倾斜 |

### 权重模式

通过 `objective.params.mode` 选择评分模式：

| 模式 | α (Peak) | β (Roughness) | δ (Skew) | 适用场景 |
|------|----------|---------------|----------|---------|
| `smooth` | 0.2 | 0.4 | 0.2 | 追求轨道平滑稳定 |
| `balanced` | 0.3 | 0.2 | 0.1 | 平衡精度与平滑（默认） |
| `aggressive` | 0.5 | 0.0 | 0.0 | 追求极致精度 |

> 注：aggressive 模式中 β=0 表示忽略平滑性惩罚，可能导致轨道振荡。

### 配置示例

```json
{
  "objective": {
    "type": "orbit",
    "read_pvs": ["LA-BI:SBPM1:POS_X", "LA-BI:SBPM1:POS_Y"],
    "params": {
      "mode": "balanced"
    }
  }
}
```

如不指定 `mode`，默认使用 `balanced` 模式。

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

### 硬件参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `repetition_rate` | 束团重复频率（Hz），用于计算 BPM 采样间隔 | 10 |
| `num_bpm_averages` | BPM 采样平均次数 | 5 |
| `min_adjust_interval` | 校正子最小调整间隔（秒），硬件限制 | 6 |
| `poll_interval` | 轮询间隔（秒） | 0.2 |
| `tolerance` | 设定值容差 | 0.0001 |
| `max_wait` | 最大等待时间（秒） | 10 |

> **注意**：硬件参数通过 `objective.params` 配置。`min_adjust_interval` 是硬件限制，校正子调整后需等待至少指定秒数才能进行下一次调整。BPM 采样间隔为 `1/repetition_rate` 秒。

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
    if obj_type == 'orbit':
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

参考: [core/objectives/orbit.py](../../core/objectives/orbit.py)

`OrbitObjective` 类核心逻辑：

```python
def get_score(self, params, device_pvs):
    # 1. 安全设置设备参数
    success = safe_device_operation(device_pvs, params, self.config)
    if not success:
        return float('inf')

    # 2. 检查硬件调整间隔（6秒限制）
    elapsed = time.time() - self._last_adjust_time
    if elapsed < self.min_adjust_interval:
        wait_time = self.min_adjust_interval - elapsed
        print(f"  等待硬件调整间隔: {wait_time:.1f}秒")
        time.sleep(wait_time)

    # 3. 轮询等待所有元件达到设定值
    from ..utils import wait_for_all_devices_settled
    success, failed_devs = wait_for_all_devices_settled(
        device_pvs, params,
        tolerance=self.tolerance,
        max_wait=self.max_wait,
        poll_interval=self.poll_interval
    )

    if not success:
        # 抛出异常，触发回滚
        raise OptimizationError("元件写入失败")

    self._last_adjust_time = time.time()

    # 4. 获取BPM读数（多次采样平均）
    bpm_readings = self._get_bpm_readings()

    # 5. 计算与参考轨道的偏差
    ref_values = [self.reference_orbit.get(pv, 0.0) for pv in self.bpm_pvs]
    diff = np.array(bpm_readings) - np.array(ref_values)
    score = np.sqrt(np.sum(diff**2))

    return score
```

### BPM 采样与错误处理

```python
def _get_bpm_readings(self, retries=3, retry_interval=1.0):
    """获取所有BPM的轨道读数（多次采样平均）

    特点：
    - 首次读取失败时自动重试（最多 retries 次）
    - 采样过程中如果某BPM持续返回None，抛出 RuntimeError 中断优化
    - 返回所有采样点的平均值
    """
    sample_interval = 1.0 / self.repetition_rate

    # 首先确保首次读取成功（最多重试 retries 次）
    for attempt_idx in range(retries + 1):
        readings = caget_many(self.bpm_pvs)
        none_pvs = [pv for pv, r in zip(self.bpm_pvs, readings) if r is None]
        if none_pvs:
            if attempt_idx < retries:
                print(f"  警告: {len(none_pvs)}/{len(self.bpm_pvs)} 个BPM返回None，第{attempt_idx+1}次重试...")
                time.sleep(retry_interval)
            else:
                raise RuntimeError(f"错误: BPM读取失败，以下BPM持续返回None: {none_pvs}")
        else:
            break

    # 读取成功后，进行多次采样平均
    all_readings = [readings]
    for _ in range(1, self.num_bpm_averages):
        readings = caget_many(self.bpm_pvs)
        none_pvs = [pv for pv, r in zip(self.bpm_pvs, readings) if r is None]
        if none_pvs:
            raise RuntimeError(f"错误: 以下BPM持续返回None: {none_pvs}")
        all_readings.append(readings)
        time.sleep(sample_interval)

    return np.mean(all_readings, axis=0).tolist()
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

## 结果可视化

优化完成后，结果自动保存为 HDF5 格式（`results/orbit_YYYYMMDD_HHMMSS.h5`）。

使用交互式可视化工具查看详细结果：

```bash
python tools/plot_results.py
```

该工具会生成包含以下内容的图表和报告：

### 生成的图表
- **收敛曲线**：评分随迭代次数的变化
- **RMS/Peak 偏差变化**：轨道偏差均方根和最大偏差的演化
- **轨道轮廓**：X/Y 方向轨道位置的初始、最优和参考值对比
- **校正器参数热图**：各校正器磁铁参数的变化过程

### 生成的报告 (Markdown)
可视化工具同时自动生成 Markdown 格式的优化报告，包含：
- **任务概述**：算法、预算、运行时间、轨道模式
- **优化结果摘要**：Score/RMS/Peak 的初始值、最优值及改善率
- **收敛分析**：实际迭代次数、早停原因、收敛评价
- **轨道质量详情**：逐个 BPM 的初始/最优偏差对比表
- **设备调节记录**：校正器参数变化及总调节幅度
- **配置信息**：BPM/校正器完整 PV 列表

### 查看历史结果

结果文件为 HDF5 格式（`.h5`），可通过以下方式加载：

```python
from core.results import load_orbit

history, orbit_mode = load_orbit('results/orbit_20260402_120000.h5')
print(history.keys())
# ['device_pvs', 'bpm_names', 'iterations', 'best_params', 'best_score', ...]
```
