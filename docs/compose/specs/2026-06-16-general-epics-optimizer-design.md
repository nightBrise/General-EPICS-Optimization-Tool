# [S1] 通用 EPICS 优化器设计

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/general-epics-optimizer.md)

日期: 2026-06-16
状态: v1 待实施

## [S2] 动机

现有优化工具紧耦合 SXFEL 装置的束流/轨道优化场景，`BeamObjective`(1198行) 集评分、EPICS交互、步长管理于一身。新增优化场景需要写新的 Objective 子类并在多处添加 if/else 分支。

目标：将优化引擎泛化为**纯配置驱动的通用 EPICS 优化器**，用户可以只改 JSON 配置就适配新的加速器优化场景。

## [S3] 核心设计哲学

通用 EPICS 优化器 = 一个纯粹的循环：

```
caput(变量PV) → wait(稳定) → caget(目标PV) → score(读数, 目标) → tell(Nevergrad)
```

全部由配置驱动，无需写 Python 代码。

## [S4] 架构

```
                    config.json
                         │
            ┌────────────┴────────────┐
            │     GenericOptimizer    │
            │                         │
            │  VariableManager        │  ← 管理变量 PV + range + 初始值
            │  ScoringEngine          │  ← 分组评分策略
            │  OptimizerLoop          │  ← ask → apply → read → score → tell
            │  HardwareController     │  ← caput + 验证 + 等待 + 回滚
            │  ResultRecorder         │  ← 通用 HDF5 存储
            └─────────────────────────┘
```

## [S5] 配置文件格式

```jsonc
{
  "name": "优化任务名",

  // ========== 变量 PV（旋钮） ==========
  "variables": [
    {
      "pv": "LA-PS:CH00:SETI",
      "range": [-0.5, 0.5]    // Nevergrad 搜索边界
    }
  ],

  // ========== 目标 PV（被观测值） ==========
  "objectives": {
    // 分组：每组独立评分、独立量纲
    "groups": [
      {
        "name": "orbit",             // 组名（日志/调试用）
        "weight": 1.0,               // 组权重（参与总体评分）
        "pvs": [
          {
            "pv": "LA-BI:SBPM1:POS_X",
            "target": 0.0,            // 目标值（默认 0）
            "weight": 1.0,            // 组内权重（默认 1）
            "range": [-0.5, 0.5]      // 可接受区间（可选），超出才惩罚
          }
        ],
        "scoring": {
          "method": "l2",            // l2 | l1 | max | weighted_sum | custom:<name>
          "params": {}               // 策略参数（可选）
        }
      }
    ],
    "overall_scoring": "weighted_sum"  // 组间聚合方式
  },

  // ========== 优化参数 ==========
  "optimization": {
    "algorithm": "Compass",
    "budget": 100,
    "early_stopping": {
      "enabled": true,
      "patience": 10,
      "min_relative_improvement": 0.005
    }
  },

  // ========== 硬件控制参数 ==========
  "hardware": {
    "tolerance": 0.0001,
    "max_wait": 10,
    "poll_interval": 0.2,
    "min_adjust_interval": 6
  }
}
```

## [S6] 评分策略体系

### 内置策略

| 方法 | 公式 | 适用场景 |
|------|------|---------|
| `l2` | √[Σ(wᵢ·(rᵢ−tᵢ)²)/Σwᵢ] | 默认，平滑收敛 |
| `l1` | Σ(wᵢ·\|rᵢ−tᵢ\|)/Σwᵢ | 对离群点鲁棒 |
| `max` | max(wᵢ·\|rᵢ−tᵢ\|) | 压制最大偏差 |
| `weighted_sum` | Σwᵢ·(rᵢ−tᵢ)/Σwᵢ | 简单加权和 |

### 自定义策略

通过 `"method": "custom:<name>"` 引用注册的评分器：

```python
@register_scorer("beam_optimizer")
class BeamScorer:
    def __call__(self, readings, targets, weights, ranges, params):
        # readings: 组内目标 PV 的读数列表
        # params: scoring.params 字典
        # 返回 float
        ...
```

### 总体评分

`overall_scoring = "weighted_sum"`:
```
总评分 = (Σ 组权重 × 组评分) / Σ 组权重
```

每个组独立归一化，量纲隔离。

## [S7] 变量 PV 的 `range` 行为

- `range` 同时用于 Nevergrad 搜索空间边界和 caput 写入前的安全裁剪
- 首次迭代前自动读取各变量 PV 的当前值作为初始值（用于回滚）
- 写入时不依赖 `range` 校验，而是由 EPICS 后端自身处理边界（模拟器模式做边界裁剪）

## [S8] 目标 PV 的 `range`（可接受区间）

当目标 PV 配置了 `range`:
- 读数在 `[range[0], range[1]]` 内 → 该 PV 的贡献为 0（不惩罚）
- 读数超出 `range` → 按偏差归一化后惩罚
- 未配置 `range` → 总是按 `|reading - target|` 惩罚

## [S9] 优化循环流程

```
GenericOptimizer.run():
  1. 读取变量 PV 的当前值，保存为初始值（用于回滚）
  2. 初始化 Nevergrad 参数空间
  3. Loop i in 0..budget:
     a. candidate = optimizer.ask()
     b. hardware_ctrl.apply(variable_pvs, candidate_values)
          → 逐个 caput + 验证读回 + 等待稳定
     c. readings = caget_many(all_objective_pvs)
     d. 分组评分:
          for each group:
            group_readings = readings[group.indices]
            group_score = scorer(group_readings, group.targets, group.weights, group.ranges)
          total_score = weighted_sum of group_scores
     e. optimizer.tell(candidate, total_score)
     f. 记录历史 → 检查早停 → 继续/终止
  4. 返回最佳结果，保存 HDF5
```

## [S10] 错误处理

| 场景 | 行为 |
|------|------|
| PV 读取失败 | 重试 3 次 → 失败后 score=inf，继续迭代 |
| PV 写入失败 | 重试 3 次 → 失败后回滚到初始值，抛出异常 |
| 等待稳定超时 | 打印警告，score=inf 继续迭代 |
| score=inf/nan | 告知 Nevergrad，继续下一轮 |
| Ctrl+C | 自动回滚到初始值 |
| 连续 N 次无效 score | 自动终止（可配置阈值） |

## [S11] 向后兼容

- 现有 `config_beam.json` → 用 `custom:beam_scorer` 插件封装 BeamObjective 逻辑
- 现有 `config_orbit.json` → 直接用内置 `l2` 评分，无需自定义插件
- 旧版 CLI 参数 (`--mode`, `--simulator`) 保持兼容
- EPICS 后端 `core/epics_backend.py` 保持不变

## [S12] 模拟器通用化

模拟器改用 PV pattern 注册制：

```python
class GenericSimulator:
    def register_handler(self, pattern: str, handler: Callable):
        # glob pattern 匹配 PV 名
        ...

    def register_response(self, variable_pv: str, objective_pv: str,
                          response_type: str, params: dict):
        # 声明变量→目标的响应关系
        # response_type: "linear", "gaussian", "identity"
        ...
```

内置响应模型：
- `identity`: caget 返回最后一次 caput 的值
- `linear`: 目标 = 基线 + Σ(灵敏度 × 变量值)
- `gaussian`: 目标对变量呈高斯响应

现有的 SXFEL 模拟器（含束流图像生成）注册为 custom handler。

## [S13] 新目录结构

```
sxfel_optim_tools/
├── run_optimization.py          # 通用入口（精简，无类型分支）
├── core/
│   ├── optimizer.py             # GenericOptimizer（主循环）
│   ├── variable_manager.py      # 变量 PV 管理
│   ├── scoring/
│   │   ├── base.py              # Scorer 基类
│   │   ├── registry.py          # register_scorer 装饰器
│   │   ├── l2.py                # 内置评分策略
│   │   ├── l1.py
│   │   ├── max_score.py
│   │   └── weighted_sum.py
│   ├── hardware_controller.py   # caput + 验证 + 等待 + 回滚
│   ├── result_recorder.py       # 通用 HDF5 记录（取代 save_beam/save_orbit）
│   ├── simulator.py             # 通用模拟器（PV pattern 注册制）
│   └── epics_backend.py         # 保留（单例切换模式）
├── configs/                     # 新配置目录
│   ├── orbit_optimization.json
│   └── phase_tuning.json
└── custom_scorers/              # 自定义评分插件目录
    └── beam_scorer.py           # 封装现有 beam 计算逻辑
```
