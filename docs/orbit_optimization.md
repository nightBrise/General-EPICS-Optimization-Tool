# 轨道优化

## 新架构实现

轨道优化通过内置 `l2` 评分直接实现，无需自定义代码。

全零轨道和参考轨道只是 target 值的差异，用不同配置文件或不同 target 值区分。

## 配置示例

### 全零轨道（`configs/orbit_full.json`）

```jsonc
{
  "variables": [
    {"pv": "LA-PS:CH00:SETI", "range": [-0.5, 0.5]},
    {"pv": "LA-PS:CV00:SETI", "range": [-0.5, 0.5]},
    // ... 20 个校正子
  ],
  "objectives": {
    "groups": [{
      "name": "orbit",
      "pvs": [
        {"pv": "LA-BI:SBPM1:POS_X", "target": 0.0},   // 全零
        {"pv": "LA-BI:SBPM1:POS_Y", "target": 0.0},
        // ... 20 个 BPM
      ],
      "scoring": {"method": "l2"}
    }]
  }
}
```

### 参考轨道（`configs/orbit_ref.json`）

与全零轨道结构完全相同，仅 target 值不同：

```jsonc
{"pv": "LA-BI:SBPM1:POS_X", "target": 0.5},  // 参考轨道的 X 方向期望值
{"pv": "LA-BI:SBPM1:POS_Y", "target": 0.3},  // 参考轨道的 Y 方向期望值
```

## 评分策略

| 策略 | 适用 |
|------|------|
| `l2` | 默认，平滑收敛 |
| `l1` | 有离群 BPM 时更鲁棒 |
| `max` | 压制最差的 BPM |

## 降噪

每个 BPM 可配置 `average` transform：

```jsonc
{"pv": "LA-BI:SBPM1:POS_X", "target": 0.0,
 "transform": {"type": "average", "params": {"n": 5}}}
```

## 运行

```bash
python run_optimization.py --config configs/orbit_full.json      # 全零轨道
python run_optimization.py --config configs/orbit_ref.json       # 参考轨道
python run_optimization.py --config config.json --simulator -y   # 模拟器调试
```
