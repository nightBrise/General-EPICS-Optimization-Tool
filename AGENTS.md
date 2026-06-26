# AGENTS.md — 通用 EPICS 优化工具箱

## 入口

```bash
pip install -r requirements.txt

# 模拟器模式（算法基准/调试）
python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 30

# 真实 EPICS 模式（默认）
python run_optimization.py --config my_config.json
```

CLI 流程：**确认 → 运行 → 摘要 → 询问出图**。`-y` 跳过确认，`--simulator` 换模拟器，`--budget N` 覆盖迭代次数，`--algorithm X` 覆盖算法，`--plot` 自动出图。

## 架构

```
config.json → GenericOptimizer → ObjectiveFunction → HW + Score → repeat
                   │
   ┌──────────────┼──────────────┐
   │              │              │
VariableManager  HardwareCtrl  OptimizationProblem
                 (安全写入)   (PV索引+评分)
                   │
             EPICSBackend (单例)
              ├── pyepics (真实)
              └── TestFunctionSimulator (Griewank)
```

算法通过 `core/algorithms/` 插件分发，不修改 `optimizer.py`。

## 核心模块

| 文件 | 职责 |
|------|------|
| `core/optimizer.py` | 编排层：读初始值→创建 History→分发到算法插件 |
| `core/problem.py` | 优化问题定义：PV索引 + compute_score（含变换链） |
| `core/history.py` | 类型化迭代记录容器，`to_dict()` 供 result_recorder |
| `core/objective.py` | 黑盒目标函数：`__call__(x) → float` |
| `core/algorithms/` | 算法插件：DE / NM / NGOpt / CMA / Bayesian |
| `core/simulator.py` | Griewank 基准函数（偏移公式适配任意 N 变量） |
| `core/result_recorder.py` | SQLite 6 表存储（批量写入） |
| `core/hardware_controller.py` | caput + 读回验证 + NaN/Inf 检查 + 回滚 |
| `core/variable_manager.py` | 变量 PV 管理 + 边界裁剪 |
| `core/epics_backend.py` | 单例路由 + 重试机制 |

## 算法

| 算法 | 算法名 | 后端 | 调用方式 |
|------|--------|------|----------|
| Differential Evolution | `de` / `differential_evolution` | scipy | `--algorithm de` |
| Nelder-Mead | `nelder-mead` | scipy | `--algorithm nelder-mead` |
| NGOpt | `ngopt` / `NGOpt` | Nevergrad | `--algorithm ngopt`（需安装） |
| CMA | `cma` / `CMA` | Nevergrad | `--algorithm cma`（需安装） |
| Bayesian | `bayesian` | skopt → sklearn → DE | `--algorithm bayesian` |

Nevergrad 未安装时选择 ngopt/cma 自动降级到 DE（打印警告）。

## 配置文件

| 文件 | 用途 |
|------|------|
| `template.minimal.json` | **唯一入口模板**，复制即用 |
| `config_reference.json` | 完整字段参考手册（含 algorithm_params + simulation） |
| `orbit_example.json` | 轨道优化示例 |
| `beam_example.json` | 束流尺寸优化（含 transform 链） |
| `test_benchmark.json` | Griewank 10D 基准测试 |

## 非显而易见的事实

- `set_simulator_config(config)` 必须在创建 `GenericOptimizer` **之前**调用。否则模拟器默认使用 Griewank/scalar 模式，但 initial_values 为空。
- Griewank 全局最优使用偏移公式 `200 * ((i * 137 + 53) % 13 - 6)`，不在搜索空间中心 [0,0,...,0]，防止 NGOpt 从起点直接命中最优。
- `simulation.initial_values` 字段：配置中的初始值，在 `TestFunctionSimulator.__init__` 中设置，先于 `var_mgr.read_initial_values()` 调用。
- Bayesian 算法三级降级：skopt → sklearn GP + EI → DE。当前环境 sklearn 已装，路径 B 直接可用。
- `hardware.min_adjust_interval` 默认为 6 秒——测试配置必须设为 0。
- 项目无测试套件、无 CI、无 linter/typechecker。验证通过 `--simulator` 模式手动运行。
- `save_results()` 返回 `(db_path, run_id)`，CLI 打印 run_id 后询问是否出图。
- 结果可视化：`tools/plot_results.py` 生成 2×3 布局 6 张图，全英文标注。

## 扩展点

```python
# 自定义算法（不改 optimizer.py）
# core/algorithms/my_algo.py
from .registry import register_algorithm

@register_algorithm("my_algo")
class MyAlgoAlgorithm:
    def run(self, objective, bounds, budget, params, history, progress_fn):
        # objective(x) → float (黑盒，无需梯度)
        # history.append(...) 自动记录
        ...

# 自定义评分（在 objectives.groups[].scoring.method 中引用）
@register_scorer("my_scorer")
class MyScorer(Scorer):
    def __call__(self, readings, targets, weights, ranges=None) -> float: ...

# 自定义变换（在 objectives.groups[].pvs[].transform.type 中引用）
@register_transform("my_transform")
class MyTransform(Transform):
    def __call__(self, raw, *, pv_name="", caget_fn=None) -> float: ...
```
