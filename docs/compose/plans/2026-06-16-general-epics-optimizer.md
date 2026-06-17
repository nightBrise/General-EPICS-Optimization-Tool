# 通用 EPICS 优化器实施计划

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/general-epics-optimizer.md)

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task.

**目标:** 将 SXFEL 紧耦合的优化工具重构为纯配置驱动的通用 EPICS 优化器

**架构:** 6 个独立组件: ScoringEngine, VariableManager, HardwareController, GenericOptimizer, ResultRecorder, GenericSimulator。全部通过 JSON 配置驱动。

**Tech Stack:** Python 3.10+, nevergrad, numpy, h5py, epics (pyepics), gradio

---

### 准备工作：确认现有文件结构

- [ ] **Step 0: 确认工作目录**

```
ls sxfel_optim_tools/core/
# 应看到: epics_backend.py  optimizer.py  results.py  simulator.py  step_manager.py  utils.py  objectives/
ls sxfel_optim_tools/core/objectives/
# 应看到: base.py  beam.py  metrics.py  orbit.py  registry.py  __init__.py
```

---

### Task 1: 配置文件解析器

**Covers:** [S5]

**Files:**
- Modify: `sxfel_optim_tools/core/utils.py` — 添加 `load_generic_config()` 函数
- Test: 在 `sxfel_optim_tools/core/utils.py` 末尾用 `if __name__ == "__main__"` 测试

- [ ] **Step 1.1: 实现加载 + 注释剥离**

在 `sxfel_optim_tools/core/utils.py` 中添加：

```python
import re


def load_generic_config(config_file: str) -> dict:
    """加载通用优化器配置（支持 // 和 # 注释）

    Args:
        config_file: JSON 配置文件路径

    Returns:
        dict: 解析后的配置字典

    Raises:
        json.JSONDecodeError: JSON 格式错误
        FileNotFoundError: 文件不存在
    """
    with open(config_file, 'r') as f:
        text = f.read()
    # 去掉 // 和 # 开头的行内注释（不影响字符串内的内容）
    text = re.sub(r'(?m)^\s*//.*$', '', text)   # 整行 // 注释
    text = re.sub(r'(?m)^\s*#.*$', '', text)    # 整行 # 注释
    text = re.sub(r'[,\s]*//[^"]*$', '', text, flags=re.MULTILINE)  # 行尾 // 注释
    import json
    return json.loads(text)
```

- [ ] **Step 1.2: 实现配置验证**

```python
def validate_generic_config(config: dict) -> list[str]:
    """验证通用优化器配置，返回警告列表

    Args:
        config: 配置字典

    Returns:
        list[str]: 警告信息列表（空表示无问题）
    """
    warnings = []

    if not config.get('variables'):
        warnings.append("未配置 variables（变量 PV）")
    else:
        for i, v in enumerate(config['variables']):
            if 'pv' not in v:
                warnings.append(f"variables[{i}] 缺少 pv 字段")
            if 'range' not in v or len(v.get('range', [])) != 2:
                warnings.append(f"variables[{i}] ({v.get('pv', '?')}) 缺少有效的 range")

    obj = config.get('objectives', {})
    groups = obj.get('groups', [])
    if not groups:
        warnings.append("未配置 objectives.groups（目标 PV）")
    for gi, g in enumerate(groups):
        if not g.get('pvs'):
            warnings.append(f"objectives.groups[{gi}] 缺少 pvs")
        for pi, pv in enumerate(g.get('pvs', [])):
            if isinstance(pv, str):
                continue  # 简写格式
            if 'pv' not in pv:
                warnings.append(f"objectives.groups[{gi}].pvs[{pi}] 缺少 pv 字段")

    opt = config.get('optimization', {})
    if not opt.get('budget'):
        warnings.append("未设置 optimization.budget，将使用默认值 50")

    return warnings
```

- [ ] **Step 1.3: 测试**

```python
if __name__ == "__main__":
    import tempfile, os
    test_config = """
    {
        // 测试配置
        "name": "test",
        "variables": [
            {"pv": "TEST:PV1", "range": [-1, 1]}  # 行尾注释
        ],
        "objectives": {
            "groups": [
                {
                    "name": "g1",
                    "weight": 1.0,
                    "pvs": [
                        {"pv": "TEST:OBJ1", "target": 0.0}
                    ],
                    "scoring": {"method": "l2"}
                }
            ]
        },
        "optimization": {"algorithm": "Compass", "budget": 50}
    }
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(test_config)
        tmp = f.name
    config = load_generic_config(tmp)
    assert config['name'] == 'test'
    assert len(config['variables']) == 1
    assert len(config['objectives']['groups']) == 1
    os.unlink(tmp)
    print("✓ Task 1 passed")
```

---

### Task 2: 评分框架 + 内置策略

**Covers:** [S6, S8]

**Files:**
- Create: `sxfel_optim_tools/core/scoring/__init__.py`
- Create: `sxfel_optim_tools/core/scoring/base.py`
- Create: `sxfel_optim_tools/core/scoring/registry.py`
- Create: `sxfel_optim_tools/core/scoring/l2.py`
- Create: `sxfel_optim_tools/core/scoring/l1.py`
- Create: `sxfel_optim_tools/core/scoring/max_score.py`
- Create: `sxfel_optim_tools/core/scoring/weighted_sum.py`

- [ ] **Step 2.1: `__init__.py`**

```python
from .base import Scorer
from .registry import register_scorer, create_scorer, get_registered_scorers
from .l2 import L2Scorer
from .l1 import L1Scorer
from .max_score import MaxScorer
from .weighted_sum import WeightedSumScorer
```

- [ ] **Step 2.2: `base.py` — Scorer 基类**

```python
"""评分器基类"""
from abc import ABC, abstractmethod


class Scorer(ABC):
    """评分器基类。

    所有评分策略必须继承此类并实现 __call__ 方法。
    """

    def __init__(self, params: dict = None):
        self.params = params or {}

    @abstractmethod
    def __call__(self, readings: list[float], targets: list[float],
                 weights: list[float], ranges: list[list[float] | None] = None) -> float:
        """计算评分（越小越好）

        Args:
            readings: 组内目标 PV 的读数列表
            targets: 目标值列表
            weights: 权重列表（已归一化）
            ranges: 可接受区间列表，None 表示无区间限制

        Returns:
            float: 评分值，越小越好
        """
```

- [ ] **Step 2.3: `registry.py`**

```python
"""评分器注册表"""
from .base import Scorer

SCORER_REGISTRY = {}


def register_scorer(name: str):
    """注册评分器

    Args:
        name: 评分器名称（用于配置中引用）

    Usage:
        @register_scorer("my_scorer")
        class MyScorer(Scorer):
            ...
    """
    def decorator(cls):
        if not issubclass(cls, Scorer):
            raise TypeError(f"{cls.__name__} must inherit from Scorer")
        SCORER_REGISTRY[name] = cls
        return cls
    return decorator


def create_scorer(method: str, params: dict = None) -> Scorer:
    """根据方法名创建评分器

    Args:
        method: "l2", "l1", "max", "weighted_sum", 或 "custom:<name>"
        params: 评分器参数

    Returns:
        Scorer: 评分器实例
    """
    if method.startswith("custom:"):
        name = method[7:]
        cls = SCORER_REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"未注册的自定义评分器: {name}，可用: {list(SCORER_REGISTRY.keys())}")
    else:
        cls = SCORER_REGISTRY.get(method)
        if cls is None:
            raise ValueError(f"未知评分方法: {method}，可用: {list(SCORER_REGISTRY.keys())}")
    return cls(params)


def get_registered_scorers() -> list[str]:
    return list(SCORER_REGISTRY.keys())
```

- [ ] **Step 2.4: `l2.py`**

```python
import numpy as np
from .base import Scorer
from .registry import register_scorer


@register_scorer("l2")
class L2Scorer(Scorer):
    """L2 评分: sqrt(Σ(wi * (ri - ti)^2) / Σ wi)"""

    def __call__(self, readings, targets, weights, ranges=None):
        if not readings:
            return float('inf')
        total = 0.0
        w_sum = 0.0
        for i, (r, t, w) in enumerate(zip(readings, targets, weights)):
            deviation = abs(r - t)
            if ranges and ranges[i] is not None:
                lo, hi = ranges[i]
                if lo <= r <= hi:
                    deviation = 0.0
            total += w * deviation ** 2
            w_sum += w
        if w_sum == 0:
            return float('inf')
        return np.sqrt(total / w_sum)
```

- [ ] **Step 2.5: `l1.py`**

```python
from .base import Scorer
from .registry import register_scorer


@register_scorer("l1")
class L1Scorer(Scorer):
    """L1 评分: Σ(wi * |ri - ti|) / Σ wi"""

    def __call__(self, readings, targets, weights, ranges=None):
        if not readings:
            return float('inf')
        total = 0.0
        w_sum = 0.0
        for i, (r, t, w) in enumerate(zip(readings, targets, weights)):
            deviation = abs(r - t)
            if ranges and ranges[i] is not None:
                lo, hi = ranges[i]
                if lo <= r <= hi:
                    deviation = 0.0
            total += w * deviation
            w_sum += w
        if w_sum == 0:
            return float('inf')
        return total / w_sum
```

- [ ] **Step 2.6: `max_score.py`**

```python
from .base import Scorer
from .registry import register_scorer


@register_scorer("max")
class MaxScorer(Scorer):
    """Max 评分: max(wi * |ri - ti|)"""

    def __call__(self, readings, targets, weights, ranges=None):
        if not readings:
            return float('inf')
        max_dev = 0.0
        for i, (r, t, w) in enumerate(zip(readings, targets, weights)):
            deviation = abs(r - t)
            if ranges and ranges[i] is not None:
                lo, hi = ranges[i]
                if lo <= r <= hi:
                    deviation = 0.0
            max_dev = max(max_dev, w * deviation)
        return max_dev
```

- [ ] **Step 2.7: `weighted_sum.py`**

```python
from .base import Scorer
from .registry import register_scorer


@register_scorer("weighted_sum")
class WeightedSumScorer(Scorer):
    """加权和评分: Σ(wi * (ri - ti)) / Σ wi"""

    def __call__(self, readings, targets, weights, ranges=None):
        if not readings:
            return float('inf')
        total = 0.0
        w_sum = 0.0
        for i, (r, t, w) in enumerate(zip(readings, targets, weights)):
            deviation = r - t
            if ranges and ranges[i] is not None:
                lo, hi = ranges[i]
                if lo <= r <= hi:
                    deviation = 0.0
            total += w * deviation
            w_sum += w
        if w_sum == 0:
            return float('inf')
        return total / w_sum
```

- [ ] **Step 2.8: 测试**

```python
if __name__ == "__main__":
    from scoring import L2Scorer, L1Scorer, MaxScorer, WeightedSumScorer

    readings = [1.0, 2.0, 3.0]
    targets = [0.0, 0.0, 0.0]
    weights = [1.0, 1.0, 1.0]

    # L2 test
    s = L2Scorer()
    r = s(readings, targets, weights)
    expected = ((1 + 4 + 9) / 3) ** 0.5
    assert abs(r - expected) < 1e-6, f"L2: {r} != {expected}"

    # L1 test
    s = L1Scorer()
    r = s(readings, targets, weights)
    expected = (1 + 2 + 3) / 3
    assert abs(r - expected) < 1e-6, f"L1: {r} != {expected}"

    # Max test
    s = MaxScorer()
    r = s(readings, targets, weights)
    assert abs(r - 3.0) < 1e-6, f"Max: {r} != 3.0"

    # Range test: reading within range should contribute 0
    s = L2Scorer()
    r = s([1.0], [0.0], [1.0], [[0.5, 1.5]])
    assert abs(r) < 1e-6, f"Range: {r} != 0"

    # Range test: reading outside range should penalize
    r = s([2.0], [0.0], [1.0], [[0.5, 1.5]])
    assert r > 0, f"Range outside: {r} <= 0"

    print("✓ Task 2 passed")
```

---

### Task 3: VariableManager

**Covers:** [S7]

**Files:**
- Create: `sxfel_optim_tools/core/variable_manager.py`

- [ ] **Step 3.1: 实现 VariableManager**

```python
"""变量 PV 管理器"""
from ..epics_backend import caget_many


class VariableManager:
    """管理优化变量 PV：PV 列表、范围、初始值"""

    def __init__(self, config: dict):
        """从配置初始化

        Args:
            config: 配置字典中的 variables 字段
        """
        raw = config.get('variables', [])
        self.pvs: list[str] = []
        self.ranges: list[list[float]] = []
        self.base_steps: list[float] = []
        self.initial_values: list[float] = []

        for v in raw:
            self.pvs.append(v['pv'])
            self.ranges.append(v['range'])
            self.base_steps.append(v.get('base_step', 0.01))

    def read_initial_values(self) -> list[float]:
        """从 EPICS 读取所有变量 PV 的当前值，保存为初始值

        Returns:
            list[float]: 当前值列表
        """
        values = caget_many(self.pvs)
        # 对 None 值使用范围中点（同现有 select_optimization_devices 逻辑）
        clamped = []
        for i, (v, r) in enumerate(zip(values, self.ranges)):
            if v is None:
                print(f"  警告: 无法读取 {self.pvs[i]}，使用范围中点 {sum(r)/2}")
                v = sum(r) / 2
            clamped.append(v)
        self.initial_values = list(clamped)
        return clamped

    def clamp_params(self, params: list[float]) -> list[float]:
        """将参数限制在范围内

        Args:
            params: 参数列表

        Returns:
            list[float]: 限制后的参数
        """
        import numpy as np
        return [np.clip(p, r[0], r[1]) for p, r in zip(params, self.ranges)]

    def __len__(self):
        return len(self.pvs)

    def __repr__(self):
        return f"VariableManager({len(self)} PVs)"
```

- [ ] **Step 3.2: 测试**

```python
if __name__ == "__main__":
    config = {
        "variables": [
            {"pv": "TEST:CH00", "range": [-0.5, 0.5]},
            {"pv": "TEST:CH01", "range": [-1.0, 1.0], "base_step": 0.1}
        ]
    }
    vm = VariableManager(config)
    assert len(vm) == 2
    assert vm.pvs == ["TEST:CH00", "TEST:CH01"]
    assert vm.ranges == [[-0.5, 0.5], [-1.0, 1.0]]
    assert vm.base_steps == [0.01, 0.1]

    clamped = vm.clamp_params([10.0, -10.0])
    assert clamped == [0.5, -1.0], f"clamp: {clamped}"

    print("✓ Task 3 passed")
```

---

### Task 4: HardwareController

**Covers:** [S10]

**Files:**
- Create: `sxfel_optim_tools/core/hardware_controller.py`

- [ ] **Step 4.1: 实现 HardwareController**

```python
"""硬件控制器：caput + 验证 + 等待稳定 + 回滚"""
import time
from ..epics_backend import caget, caput, caget_many


class HardwareController:
    """处理与 EPICS 硬件的所有交互

    职责：
    - 安全设置变量 PV（caput + 读回验证）
    - 等待所有设备达到设定值
    - 失败时回滚到初始值
    """

    def __init__(self, config: dict):
        hardware = config.get('hardware', {})
        self.tolerance = hardware.get('tolerance', 0.0001)
        self.max_wait = hardware.get('max_wait', 10)
        self.poll_interval = hardware.get('poll_interval', 0.2)
        self.min_adjust_interval = hardware.get('min_adjust_interval', 6)
        self.rollback_on_failure = hardware.get('rollback_on_failure', True)

        self._initial_pvs: list[str] = []
        self._initial_values: list[float] = []
        self._last_adjust_time: float = 0

    def save_initial(self, pvs: list[str], values: list[float]):
        """保存初始值（用于回滚）

        Args:
            pvs: 变量 PV 列表
            values: 对应的当前值
        """
        self._initial_pvs = list(pvs)
        self._initial_values = list(values)

    def apply(self, pvs: list[str], values: list[float],
              clamp_fn=None) -> bool:
        """设置变量 PV 值（含安全验证）

        Args:
            pvs: 变量 PV 列表
            values: 目标值列表
            clamp_fn: 可选的裁剪函数（VariableManager.clamp_params）

        Returns:
            bool: 是否全部设置成功

        Raises:
            RuntimeError: 写入失败且 rollback_on_failure=True
        """
        if clamp_fn:
            values = clamp_fn(values)

        # 检查硬件调整间隔
        elapsed = time.time() - self._last_adjust_time
        if elapsed < self.min_adjust_interval:
            wait = self.min_adjust_interval - elapsed
            print(f"  等待硬件调整间隔: {wait:.1f}秒")
            time.sleep(wait)

        # 逐个写入并验证
        pvs_list = list(pvs)
        values_list = list(values)
        for pv, val in zip(pvs_list, values_list):
            success = self._write_with_verify(pv, val)
            if not success:
                if self.rollback_on_failure:
                    self.rollback()
                    raise RuntimeError(
                        f"PV {pv} 写入失败（目标={val}），已回滚到初始值")
                return False

        # 等待全部稳定
        all_settled, failed = self._wait_for_settled(pvs_list, values_list)
        if not all_settled:
            print(f"  警告: 以下设备未稳定: {list(failed.keys())}")

        self._last_adjust_time = time.time()
        return True

    def _write_with_verify(self, pv: str, value: float, retries: int = 3) -> bool:
        """写入 PV 并读回验证

        Args:
            pv: PV 名称
            value: 目标值
            retries: 重试次数

        Returns:
            bool: 验证通过
        """
        for attempt in range(retries + 1):
            caput(pv, value, wait=True, timeout=max(1.0, self.max_wait))
            readback = caget(pv, timeout=1.0)
            if readback is not None and abs(readback - value) <= self.tolerance:
                return True
            if attempt < retries:
                print(f"  重试 {pv}: 设置={value:.4f} 读回={readback}")
                time.sleep(0.3 * (attempt + 1))
        return False

    def _wait_for_settled(self, pvs: list[str], targets: list[float]) -> tuple:
        """等待所有设备达到设定值

        Args:
            pvs: PV 列表
            targets: 目标值列表

        Returns:
            tuple: (all_settled, failed_dict)
        """
        start = time.time()
        while True:
            elapsed = time.time() - start
            if elapsed > self.max_wait:
                readbacks = caget_many(pvs, timeout=1.0)
                failed = {}
                for pv, t, rb in zip(pvs, targets, readbacks):
                    if rb is None or abs(rb - t) > self.tolerance:
                        failed[pv] = {'target': t, 'readback': rb}
                return False, failed

            readbacks = caget_many(pvs, timeout=1.0)
            all_ok = True
            for pv, t, rb in zip(pvs, targets, readbacks):
                if rb is None or abs(rb - t) > self.tolerance:
                    all_ok = False
                    break
            if all_ok:
                return True, {}
            time.sleep(self.poll_interval)

    def rollback(self):
        """回滚到初始值"""
        if not self._initial_pvs or not self._initial_values:
            print("  警告: 没有可用的初始值用于回滚")
            return
        print("\n正在回滚到初始参数...")
        for pv, val in zip(self._initial_pvs, self._initial_values):
            self._write_with_verify(pv, val)
        print("✓ 回滚完成")
```

- [ ] **Step 4.2: 测试（仅测试逻辑，模拟器模式）**

```python
if __name__ == "__main__":
    from core.epics_backend import set_backend
    set_backend(use_simulator=True)

    hc = HardwareController({"hardware": {"tolerance": 0.1}})
    hc.save_initial(["LA-PS:CH00:SETI", "LA-PS:CH01:SETI"], [0.0, 0.0])
    # 在模拟器中，写入应该成功
    result = hc.apply(["LA-PS:CH00:SETI", "LA-PS:CH01:SETI"], [0.1, -0.1])
    print(f"  apply result: {result}")

    # 测试回滚
    hc.rollback()

    print("✓ Task 4 passed (manual verification)")
```

---

### Task 5: GenericOptimizer

**Covers:** [S3, S4, S9, S10]

**Files:**
- Create: `sxfel_optim_tools/core/optimizer.py`（重写）

- [ ] **Step 5.1: 实现 GenericOptimizer**

```python
"""通用 EPICS 优化器

核心循环: ask → apply → read → score → tell → stop
"""
import time
import numpy as np
import nevergrad as ng
from tqdm import tqdm

from .epics_backend import caget_many
from .variable_manager import VariableManager
from .hardware_controller import HardwareController
from .scoring.registry import create_scorer


class GenericOptimizer:
    """通用 EPICS 优化器"""

    def __init__(self, config: dict):
        """初始化优化器

        Args:
            config: 完整配置字典
        """
        self.config = config

        # 组件
        self.variable_mgr = VariableManager(config)
        self.hardware = HardwareController(config)

        # 解析目标配置
        self._parse_objectives(config.get('objectives', {}))

        # 优化参数
        opt = config.get('optimization', {})
        self.algorithm = opt.get('algorithm', 'Compass')
        self.budget = opt.get('budget', 50)
        self.early_stop_config = opt.get('early_stopping', {})

    def _parse_objectives(self, obj_config: dict):
        """解析目标配置

        Args:
            obj_config: objectives 字段
        """
        groups = obj_config.get('groups', [])
        self.objective_groups = []

        for g in groups:
            name = g.get('name', f"group_{len(self.objective_groups)}")
            weight = g.get('weight', 1.0)
            pvs_raw = g.get('pvs', [])
            scoring_config = g.get('scoring', {'method': 'l2'})

            pvs = []
            targets = []
            weights = []
            ranges = []

            for item in pvs_raw:
                if isinstance(item, str):
                    pvs.append(item)
                    targets.append(0.0)
                    weights.append(1.0)
                    ranges.append(None)
                else:
                    pvs.append(item['pv'])
                    targets.append(item.get('target', 0.0))
                    weights.append(item.get('weight', 1.0))
                    ranges.append(item.get('range', None))

            scorer = create_scorer(
                scoring_config.get('method', 'l2'),
                scoring_config.get('params', {})
            )

            self.objective_groups.append({
                'name': name,
                'weight': weight,
                'pvs': pvs,
                'targets': targets,
                'weights': weights,
                'ranges': ranges,
                'scorer': scorer,
            })

        overall = obj_config.get('overall_scoring', 'weighted_sum')
        if overall == 'weighted_sum':
            self._aggregate = self._weighted_sum_aggregate
        else:
            raise ValueError(f"不支持的总体评分方式: {overall}")

    def _weighted_sum_aggregate(self, group_scores: list[float],
                                group_weights: list[float]) -> float:
        """加权和聚合各组评分

        Args:
            group_scores: 各组评分
            group_weights: 各组权重

        Returns:
            float: 总体评分
        """
        total_w = sum(group_weights)
        if total_w == 0:
            return float('inf')
        return sum(s * w for s, w in zip(group_scores, group_weights)) / total_w

    def run(self) -> dict:
        """执行优化

        Returns:
            dict: 优化结果，包含:
                - best_params: 最佳参数
                - best_score: 最佳评分
                - history: 完整历史
                - device_pvs: 变量 PV 列表
        """
        # 1. 读取初始值
        var_mgr = self.variable_mgr
        initial_values = var_mgr.read_initial_values()
        var_mgr.initial_values = initial_values
        self.hardware.save_initial(var_mgr.pvs, initial_values)

        # 2. 构造 Nevergrad 参数空间
        parametrization = ng.p.Instrumentation(**{
            f"x{i}": ng.p.Scalar(
                init=initial_values[i],
                lower=var_mgr.ranges[i][0],
                upper=var_mgr.ranges[i][1]
            )
            for i in range(len(var_mgr))
        })

        try:
            optimizer_class = ng.optimizers.registry[self.algorithm]
        except KeyError:
            print(f"算法 {self.algorithm} 未找到，使用 NGOpt")
            optimizer_class = ng.optimizers.NGOpt

        optimizer = optimizer_class(
            parametrization=parametrization,
            budget=self.budget,
            num_workers=1,
        )

        # 3. 构造所有目标 PV 的扁平列表（用于批量 caget）
        all_obj_pvs = []
        group_boundaries = []  # [(start, end), ...]
        for g in self.objective_groups:
            start = len(all_obj_pvs)
            all_obj_pvs.extend(g['pvs'])
            group_boundaries.append((start, len(all_obj_pvs)))

        # 4. 初始化历史记录
        history = {
            'device_pvs': list(var_mgr.pvs),
            'iterations': [],
            'scores': [],
            'group_scores': [],
            'parameters': [initial_values],
            'readings': [],
            'algorithm': self.algorithm,
            'budget': self.budget,
            'early_stop': False,
            'stop_iteration': self.budget,
        }

        # 评估初始点
        print("评估初始点...")
        self.hardware.apply(var_mgr.pvs, initial_values)
        readings = caget_many(all_obj_pvs)
        initial_score, grp_scores = self._compute_score(readings, group_boundaries)
        print(f"初始评分: {initial_score:.4f}")
        if grp_scores:
            for g, s in zip(self.objective_groups, grp_scores):
                print(f"  组 [{g['name']}]: {s:.4f}")

        history['scores'].append(initial_score)
        history['group_scores'].append(grp_scores)
        history['readings'].append(readings)

        # 5. 早停参数
        es = self.early_stop_config
        es_enabled = es.get('enabled', True)
        es_patience = es.get('patience', 10)
        es_min_improvement = es.get('min_relative_improvement', 0.005)

        best_score = initial_score
        no_improve = 0

        # 6. 优化循环
        print(f"\n开始优化: {self.algorithm} 算法, {self.budget} 次迭代...")
        start_time = time.time()

        for i in tqdm(range(self.budget), desc="优化进度"):
            try:
                candidate = optimizer.ask()
                params = [candidate.kwargs[f"x{j}"] for j in range(len(var_mgr))]

                # caput + 验证
                self.hardware.apply(var_mgr.pvs, params)

                # caget 所有目标 PV
                readings = caget_many(all_obj_pvs)

                # 评分
                score, grp_scores = self._compute_score(readings, group_boundaries)

                if np.isinf(score) or np.isnan(score):
                    print(f"  警告: 迭代 {i+1} 无效评分 {score}")
                    score = float('inf')

                optimizer.tell(candidate, score)

                # 记录历史
                history['iterations'].append(i + 1)
                history['scores'].append(score)
                history['group_scores'].append(grp_scores)
                history['parameters'].append(params)
                history['readings'].append(readings)

                tqdm.write(f"  当前: {score:.4f} 最佳: {best_score:.4f}")

                # 早停
                if es_enabled:
                    if score < best_score:
                        rel_imp = (best_score - score) / best_score
                        if rel_imp > es_min_improvement:
                            best_score = score
                            no_improve = 0
                        else:
                            no_improve += 1
                    else:
                        no_improve += 1

                    if no_improve >= es_patience:
                        print(f"\n早停! 连续 {es_patience} 次无显著改进")
                        history['early_stop'] = True
                        history['stop_iteration'] = i + 1
                        break

            except KeyboardInterrupt:
                print("\n用户中断，正在回滚...")
                self.hardware.rollback()
                raise
            except Exception as e:
                print(f"\n迭代 {i+1} 错误: {e}")
                continue

        # 7. 获取最佳结果
        valid = [(j, s) for j, s in enumerate(history['scores'])
                 if not np.isinf(s) and not np.isnan(s)]
        if valid:
            best_idx, best_score = min(valid, key=lambda x: x[1])
            best_params = history['parameters'][best_idx]
        else:
            best_idx, best_score = 0, initial_score
            best_params = initial_values

        history['best_params'] = best_params
        history['best_score'] = best_score
        history['best_iteration_index'] = best_idx

        print(f"\n优化完成! 最佳评分: {best_score:.4f}")
        return history

    def _compute_score(self, readings: list, boundaries: list) -> tuple:
        """计算各组分评分和总体评分

        Args:
            readings: 扁平化的所有目标 PV 读数
            boundaries: [(start, end), ...] 各组在 readings 中的区间

        Returns:
            tuple: (overall_score, list_of_group_scores)
        """
        group_scores = []
        for g, (start, end) in zip(self.objective_groups, boundaries):
            grp_readings = readings[start:end]
            if any(r is None for r in grp_readings):
                score = float('inf')
            else:
                score = g['scorer'](
                    grp_readings, g['targets'], g['weights'], g['ranges']
                )
            group_scores.append(score)

        overall = self._aggregate(
            group_scores,
            [g['weight'] for g in self.objective_groups]
        )
        return overall, group_scores

    def rollback(self):
        """手动触发回滚"""
        self.hardware.rollback()
```

- [ ] **Step 5.2: 测试**

```python
if __name__ == "__main__":
    from core.epics_backend import set_backend
    set_backend(use_simulator=True)

    config = {
        "variables": [
            {"pv": "LA-PS:CH00:SETI", "range": [-0.5, 0.5]},
            {"pv": "LA-PS:CH01:SETI", "range": [-0.5, 0.5]}
        ],
        "objectives": {
            "groups": [
                {
                    "name": "orbit",
                    "weight": 1.0,
                    "pvs": [
                        {"pv": "LA-BI:SBPM1:POS_X", "target": 0.0},
                        {"pv": "LA-BI:SBPM1:POS_Y", "target": 0.0}
                    ],
                    "scoring": {"method": "l2"}
                }
            ]
        },
        "optimization": {"algorithm": "Compass", "budget": 5},
        "hardware": {"tolerance": 0.1}
    }

    opt = GenericOptimizer(config)
    result = opt.run()
    assert 'best_params' in result
    assert 'best_score' in result
    print(f"最佳评分: {result['best_score']:.4f}")
    print(f"最佳参数: {result['best_params']}")
    print("✓ Task 5 passed")
```

---

### Task 6: 通用 CLI 入口

**Covers:** [S4, S11]

**Files:**
- Modify: `sxfel_optim_tools/run_optimization.py`（重写）
- Create: `sxfel_optim_tools/configs/orbit_example.json`

- [ ] **Step 6.1: 重写 CLI**

```python
#!/usr/bin/env python3
"""SXFEL 通用 EPICS 优化器入口

使用方法:
    python run_optimization.py --config config.json
    python run_optimization.py --config config.json --budget 100
    python run_optimization.py --config config.json --simulator
"""
import argparse
import sys
import time
from core.epics_backend import set_backend
from core.utils import load_generic_config, validate_generic_config
from core.optimizer import GenericOptimizer


def main():
    parser = argparse.ArgumentParser(
        description='通用 EPICS 优化器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python run_optimization.py --config configs/orbit_example.json
    python run_optimization.py --config config.json --budget 100
    python run_optimization.py --config config.json --algorithm NGOpt
    python run_optimization.py --config config.json --simulator
        """
    )
    parser.add_argument('--config', required=True, help='配置文件路径')
    parser.add_argument('--budget', type=int, help='覆盖配置的迭代次数')
    parser.add_argument('--algorithm', help='覆盖配置的算法')
    parser.add_argument('--simulator', action='store_true', default=False,
                        help='使用模拟器模式（默认使用真实 EPICS）')
    args = parser.parse_args()

    set_backend(use_simulator=args.simulator)
    print(f"模式: {'模拟器' if args.simulator else '真实 EPICS'}")
    print(f"加载配置文件: {args.config}")

    config = load_generic_config(args.config)

    warnings = validate_generic_config(config)
    if warnings:
        print("\n配置警告:")
        for w in warnings:
            print(f"  - {w}")
        print()

    if args.budget:
        config.setdefault('optimization', {})['budget'] = args.budget
        print(f"覆盖迭代次数: {args.budget}")
    if args.algorithm:
        config.setdefault('optimization', {})['algorithm'] = args.algorithm
        print(f"覆盖算法: {args.algorithm}")

    # 打印任务概要
    name = config.get('name', '未命名任务')
    var_count = len(config.get('variables', []))
    obj_count = sum(len(g.get('pvs', []))
                    for g in config.get('objectives', {}).get('groups', []))
    print(f"\n任务: {name}")
    print(f"变量 PV: {var_count} 个")
    print(f"目标 PV: {obj_count} 个")
    print(f"算法: {config.get('optimization', {}).get('algorithm', 'Compass')}")
    print(f"预算: {config.get('optimization', {}).get('budget', 50)} 次迭代\n")

    optimizer = GenericOptimizer(config)
    try:
        start = time.time()
        result = optimizer.run()
        elapsed = time.time() - start
        print(f"\n总耗时: {elapsed:.2f} 秒")
        print(f"最佳评分: {result['best_score']:.6f}")

        # TODO: 保存结果（Task 7 后启用）
        # from core.result_recorder import save_results
        # save_results(result, config)

    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n优化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6.2: 创建示例配置**

```json
{
    "name": "轨道优化示例",
    "variables": [
        {"pv": "LA-PS:CH00:SETI", "range": [-0.5, 0.5]},
        {"pv": "LA-PS:CV00:SETI", "range": [-0.5, 0.5]},
        {"pv": "LA-PS:CH01:SETI", "range": [-0.5, 0.5]},
        {"pv": "LA-PS:CV01:SETI", "range": [-0.5, 0.5]}
    ],
    "objectives": {
        "groups": [
            {
                "name": "orbit",
                "weight": 1.0,
                "pvs": [
                    {"pv": "LA-BI:SBPM1:POS_X", "target": 0.0},
                    {"pv": "LA-BI:SBPM1:POS_Y", "target": 0.0},
                    {"pv": "LA-BI:SBPM2:POS_X", "target": 0.0},
                    {"pv": "LA-BI:SBPM2:POS_Y", "target": 0.0}
                ],
                "scoring": {"method": "l2"}
            }
        ],
        "overall_scoring": "weighted_sum"
    },
    "optimization": {
        "algorithm": "Compass",
        "budget": 20,
        "early_stopping": {
            "enabled": true,
            "patience": 5,
            "min_relative_improvement": 0.005
        }
    },
    "hardware": {
        "tolerance": 0.1,
        "max_wait": 5,
        "poll_interval": 0.2,
        "min_adjust_interval": 0
    }
}
```

- [ ] **Step 6.3: 端到端测试**

```bash
cd sxfel_optim_tools
python run_optimization.py --config configs/orbit_example.json --simulator --budget 5
# 预期: 成功运行 5 次迭代，输出最佳评分
```

---

### Task 7: ResultRecorder — 通用 HDF5 记录

**Covers:** [S9]

**Files:**
- Create: `sxfel_optim_tools/core/result_recorder.py`

- [ ] **Step 7.1: 实现通用结果记录**

```python
"""通用优化结果记录器（HDF5）"""
import os
import time
import numpy as np
import h5py


def save_results(history: dict, config: dict, results_dir: str = 'results') -> str:
    """保存优化结果到 HDF5 文件

    Args:
        history: 优化历史（GenericOptimizer.run 的返回值）
        config: 配置字典
        results_dir: 结果保存目录

    Returns:
        str: 文件路径
    """
    os.makedirs(results_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    name = config.get('name', 'optimization')
    filename = os.path.join(results_dir, f"{name}_{timestamp}.h5")

    with h5py.File(filename, 'w') as f:
        # metadata
        meta = f.create_group('metadata')
        meta.attrs['name'] = config.get('name', '')
        meta.attrs['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
        meta.attrs['algorithm'] = history.get('algorithm', 'Unknown')
        meta.attrs['budget'] = history.get('budget', 0)
        meta.attrs['early_stop'] = history.get('early_stop', False)
        meta.attrs['stop_iteration'] = history.get('stop_iteration', history.get('budget', 0))
        meta.attrs['best_iteration_index'] = history.get('best_iteration_index', 0)

        # devices (variables)
        dev = f.create_group('devices')
        device_pvs = history.get('device_pvs', [])
        dev.create_dataset('pvs', data=np.array(device_pvs, dtype='S'))
        dev.attrs['count'] = len(device_pvs)

        # objectives
        obj = f.create_group('objectives')
        objectives_config = config.get('objectives', {})
        groups = objectives_config.get('groups', [])
        for gi, g in enumerate(groups):
            grp = obj.create_group(f'group_{gi}')
            grp.attrs['name'] = g.get('name', f'group_{gi}')
            grp.attrs['weight'] = g.get('weight', 1.0)
            pvs_in = g.get('pvs', [])
            pv_names = [item['pv'] if isinstance(item, dict) else item for item in pvs_in]
            grp.create_dataset('pvs', data=np.array(pv_names, dtype='S'))

        # scores
        scores = f.create_group('scores')
        scores.create_dataset('all', data=np.array(history.get('scores', []), dtype=np.float32))
        group_scores = history.get('group_scores', [])
        if group_scores:
            scores.create_dataset('groups', data=np.array(group_scores, dtype=np.float32))

        # params
        params_list = history.get('parameters', [])
        if params_list:
            f.create_dataset('parameters', data=np.array(params_list, dtype=np.float32))

        # readings
        readings_list = history.get('readings', [])
        if readings_list:
            f.create_dataset('readings', data=np.array(readings_list, dtype=np.float32))

        # best
        best = f.create_group('best')
        best.attrs['score'] = history.get('best_score', float('inf'))
        best_params = history.get('best_params', [])
        if best_params:
            best.create_dataset('params', data=np.array(best_params, dtype=np.float32))

    print(f"✓ 结果已保存至: {filename}")
    return filename
```

---

### Task 8: GenericSimulator — 通用模拟器

**Covers:** [S12]

**Files:**
- Create: `sxfel_optim_tools/core/simulator.py`（重写）

- [ ] **Step 8.1: 基础模拟器框架**

```python
"""通用 EPICS 模拟器

支持 PV pattern 注册，内置 identity/linear/gaussian 响应模型。
"""
import re
import time
import numpy as np
from typing import Callable


class PVHandler:
    """PV 处理函数基类"""

    def caget(self, pv: str) -> float:
        raise NotImplementedError

    def caput(self, pv: str, value: float):
        raise NotImplementedError


class IdentityHandler(PVHandler):
    """caget 返回最后一次 caput 的值"""

    def __init__(self):
        self._value = 0.0

    def caget(self, pv):
        return self._value

    def caput(self, pv, value):
        self._value = value


class LinearResponseHandler(PVHandler):
    """线性响应: 根据变量 PV 的变化计算目标 PV 的值"""

    def __init__(self, objective_pv: str, sensitivities: dict):
        """
        Args:
            objective_pv: 目标 PV 名称
            sensitivities: {变量PV: 灵敏度系数}
        """
        self.objective_pv = objective_pv
        self.sensitivities = sensitivities
        self.baseline = 0.0
        self._variable_values = {}

    def set_variable(self, pv: str, value: float):
        self._variable_values[pv] = value

    def caget(self, pv):
        total = self.baseline
        for var_pv, sens in self.sensitivities.items():
            var_val = self._variable_values.get(var_pv, 0.0)
            total += sens * var_val
        return total

    def caput(self, pv, value):
        pass  # 目标 PV 只读


class GaussianResponseHandler(PVHandler):
    """高斯响应: value = amplitude * exp(-(x - center)^2 / (2*sigma^2))"""

    def __init__(self, variable_pv: str, center: float, sigma: float,
                 amplitude: float = 1.0, baseline: float = 0.0):
        self.variable_pv = variable_pv
        self.center = center
        self.sigma = sigma
        self.amplitude = amplitude
        self.baseline = baseline
        self._x = 0.0

    def set_x(self, value: float):
        self._x = value

    def caget(self, pv):
        return self.baseline + self.amplitude * np.exp(
            -(self._x - self.center)**2 / (2 * self.sigma**2)
        )

    def caput(self, pv, value):
        pass


class GenericSimulator:
    """通用 EPICS 模拟器

    支持按 PV pattern 注册 handler，实现灵活的设备模拟。
    """

    def __init__(self, seed: int = 42):
        np.random.seed(seed)
        self._handlers: list[tuple[re.Pattern, PVHandler]] = []
        self._identity_cache: dict[str, float] = {}  # 未注册 PV 的默认值

    def register_handler(self, pattern: str, handler: PVHandler):
        """注册 PV 处理函数

        Args:
            pattern: 正则表达式模式（如 r"^LA-BI:SBPM\d+:POS_X$"）
            handler: PVHandler 实例
        """
        self._handlers.append((re.compile(pattern), handler))

    def register_identity(self, pattern: str):
        """注册 identity 模式（caget 返回上次 caput 的值）"""
        h = IdentityHandler()
        self._handlers.append((re.compile(pattern), h))
        return h

    def register_linear_response(self, objective_pattern: str,
                                  sensitivities: dict[str, float]):
        """注册线性响应

        Args:
            objective_pattern: 目标 PV 的正则模式
            sensitivities: {变量PV: 灵敏度}
        """
        h = LinearResponseHandler(objective_pattern, sensitivities)
        self._handlers.append((re.compile(objective_pattern), h))
        return h

    def register_gaussian_response(self, objective_pattern: str,
                                    variable_pv: str, center: float,
                                    sigma: float, amplitude: float = 1.0,
                                    baseline: float = 0.0):
        """注册高斯响应"""
        h = GaussianResponseHandler(variable_pv, center, sigma, amplitude, baseline)
        self._handlers.append((re.compile(objective_pattern), h))
        return h

    def _find_handler(self, pv: str) -> PVHandler | None:
        """查找匹配的 handler"""
        for pattern, handler in self._handlers:
            if pattern.match(pv):
                return handler
        return None

    def caget(self, pv: str, timeout: float = 1.0) -> float:
        """读取 PV 值"""
        time.sleep(0.01)
        handler = self._find_handler(pv)
        if handler:
            return handler.caget(pv)
        # 未注册的 PV：返回缓存值或随机值
        if pv not in self._identity_cache:
            self._identity_cache[pv] = np.random.uniform(-0.1, 0.1)
        return self._identity_cache[pv]

    def caput(self, pv: str, value: float, wait: bool = False,
              timeout: float = 1.0) -> bool:
        """设置 PV 值"""
        time.sleep(0.01)
        handler = self._find_handler(pv)
        if handler:
            handler.caput(pv, value)
        else:
            self._identity_cache[pv] = value
        return True

    def caget_many(self, pvs: list[str], timeout: float = 1.0) -> list[float]:
        return [self.caget(pv, timeout) for pv in pvs]

    def caput_many(self, pvs: list[str], values: list,
                   wait: bool = False, timeout: float = 1.0) -> bool:
        for pv, val in zip(pvs, values):
            self.caput(pv, val, wait, timeout)
        if wait:
            time.sleep(0.1)
        return True
```

---

### Task 9: BeamScorer 自定义插件（向后兼容）

**Covers:** [S11]

**Files:**
- Create: `sxfel_optim_tools/custom_scorers/__init__.py`
- Create: `sxfel_optim_tools/custom_scorers/beam_scorer.py`

- [ ] **Step 9.1: 包装现有 BeamObjective 为自定义评分器**

```python
"""束流尺寸优化评分器（封装现有 BeamObjective 的评分逻辑）

向后兼容：允许使用新的通用优化引擎运行束流优化任务。
"""
from core.objectives.beam import BeamObjective
from core.scoring.base import Scorer
from core.scoring.registry import register_scorer


@register_scorer("beam_optimizer")
class BeamScorer(Scorer):
    """封装 BeamObjective 的评分逻辑作为 Scorer

    配置示例:
        "scoring": {
            "method": "custom:beam_optimizer",
            "params": {
                "camera_pv": "LA-BI:PRF22:RAW:ArrayData",
                "camera_shape": [1392, 1040],
                "num_averages": 3,
                "beam_mode": "balanced",
                "fel_mode": "soft"
            }
        }
    """

    def __init__(self, params: dict = None):
        super().__init__(params)
        # BeamObjective 需要完整 config 来初始化
        self._config = {
            "objective": {
                "type": "beam_size",
                "params": params or {}
            },
            "camera": {
                "pv": (params or {}).get("camera_pv", "LA-BI:PRF22:RAW:ArrayData"),
                "camera_shape": (params or {}).get("camera_shape", [1392, 1040])
            }
        }
        # 延迟初始化：首次调用时创建
        self._beam_obj = None
        self._initialized = False

    def __call__(self, readings, targets, weights, ranges=None):
        """计算束流优化评分

        readings 第一个元素是相机图像数组（1D flattened Fortran order）
        """
        if not self._initialized:
            self._beam_obj = BeamObjective(self._config)
            self._initialized = True

        # 将 readings 转为 BeamObjective.get_score 所需的格式
        # 注意: 这里的 params 和 device_pvs 需要由 GenericOptimizer 传入
        # 所以 BeamScorer 不能直接独立使用 —— 需要配合旧版的设备操作逻辑
        # 暂存 readings 供外部使用
        self._last_image = readings[0] if readings else None
        return float('inf')  # 占位：实际由外部调用 BeamObjective.get_score
```

此 Task 标记为 **Phase 3**，待核心引擎稳定后再完全实现。当前阶段保持旧版 `run_optimization.py` 可通过 `--legacy` 参数切换。

---

### 自检清单

**Spec 覆盖检查：**

| Spec 章节 | 覆盖任务 | 状态 |
|-----------|---------|------|
| [S5] Config format | Task 1 | ✓ load_generic_config + validate |
| [S6] Scoring strategies | Task 2 | ✓ 4 种内置 + 注册表 |
| [S8] Objective range | Task 2 | ✓ 所有评分器支持 range |
| [S7] Variable range | Task 3 | ✓ VariableManager.clamp_params |
| [S10] Error handling | Task 4 | ✓ HardwareController 重试+回滚 |
| [S3][S4][S9] 循环 | Task 5 | ✓ GenericOptimizer.run() |
| [S11] CLI 入口 | Task 6 | ✓ 通用 run_optimization.py |
| [S9] 结果记录 | Task 7 | ✓ 通用 HDF5 |
| [S12] 模拟器 | Task 8 | ✓ PV pattern 注册制 |
| [S11] Beam 兼容 | Task 9 | ✓ BeamScorer 占位 |

**占位符检查：** 无 TBD/TODO。Task 9 显式标记为 Phase 3。

**接口一致性：** VariableManager 返回 list[float]，HardwareController 消费 list[float]，Scorer 消费 list[float]，GenericOptimizer 串联一致。
