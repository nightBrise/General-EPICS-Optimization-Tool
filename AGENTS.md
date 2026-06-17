# AGENTS.md — 通用 EPICS 优化工具箱

## 入口

```bash
pip install -r requirements.txt

# 模拟器模式（算法基准/调试）
python run_optimization.py --config configs/orbit_full.json --simulator -y
python run_optimization.py --config configs/beam_example.json --simulator -y

# 真实 EPICS 模式（默认）
python run_optimization.py --config my_config.json
```

CLI 流程：**确认 → 运行 → 摘要**。`-y` 跳过确认，`--simulator` 换模拟器，`--budget N` 覆盖迭代次数。

## 架构

```
config.json → GenericOptimizer → ask → apply → read → score → tell → repeat
                  │
   ┌──────────────┼──────────────┐
   │              │              │
VariableManager  HardwareCtrl  ScoringEngine
(51 行)          (130 行)      +Transforms
   │              │              │
   └──────────────┼──────────────┘
                  │
            EPICSBackend (278 行，单例)
             ├── pyepics (真实)
             └── TestFunctionSimulator (295 行，算法测试台)
```

- **`core/optimizer.py`** — GenericOptimizer，主循环。`_parse_objectives` 解析分组目标，`_build_pv_index` 去重 PV
- **`core/hardware_controller.py`** — caput + 读回验证 + 等待稳定 + 失败回滚。所有参数在 `hardware{}` 配置
- **`core/simulator.py`** — 4 个基准函数 (sphere/rosenbrock/rastrigin/ackley)，3 种输出模式 (scalar/vector/image)，已知极值
- **`core/scoring/`** — l2/l1/max/weighted_sum 内置评分 + `@register_scorer` 注册表
- **`core/transforms/`** — reshape/average/combine 内置变换 + `@register_transform` 注册表
- **`core/result_recorder.py`** — 通用 HDF5 存储
- **`core/variable_manager.py`** — 变量 PV 管理 + 边界裁剪
- **`core/utils.py`** — `load_generic_config` (支持 `//` 和 `#` 注释) + `validate_generic_config`
- **`core/epics_backend.py`** — 未改动，单例路由 + 重试机制

## 配置文件

所有配置在 `configs/` 目录，JSON + `//`/`#` 注释：

| 文件 | 用途 |
|------|------|
| `orbit_full.json` | 全零轨道（20 校正子 + 20 BPM） |
| `orbit_ref.json` | 参考轨道（同上 + 非零 target） |
| `orbit_example.json` | 快速入门（4 校正子 + 完整注释） |
| `beam_example.json` | 束流尺寸优化 (custom:beam_optimizer transform) |
| `test_bench_scalar.json` | 标量算法测试 (rosenbrock) |
| `test_bench_vector.json` | 向量算法测试 (sphere) |
| `transform_example.json` | 完整字段参考手册 |

核心配置段：`variables[]` (PV+range)、`objectives.groups[].pvs[]` (PV+target+weight+range+transform)、`optimization{}` (algorithm+budget+early_stop)、`hardware{}` (tolerance+max_wait+...)、`simulation{}` (function+mode+image)。

## 非显而易见的事实

- `set_simulator_config(config)` 必须在创建 `GenericOptimizer` **之前**调用（CLI 中第 203 行）。否则模拟器使用默认 sphere/scalar 模式。
- `custom_scorers/beam_scorer.py` 注册的是 `custom:beam_optimizer` **transform**（不是 scorer）。通过 import 该模块生效。
- `epics_backend._get_simulator()` 每次从模块读取 `_simulator` 全局变量（非缓存），支持热替换。
- 模拟器 image 模式的 `caget` 和 `caget_many` 都返回 1D Fortran 顺序 list（与真实 EPICS CCD 输出一致）。
- 配置文件中的 `hardware.min_adjust_interval` 默认为 6 秒——测试配置必须设为 0。
- `Compass` 算法名在 Nevergrad 中不存在（降级为 NGOpt 有提示）。
- `validateg_generic_config` 返回 `(errors, warnings)` — errors 非空时 CLI 直接 exit(1)。
- `average` transform 必须放在链首位。它通过 `caget_fn` 重读原始 PV 做逐元素平均。放在分析变换之后会导致类型不匹配。✓ `average → beam_optimizer`，✗ `beam_optimizer → average`。

## 扩展点

```python
# 自定义评分（在 objectives.groups[].scoring.method 中引用）
@register_scorer("my_scorer")
class MyScorer(Scorer):
    def __call__(self, readings, targets, weights, ranges=None) -> float: ...

# 自定义变换（在 objectives.groups[].pvs[].transform.type 中引用）
@register_transform("my_transform")
class MyTransform(Transform):
    def __call__(self, raw, *, pv_name="", caget_fn=None) -> float: ...
```

## Python 脚本模式

```python
from core.epics_backend import set_backend
from core.utils import load_generic_config
from core.optimizer import GenericOptimizer

set_backend(use_simulator=True)
import custom_scorers.beam_scorer  # 注册 custom:beam_optimizer

config = load_generic_config("configs/beam_example.json")
opt = GenericOptimizer(config)
result = opt.run()
```
