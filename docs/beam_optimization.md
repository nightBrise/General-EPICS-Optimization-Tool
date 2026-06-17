# 束斑优化

## 新架构实现

束斑优化通过 `custom:beam_optimizer` transform 实现，流程：

```
caget(相机PV) → 1D 数组 (Fortran) → average(n=3) 降噪 → custom:beam_optimizer → 加权评分 → l2 vs target
```

## 配置示例

见 `configs/beam_example.json`。关键字段：

```jsonc
{
  "variables": [{"pv": "LA-PS:Q34:SETI", "range": [-1.04, -0.04]}, ...],
  "objectives": {
    "groups": [{
      "pvs": [{
        "pv": "LA-BI:PRF22:RAW:ArrayData",
        "target": 0.0,
        "transform": [
          {"type": "average", "params": {"n": 3}},
          {"type": "custom:beam_optimizer", "params": {"shape": [1392,1040], "order": "F"}}
        ]
      }],
      "scoring": {"method": "l2"}
    }]
  }
}
```

## 变换参数

| 参数 | 必填 | 默认 | 说明 |
|------|:--:|------|------|
| `shape` | 是 | — | 相机像素尺寸 [高度, 宽度] |
| `order` | 是 | — | 数据排列: `"F"` Fortran / `"C"` C 顺序 |
| `beam_mode` | 否 | `"balanced"` | `size_focus` / `balanced` / `roundness_focus` |
| `maintain_position` | 否 | `true` | 是否锁定初始束斑位置 |

## Python 脚本模式

```python
from core.epics_backend import set_backend
from core.optimizer import GenericOptimizer
import custom_scorers.beam_scorer  # 注册 custom:beam_optimizer

set_backend(use_simulator=False)
config = load_generic_config("config.json")
opt = GenericOptimizer(config)
opt.run()
```
