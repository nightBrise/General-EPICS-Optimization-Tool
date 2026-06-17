# 扩展接口

通用优化器通过三个注册机制 + Python 脚本模式支持自定义扩展。

## 1. 自定义评分策略

实现 `Scorer` 子类，用 `@register_scorer` 注册，在配置中通过 `custom:<name>` 引用。

**接口：**

```python
class Scorer(ABC):
    def __init__(self, params: dict = None):
        self.params = params or {}

    @abstractmethod
    def __call__(self, readings: list[float], targets: list[float],
                 weights: list[float], ranges=None) -> float:
        """readings: 组内目标 PV 的读数（已过 transform）
           targets:  目标值
           weights:  权重
           ranges:   可接受区间 [min,max] 或 None
           返回: 评分值（越小越好）"""
```

**示例 — 轨道复合评分：**

```python
import numpy as np
from core.scoring.base import Scorer
from core.scoring.registry import register_scorer

@register_scorer("orbit_composite")
class OrbitCompositeScorer(Scorer):
    """评分 = RMS + 0.3×Peak + 0.2×Roughness"""
    def __call__(self, readings, targets, weights, ranges=None):
        devs = [abs(r - t) for r, t in zip(readings, targets)]
        rms = np.sqrt(np.mean([d**2 for d in devs]))
        peak = max(devs)

        # 相邻 BPM 偏差变化的标准差（粗糙度）
        roughness = 0.0
        if len(devs) > 2:
            diff = [abs(devs[i+1] - devs[i]) for i in range(len(devs)-1)]
            roughness = np.std(diff)

        return rms + 0.3 * peak + 0.2 * roughness
```

**配置引用：**

```jsonc
{"scoring": {"method": "custom:orbit_composite"}}
```

---

## 2. 自定义数据变换

实现 `Transform` 子类，用 `@register_transform` 注册，在配置的 `transform` 字段中引用。

**接口：**

```python
class Transform(ABC):
    def __init__(self, params: dict = None):
        self.params = params or {}

    @abstractmethod
    def __call__(self, raw_value, *,
                 pv_name: str = "",
                 caget_fn=None) -> float:
        """raw_value: caget 原始返回值（标量或数组）
           pv_name:   当前 PV 名称
           caget_fn:  可选的 caget 回调（用于重复读取）
           返回: 处理后的 float 值，传给评分函数"""
```

**示例 — 能谱仪能量分析：**

```python
import numpy as np
from core.transforms.base import Transform
from core.transforms.registry import register_transform

@register_transform("energy_spectrum")
class EnergySpectrumTransform(Transform):
    """输入 1D 能谱数据 → 输出中心能量"""
    def __call__(self, raw_value, *, pv_name="", caget_fn=None):
        arr = np.asarray(raw_value, dtype=float)
        # 加权平均：强度为权重，能量通道为值
        channels = np.arange(len(arr))
        center = np.average(channels, weights=arr)
        return float(center)
```

**配置引用：**

```jsonc
"transform": {"type": "custom:energy_spectrum", "params": {}}
```

**变换链（先平均后分析）：**

```jsonc
"transform": [
    {"type": "average", "params": {"n": 5}},
    {"type": "custom:energy_spectrum", "params": {}}
]
```

⚠️ `average` 通过 caget_fn 重读原始 PV，**必须放在链首位**。

---

## 3. 自定义模拟器基准函数

在 `core/simulator.py` 的 `BENCHMARK_FUNCTIONS` 字典中添加新函数：

```python
BENCHMARK_FUNCTIONS["griewank"] = {
    "fn": lambda x: float(1 + sum(xi**2/4000 for xi in x) -
                           np.prod([np.cos(xi/np.sqrt(i+1)) for i, xi in enumerate(x)])),
    "optimum_x": [0.0],
    "optimum_f": 0.0,
    "range": [-600.0, 600.0],
}
```

配置引用：`"simulation": {"function": "griewank", "mode": "scalar"}`

`optimum_x` 约定：
- `[0.0]` → 自动扩展为 N 维全零
- `[1.0]` → 自动扩展为 N 维全 1
- `[0.5, -0.2]` → 精确位置，维度须匹配 config 中 variables 数量

---

## 4. Python 脚本模式

不通过 CLI 和 JSON，直接写 Python 脚本：

```python
import custom_scorers.beam_scorer   # 注册自定义模块

from core.epics_backend import set_backend
from core.simulator import set_simulator_config
from core.optimizer import GenericOptimizer
from core.utils import load_generic_config

# 一行切换模拟/真实
set_backend(use_simulator=False)

# 加载配置（支持 // 和 # 注释）
config = load_generic_config("config.json")

# 注入模拟器配置（仅 --simulator 模式需要）
# set_simulator_config(config)

# 创建优化器
opt = GenericOptimizer(config)

# 运行
result = opt.run()                  # ask→apply→read→score→tell
print(result['best_score'])

# 或手动回滚
# opt.rollback()
```

---

## 注册机制简介

两个注册表使用完全相同的装饰器模式：

```python
# 评分器
SCORER_REGISTRY = {}
@register_scorer("name") → 存入 SCORER_REGISTRY
config 引用: "scoring": {"method": "custom:name"}

# 变换
TRANSFORM_REGISTRY = {}
@register_transform("name") → 存入 TRANSFORM_REGISTRY
config 引用: "transform": {"type": "custom:name"}
```

自定义模块须在创建 `GenericOptimizer` 之前 import，装饰器在 import 时自动注册。
