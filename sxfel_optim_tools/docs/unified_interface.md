# 统一接口设计

## 概述

SXFEL 优化工具箱采用配置驱动的统一接口设计，通过目标函数注册机制，支持多种优化任务类型。

## 核心概念

### 目标函数注册机制

目标函数通过 `@register_objective` 装饰器注册到全局注册表：

```python
from core.objectives.base import BaseObjective, register_objective

@register_objective("my_objective")
class MyObjective(BaseObjective):
    def get_score(self, params, device_pvs):
        # 实现评分逻辑
        ...
```

### 创建目标函数

通过配置自动创建：

```python
from core.objectives.registry import create_objective

config = load_config("config.json")
objective_fn = create_objective(config)  # 根据 config['objective']['type'] 自动选择
```

## 添加新的目标函数

### 步骤 1: 编写目标函数类

创建新文件 `core/objectives/my_objective.py`：

```python
import numpy as np
from .base import BaseObjective, register_objective
from .metrics import metrics
from ..simulator import caget_many
from ..utils import safe_device_operation


@register_objective("my_objective")
class MyObjective(BaseObjective):
    """我的自定义目标函数"""

    def __init__(self, config):
        super().__init__(config)
        # 从 config['objective']['params'] 获取自定义参数
        self.my_param = self.params.get('my_param', default_value)

    def get_score(self, params, device_pvs):
        """评估参数评分（越小越好）

        Args:
            params: 设备参数列表
            device_pvs: 设备 PV 列表

        Returns:
            float: 评分值
        """
        # 1. 设置设备参数
        success = safe_device_operation(device_pvs, params, self.config)
        if not success:
            return float('inf')

        # 2. 获取数据
        readings = caget_many(self.read_pvs)

        # 3. 计算评分
        score = self._calculate_score(readings)

        # 4. 更新指标（可选，用于追踪）
        metrics.update({'score': score, 'readings': readings}, score)

        return score

    def _calculate_score(self, readings):
        """自定义评分逻辑"""
        # 实现具体评分算法
        return np.sum(np.array(readings)**2)
```

### 步骤 2: 注册目标函数

编辑 `core/objectives/__init__.py`：

```python
from .my_objective import MyObjective

# 确保在文件底部导入以触发注册
```

### 步骤 3: 创建配置文件

创建 `config_my.json`：

```json
{
  "name": "my_optimization",
  "description": "我的自定义优化任务",
  "objective": {
    "type": "my_objective",
    "read_pvs": ["PV1", "PV2"],
    "params": {
      "my_param": 123
    }
  },
  "devices": {
    "correctors": [
      {"pv": "DEVICE:PV:SETI", "range": [-1.0, 1.0]}
    ]
  },
  "optimization": {
    "algorithm": "Compass",
    "budget": 50
  }
}
```

### 步骤 4: 运行

```bash
python run_optimization.py --config config_my.json
```

## 目标函数基类

参考: [core/objectives/base.py](../../core/objectives/base.py)

```python
from abc import ABC, abstractmethod

class BaseObjective(ABC):
    """目标函数基类"""

    def __init__(self, config):
        self.config = config
        self.read_pvs = config['objective']['read_pvs']
        self.params = config['objective'].get('params', {})

    @abstractmethod
    def get_score(self, params, device_pvs):
        """评估参数，返回评分（越小越好）

        Args:
            params: 设备参数列表
            device_pvs: 设备 PV 列表

        Returns:
            float: 评分值
        """
        pass
```

## 注册表机制

参考: [core/objectives/registry.py](../../core/objectives/registry.py)

```python
OBJECTIVE_REGISTRY = {}

def register_objective(name):
    """装饰器：注册目标函数类"""
    def decorator(cls):
        OBJECTIVE_REGISTRY[name] = cls
        return cls
    return decorator

def create_objective(config):
    """根据配置创建目标函数实例"""
    obj_type = config['objective']['type']
    cls = OBJECTIVE_REGISTRY.get(obj_type)
    if cls is None:
        raise ValueError(
            f"未知目标类型: {obj_type}，可用: {list(OBJECTIVE_REGISTRY.keys())}"
        )
    return cls(config)

def get_registered_objectives():
    """获取所有已注册的目标函数"""
    return list(OBJECTIVE_REGISTRY.keys())
```

## 统一配置格式

所有优化任务使用统一的 JSON 配置文件：

```json
{
  "name": "任务名称",
  "description": "任务描述",
  "objective": {
    "type": "目标类型",
    "read_pvs": ["读取PV列表"],
    "params": {
      "自定义参数": "参数值"
    }
  },
  "devices": {
    "设备类型": [
      {"pv": "PV地址", "range": [最小值, 最大值]}
    ]
  },
  "optimization": {
    "algorithm": "Compass",
    "budget": 50,
    "early_stopping": {
      "enabled": true,
      "patience": 10,
      "min_relative_improvement": 0.005
    }
  }
}
```

## Nevergrad 算法参数

| 算法 | 说明 | 特有参数及默认值 | 配置示例 |
|------|------|----------|----------|
| NGOpt | 默认推荐算法 | 无 | `{"algorithm": "NGOpt"}` |
| Compass | 水平集算法 | 无 | `{"algorithm": "Compass"}` |
| CMA | 协方差矩阵适应 | population_size: 30 | `{"algorithm": "CMA"}` |
| PSO | 粒子群优化 | swarm_size: 50 | `{"algorithm": "PSO"}` |
| DE | 差分进化 | population_size: 30 | `{"algorithm": "DE"}` |
| TwoPointsDE | 两点差分进化 | population_size: 30 | `{"algorithm": "TwoPointsDE"}` |
| OnePlusOne | (1+1) 进化策略 | step_size: 0.5 | `{"algorithm": "OnePlusOne"}` |

配置文件中的算法参数示例：

```json
{
  "optimization": {
    "algorithm": "NGOpt",
    "budget": 50,
    "params": {
      "population_size": 30,
      "swarm_size": 50
    }
  }
}
```

## 工具函数

### safe_device_operation

安全地设置设备参数：

```python
from core.utils import safe_device_operation

success = safe_device_operation(device_pvs, params, config)
```

### caget_many

批量读取 EPICS PV：

```python
from core.simulator import caget_many

readings = caget_many(["PV1", "PV2", "PV3"])
```

### metrics

线程安全的指标追踪器：

```python
from core.objectives.metrics import metrics

# 更新当前指标
metrics.update({'key': value, ...}, score)

# 获取当前指标
current = metrics.get_current()

# 获取最佳指标
best = metrics.get_best()
```

## 优化器

参考: [core/optimizer.py](../../core/optimizer.py)

```python
from core.optimizer import Optimizer

optimizer = Optimizer(config, objective_fn)
best_params, best_score, device_pvs, history = optimizer.run()
```

## 已注册的目标函数

| 类型 | 说明 | 文件 |
|------|------|------|
| `beam_size` | 束流尺寸优化 | `core/objectives/beam.py` |
| `orbit` | 轨道优化（全0/参考） | `core/objectives/orbit.py` |

## 注意事项

### 线程安全

`EPICSBackend` 单例模式存在线程安全问题：`_use_simulator` 是类变量而非实例变量，多线程环境下可能产生竞态条件。如需在多线程环境使用，请注意同步。

### 测试覆盖

核心模块（objectives、optimizer、epics_backend 等）目前缺乏单元测试，修改代码时请注意回归测试。
