# 优化器多算法后端实施计划

> 日期: 2026-06-24
> 环境: Python 3.8 (conda, `epics-opt` 环境)
> 目标: scipy 多算法 + SQLite 存储重写

## Python 3.8 兼容性约束

- 类型注解使用 `typing` 模块：`Dict[str, Type]` 而非 `dict[str, type]`
- 函数返回类型注释用 comment syntax：`# type: (...) -> ReturnType`
- 不使用 walrus operator `:=`（3.8 支持但保持保守）
- f-string 可用（3.6+）

## Step 0: 环境准备

```bash
conda create -n epics-opt python=3.8 -y
conda activate epics-opt
pip install -r requirements.txt
# 安装可选依赖（推荐，提供 5 种算法）
pip install nevergrad>=0.5.0
```

## 依赖变更

`requirements.txt`：

```
numpy>=1.20.0
scipy>=1.7.0
matplotlib>=3.5.0,<3.8
pyepics>=3.5.0

# 可选：高级优化算法（未安装时自动降级到 scipy DE，并提醒用户）
# nevergrad>=0.5.0

# 可选：贝叶斯优化（如安装则使用 skopt，否则使用项目内实现）
# scikit-optimize>=0.9.0
```

必需 4 个（Phase 1）：`numpy` / `scipy` / `matplotlib` / `pyepics`
可选 2 个：`nevergrad`（NGOpt/CMA）、`scikit-optimize`（Bayesian，可选）
移除：`h5py`（换 SQLite）、`gradio`（UI 后续重写）、`tqdm`（全程用内置纯文本进度条）

**贝叶斯优化策略**：
- 安装了 `scikit-optimize`：使用 `gp_minimize` 实现
- 未安装：使用项目内自定义的贝叶斯优化实现（基于高斯过程，无外部依赖）

### EPICS 路由

pyepics 必装（`pyepics>=3.5.0`），但代码默认走模拟器路由。正式运行时改一行代码即可切换到真实 EPICS。

## 算法矩阵

### Phase 1（本次实现）

| 后端 | 算法名 | 函数 | 定位 |
|------|--------|------|------|
| scipy（默认）| `de` / `differential_evolution` | `differential_evolution` | 默认全局探索 |
| scipy（默认）| `nelder-mead` | `minimize(method='Nelder-Mead')` | 全局搜索后精调 |

### Phase 2（后续实现）

| 后端 | 算法名 | 函数 | 定位 |
|------|--------|------|------|
| Nevergrad（可选）| `ngopt` | `NGOpt` | 元算法 |
| Nevergrad（可选）| `cma` | `CMA` | 收敛最快 |

### Phase 3（重点实现）

| 后端 | 算法名 | 函数 | 定位 |
|------|--------|------|------|
| 自定义（可选）| `bayesian` | 项目内实现的贝叶斯优化 | 贝叶斯优化（无外部依赖） |
| skopt（可选）| `bayesian` | `gp_minimize` | 贝叶斯优化（需安装 scikit-optimize） |

## 可调参数

通过 `optimization.algorithm_params` 段可选覆盖，不写就用默认值。

### Differential Evolution

| 参数 | 默认 | 说明 |
|------|------|------|
| `popsize` | 15 | 种群大小 |
| `tol` | 0.01 | 收敛容差 |

### Nelder-Mead

| 参数 | 默认 | 说明 |
|------|------|------|
| `xatol` | 0.0001 | 参数容差 |
| `fatol` | 0.0001 | 函数值容差 |

### Bayesian (gp_minimize)

| 参数 | 默认 | 说明 |
|------|------|------|
| `noise` | 0.1 | 硬件测量噪声水平 |
| `n_initial_points` | min(10, budget/2) | 初始随机探索点数 |
| `kappa` | 1.96 | 探索-利用权衡 |

配置示例：

```jsonc
"optimization": {
    "algorithm": "bayesian",
    "budget": 50,
    "algorithm_params": { "noise": 0.1, "n_initial_points": 5 }
}
```

## 路由逻辑

```
--algorithm 值                                后端             未安装时
───────────────────────────────────────────────────────────────────
(不指定) | de | differential_evolution → scipy DE               (始终可用)
nelder-mead                        → scipy Nelder-Mead          (始终可用)
bayesian                           → skopt gp_minimize           (降级到 DE)
ngopt | cma                        → Nevergrad                  (降级到 DE)
```

**降级提醒**：当 Nevergrad 未安装时，用户选择 `ngopt` 或 `cma` 算法，系统会：
1. 打印警告：`"警告: Nevergrad 未安装，ngopt/cma 算法不可用，自动降级到 differential_evolution"`
2. 自动降级到 scipy DE 继续运行
3. 不会中断优化流程

## SQLite 存储方案

替换 `core/result_recorder.py` 和 `h5py`。所有运行存单文件 `results/optimizations.db`。

所有数组数据（params、readings、group_scores）统一用 `zlib` 压缩后存 BLOB：

```python
import zlib, json

def pack(v):    return zlib.compress(json.dumps(v).encode())
def unpack(b):  return json.loads(zlib.decompress(b))
```

标量压缩后约 30 bytes，图像（65536 float）压缩比 ~20x（1MB → 50KB）。

```sql
CREATE TABLE runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    config_name   TEXT NOT NULL,
    config_json   TEXT,
    algorithm     TEXT NOT NULL,
    budget        INTEGER NOT NULL,
    initial_score REAL,
    best_score    REAL,
    best_params   BLOB,             -- pack([val1, ...])
    best_readings BLOB,             -- pack([val1, ...])
    best_iter     INTEGER,
    early_stop    INTEGER DEFAULT 0,
    stop_iter     INTEGER,
    elapsed_sec   REAL,
    timestamp     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE variables (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id   INTEGER NOT NULL REFERENCES runs(run_id),
    pv_name  TEXT NOT NULL,
    pv_min   REAL,
    pv_max   REAL
);

CREATE TABLE objectives (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL REFERENCES runs(run_id),
    pv_name    TEXT NOT NULL,
    target     REAL DEFAULT 0.0,
    weight     REAL DEFAULT 1.0,
    group_name TEXT
);

-- 新增。把 readings 数组位置映射到 PV
CREATE TABLE group_mapping (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES runs(run_id),
    reading_index INTEGER NOT NULL,               -- 在 readings 数组中的位置
    pv_name       TEXT NOT NULL,
    target        REAL DEFAULT 0.0
);

CREATE TABLE iterations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL REFERENCES runs(run_id),
    iteration    INTEGER NOT NULL,                -- 0 = 初始点
    score        REAL,
    group_scores BLOB,                            -- pack([g1, g2, ...])
    params       BLOB,                            -- pack([x0, x1, ...])
    readings     BLOB,                            -- pack([pv0, pv1, ...])
    elapsed_ms   REAL                             -- 本轮耗时
);

CREATE TABLE failure_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(run_id),
    iteration   INTEGER NOT NULL,
    pv_name     TEXT NOT NULL,
    target_val  REAL,
    error_msg   TEXT,
    timestamp   TEXT DEFAULT (datetime('now'))
);
```

设计要点：

| 决策 | 理由 |
|------|------|
| iteration=0 为初始点 | 解决历史 inconsistency，scores/params/readings 长度对齐 |
| 统一 zlib 压缩 | 不分标量/数组，代码一条路径 |
| `group_mapping` 独立表 | reading_index → pv_name + target，查询时无需解析 config_json |
| `params` + `readings` 都压 | 8 个 float 的 params 压完约 60 bytes，可忽略开销 |

## 已知问题修复

### Fix 1: 默认算法 NGopt 未装报错

`__init__` 中硬编码 `algorithm = 'NGOpt'`，未装 Nevergrad 时路由失败。

```python
# 修复：根据可用后端设置默认算法
opt = config.get('optimization', {})
if _HAS_NEVERGRAD:
    self.algorithm = opt.get('algorithm', 'NGOpt')
else:
    self.algorithm = opt.get('algorithm', 'differential_evolution')
```

**降级提醒实现**：在 `optimizer.py` 的 `run()` 方法中，当检测到算法不可用时：

```python
# Nevergrad 降级提醒
if self.algorithm in ('ngopt', 'cma') and not _HAS_NEVERGRAD:
    print(f"  警告: Nevergrad 未安装，{self.algorithm} 算法不可用，自动降级到 differential_evolution")
    self.algorithm = 'differential_evolution'
```

### Fix 2: group_mapping 去重索引映射

`_build_pv_index` 对目标 PV 去重后，readings 数组长度可能小于 objectives PV 总数。`group_mapping` 的 `reading_index` 必须对应去重后的索引。

```python
# result_recorder 中构建 group_mapping 时：
for g_idx, g in enumerate(objective_groups):
    for pv_idx, pv in enumerate(g['pvs']):
        reading_index = group_indices[g_idx][pv_idx]  # 去重后的实际位置
        cur.execute("INSERT INTO group_mapping VALUES (NULL,?,?,?,?)",
                     (run_id, reading_index, pv, g['targets'][pv_idx]))
```

### Fix 3: run_ui.py / tools/plot_results.py 兼容

`run_ui.py` 已删除（gradio 不可用）。`tools/plot_results.py` 依赖 matplotlib + 不存在的 `core.results` 模块。需加 try/except 兼容：

```python
# tools/plot_results.py 顶部
try:
    import matplotlib.pyplot as plt
    _HAS_MATPLOTLIB = True
except ImportError:
    print("matplotlib 未安装，可视化不可用 (pip install matplotlib)")
    _HAS_MATPLOTLIB = False
```

### Fix 4: 初始值越界校验

`var_mgr.read_initial_values()` 读回 EPICS 当前值，可能超出搜索范围。在 `__init__` 中 clip 到边界内：

```python
# 在 run() 中，读取 initial_values 之后
for i, val in enumerate(initial_values):
    lo, hi = var_mgr.ranges[i]
    if val < lo:
        print(f"  警告: {var_mgr.pvs[i]} 初始值 {val:.4f} < 下界 {lo:.4f}，裁剪到 {lo:.4f}")
        initial_values[i] = lo
    elif val > hi:
        print(f"  警告: {var_mgr.pvs[i]} 初始值 {val:.4f} > 上界 {hi:.4f}，裁剪到 {hi:.4f}")
        initial_values[i] = hi
```

### Fix 5: 写入值 NaN/Inf 安全检查

优化器可能传入无效浮点数（如评分为 inf 时的参数），直接写入硬件危险。

```python
# hardware_controller.py apply() 入口处
import math
for pv, val in zip(pvs, values):
    if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
        print(f"  跳过 {pv}: 值 {val} 无效（NaN/Inf）")
        failure_log.append((iteration, pv, val, "NaN/Inf value"))
        continue
    # 正常 caput...
```

## 实施阶段

### Phase 1: 核心实现（本次）
- `core/algorithms/registry.py` — 注册表
- `core/algorithms/de.py` — Differential Evolution（scipy）
- `core/algorithms/nelder_mead.py` — Nelder-Mead（scipy）

### Phase 2: 可选算法（后续）
- `core/algorithms/nevergrad.py` — NGOpt / CMA（可选）

### Phase 3: 贝叶斯优化（重点，最后实现）
- `core/algorithms/bayesian.py` — 贝叶斯优化
  - 优先使用 `scikit-optimize`（如已安装）
  - 未安装时使用项目内自定义实现

## 算法插件架构

和现有 `scoring/` / `transforms/` 一致，用装饰器注册：

```
core/algorithms/
├── __init__.py       # import 所有子模块触发注册
├── registry.py       # @register_algorithm + get_algorithm()
├── de.py             # Differential Evolution
├── nelder_mead.py    # Nelder-Mead
├── nevergrad.py      # NGOpt / CMA（可选, Phase 2）
├── bayesian.py       # 贝叶斯优化（Phase 3, 重点）
```

接口定义（所有算法均为黑盒优化，不需要梯度信息）：

```python
# core/algorithms/registry.py
from typing import Dict, List, Type

_registry = {}  # type: Dict[str, Type]

def register_algorithm(*names):
    """注册算法。可注册多个别名。"""
    def decorator(cls):
        for n in names:
            _registry[n] = cls
        return cls
    return decorator

def get_algorithm(name):
    # type: (str) -> Type
    """按名称查找算法，未找到返回 None。"""
    return _registry.get(name)

def list_algorithms():
    # type: () -> List[str]
    return list(_registry.keys())
```

```python
# core/algorithms/de.py
@register_algorithm("differential_evolution", "de")
class DEAlgorithm:
    def run(self, objective, bounds, budget, params, history, progress_fn) -> dict:
        """
        Args:
            objective: callable(x) -> float
            bounds: [(lo, hi), ...]
            budget: 最大迭代次数
            params: algorithm_params dict
            history: History 对象（由调用者创建，objective 函数负责追加迭代数据）
            progress_fn: callable(score, best_score) 进度输出
        Returns:
            history: History 对象（原始对象，已就地更新）
        """
        ...
```

`run()` 中的分发逻辑简化为：

```python
algo_cls = get_algorithm(self.algorithm)
if algo_cls is None:
    print(f"算法 {self.algorithm} 未知，使用 DE")
    algo_cls = get_algorithm("de")

algo = algo_cls()
history = algo.run(objective, bounds, self.budget, self.algorithm_params, history, print)
```

**加新算法**：写一个文件 + `@register_algorithm("my_algo")`，不改 optimizer.py。

## 改动清单

### 1. `requirements.txt`

- 移除 `h5py`、`gradio`
- Phase 1 必需：`numpy`、`scipy`、`matplotlib`、`pyepics`
- Phase 2 可选：`nevergrad>=0.5.0`
- Phase 3 可选：`scikit-optimize>=0.9.0`（如安装则使用 skopt，否则使用项目内实现）

### 2. `core/optimizer.py`

- **移除 tqdm 兼容层**：删除 try/import tqdm 代码块，全程使用 `sys.stdout.write` 纯文本进度条
- **Fix 1**: `__init__` 根据 `_HAS_NEVERGRAD` 设置默认算法（NGOpt → differential_evolution）
- **Fix 1 降级提醒**: `run()` 中检测算法不可用时打印警告并降级到 DE
- **Fix 4**: `run()` 中读取 initial_values 后做边界裁剪
- `run()`: 通过 `get_algorithm()` 查找算法类，分发到 `algo.run()`
- **耗时追踪**: 每轮迭代记录 `elapsed_ms` 到 history，运行结束时 `elapsed_sec` 写入总耗时
- **初始点修正**: iteration=0 为初始点，readings 在初始评估时即写入 history
- history 中 `params` / `readings` / `group_scores` 统一为原始 list（result_recorder 负责序列化+压缩）
- 删除 `_run_scipy_de()` / `_run_scipy_nm()` / `_run_bayesian()` / `_run_nevergrad()` 方法，全部迁移到 `core/algorithms/` 插件

### 2b. `core/algorithms/`（新增目录）

**Phase 1（本次）**：
- `registry.py`: `@register_algorithm` 装饰器 + `get_algorithm()` / `list_algorithms()`
- `de.py`: `DEAlgorithm`（scipy differential_evolution）
- `nelder_mead.py`: `NelderMeadAlgorithm`（scipy minimize）

**Phase 2（后续）**：
- `nevergrad.py`: `NevergradAlgorithm`（NGOpt / CMA，可选）

**Phase 3（重点）**：
- `bayesian.py`: `BayesianAlgorithm`（优先使用 skopt，未安装时使用项目内实现）

### 3. `core/result_recorder.py`（重写）

- HDF5 → SQLite，用 `sqlite3` 标准库
- `save_run()` / `save_iteration()` / `save_failure()` 写入接口
- `query_runs()` / `query_iterations()` 读取接口
- **Fix 2**: 构建 group_mapping 时用 `group_indices` 去重后的索引，非原始 pvs 索引
- 新增 `failure_log` 表（iteration, pv_name, target_val, error_msg）

### 3b. `core/hardware_controller.py`

- `apply()` 入口处检查每个 value 是否为合法 float（拒绝 NaN/Inf），不合法则跳过该 PV 并记录到 failure_log
- `apply()` 中 caput 失败时，通过回调通知 optimizer 记录到 history 的 `failure_log` 列表
- 不直接依赖 result_recorder（解耦）

### failure_log 写入流程

```
hardware_controller.apply()
    ↓ 检测到 NaN/Inf 或 caput 失败
    ↓ 追加到 history['failure_log'] 列表
    ↓
optimizer.run() 循环结束后
    ↓ 调用 result_recorder.save_failure(run_id, failure_log)
    ↓
result_recorder 写入 SQLite failure_log 表
```

hardware_controller 只负责收集，optimizer 负责汇总后一次性写入。这样 hardware_controller 不需要知道 SQLite 的存在。

### 3c. `tools/plot_results.py`（兼容处理）

- **Fix 3**: matplotlib 加 try/except 兼容，不可用时打印提示而非崩溃

> `run_ui.py` 已删除。

### 5. 验证

#### Phase 1 验证（DE + Nelder-Mead）

```bash
conda activate epics-opt

# DE 算法（默认）
python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 30

# Nelder-Mead 算法（预期陷在局部极小）
python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 30 --algorithm nelder-mead

# 降级测试（Nevergrad 未安装时）
python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 5 --algorithm ngopt
# 预期输出: "警告: Nevergrad 未安装，ngopt 算法不可用，自动降级到 differential_evolution"

# 查询结果
sqlite3 results/optimizations.db "SELECT run_id, algorithm, best_score, elapsed_sec FROM runs;"
```

#### Phase 2 验证（Nevergrad，后续）

```bash
# Nevergrad 算法（需安装 nevergrad）
python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 30 --algorithm ngopt
```

#### Phase 3 验证（Bayesian，重点）

```bash
# Bayesian 算法（优先使用 skopt，未安装时使用项目内实现）
python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 30 --algorithm bayesian

# 验证降级行为
# - 安装了 scikit-optimize：使用 gp_minimize
# - 未安装：使用项目内贝叶斯优化实现
```

## Phase 1b: 架构重构

> 前置：Phase 1 代码已跑通，DE + Nelder-Mead + 降级 + SQLite 均正常。
> 目标：将 `optimizer.py`（304 行，6 职责耦合）拆分为 4 个独立模块。
> 约束：所有算法（DE/NM/Nevergrad/Bayesian）均为黑盒优化，不需要梯度信息。

### 设计原则

1. **最小拆解**：只拆职责明确的单元，不引入未经验证的抽象
2. **双向不依赖**：新模块不 import 旧模块，旧模块仅通过注入使用新模块
3. **完整 to_dict()**：History 序列化为 result_recorder 所需的全部字段，`save_results` 签名不变
4. **可验证**：每步修改后可独立跑通回归测试
5. **无梯度**：所有算法（DE、NM、Nevergrad CMA/NGOpt、Bayesian）均为黑盒优化，不需要梯度信息。`ObjectiveFunction.__call__(x) → float` 只需返回标量评分。

### 重构范围

```
core/
├── history.py          # History: 类型化迭代记录
├── objective.py        # ObjectiveFunction: callable(x) → score
├── problem.py          # OptimizationProblem: 数据容器 + compute_score
├── optimizer.py        # GenericOptimizer: 编排层（~80 行）
├── result_recorder.py  # 重写：单连接批量写入
└── 其余文件不动
```

**不动的文件**：hardware_controller、variable_manager、epics_backend、simulator、scoring/、transforms/、configs/、run_optimization.py

**修改的文件**：algorithms/de.py（seed=None）、algorithms/nelder_mead.py（简化迭代）

### 1. `core/problem.py` — OptimizationProblem

**纯数据容器**，不做解析。`_parse_objectives` 保留在 optimizer.py 中，将解析结果注入 Problem。

```python
class OptimizationProblem:
    """优化问题定义（不可变）"""

    def __init__(self, objective_groups: list, all_obj_pvs: list,
                 group_indices: list, aggregate_fn):
        self.objective_groups = objective_groups
        self._all_obj_pvs = all_obj_pvs
        self._group_indices = group_indices
        self._aggregate = aggregate_fn

    @property
    def all_obj_pvs(self) -> list[str]:
        return self._all_obj_pvs

    @property
    def group_indices(self) -> list[list[int]]:
        return self._group_indices

    def compute_score(self, readings: list, caget_fn) -> tuple:
        """计算各组分评分和总体评分"""
        group_scores = []
        for g, indices in zip(self.objective_groups, self._group_indices):
            grp_readings = []
            for pi, (idx, tr) in enumerate(zip(indices, g['transforms'])):
                raw = readings[idx]
                if tr is not None:
                    tlist = tr if isinstance(tr, list) else [tr]
                    for t in tlist:
                        raw = t(raw, pv_name=g['pvs'][pi], caget_fn=caget_fn)
                grp_readings.append(raw)

            if any(r is None for r in grp_readings):
                score = float('inf')
            else:
                score = g['scorer'](grp_readings, g['targets'], g['weights'], g['ranges'])
            group_scores.append(score)

        overall = self._aggregate(group_scores, [g['weight'] for g in self.objective_groups])
        return overall, group_scores
```

### 2. `core/history.py` — History

类型化容器。**`to_dict()` 包含 result_recorder 所需全部字段**（含 `_groups`、`_group_indices`）。

```python
class History:
    """迭代记录容器"""

    def __init__(self, device_pvs: list, initial_values: list,
                 algorithm: str, budget: int,
                 objective_groups: list, group_indices: list):
        self.device_pvs = list(device_pvs)
        self.initial_values = list(initial_values)
        self.algorithm = algorithm
        self.budget = budget

        self.iterations = []
        self.scores = []
        self.group_scores = []
        self.parameters = []
        self.readings = []
        self.elapsed_ms_list = []
        self.failures = []
        self.elapsed_sec = 0.0
        self.best_score = float('inf')
        self.best_params = None
        self.best_readings = None
        self.best_iteration_index = 0
        self.early_stop = False
        self.stop_iteration = budget

        self._groups_raw = [
            {'pvs': g['pvs'], 'targets': g['targets']}
            for g in objective_groups
        ]
        self._group_indices = group_indices

    def add_initial(self, score: float, group_scores: list):
        self.iterations.append(0)       # iteration=0 = 初始点
        self.scores.append(score)
        self.group_scores.append(group_scores)
        self.parameters.append(self.initial_values)
        self.readings.append([])        # 初始点无 readings
        self.elapsed_ms_list.append(0.0)

    def append(self, iteration: int, score: float, group_scores: list,
               params: list, readings: list, elapsed_ms: float):
        self.iterations.append(iteration)
        self.scores.append(score)
        self.group_scores.append(group_scores)
        self.parameters.append(params)
        self.readings.append(readings)
        self.elapsed_ms_list.append(elapsed_ms)

    def update_best(self):
        valid = [(i, s) for i, s in enumerate(self.scores)
                 if s is not None and s < float('inf')]
        if valid:
            self.best_iteration_index, self.best_score = min(valid, key=lambda x: x[1])
            self.best_params = self.parameters[self.best_iteration_index]
            self.best_readings = self.readings[self.best_iteration_index] if self.best_iteration_index < len(self.readings) else None

    def to_dict(self) -> dict:
        return {
            'device_pvs': self.device_pvs,
            'iterations': self.iterations,
            'scores': self.scores,
            'group_scores': self.group_scores,
            'parameters': self.parameters,
            'readings': self.readings,
            'elapsed_ms_list': self.elapsed_ms_list,
            'failure_log': self.failures,
            'elapsed_sec': self.elapsed_sec,
            'algorithm': self.algorithm,
            'budget': self.budget,
            'early_stop': self.early_stop,
            'stop_iteration': self.stop_iteration,
            'best_score': self.best_score,
            'best_params': self.best_params,
            'best_readings': self.best_readings,
            'best_iteration_index': self.best_iteration_index,
            '_groups': self._groups_raw,
            '_group_indices': self._group_indices,
        }
```

**关键**：`_groups` 和 `_group_indices` 包含在内，`result_recorder.save_results(history.to_dict(), config)` 可直接使用，签名不出 `group_indices` 参数。

### 3. `core/objective.py` — ObjectiveFunction

从 `_make_objective` 闭包提取为类。所有算法均为黑盒优化，不需要梯度信息，`__call__` 只返回标量评分。

```python
class ObjectiveFunction:
    """优化目标函数 — callable(x) -> float（黑盒，无梯度）"""

    def __init__(self, hw, problem, history, var_pvs, progress_fn):
        self.hw = hw
        self.problem = problem
        self.history = history
        self.var_pvs = var_pvs
        self.progress_fn = progress_fn
        self.iteration = 0

    def __call__(self, x) -> float:
        self.iteration += 1
        t0 = time.time()

        values = x.tolist() if hasattr(x, 'tolist') else list(x)

        self.hw.apply(self.var_pvs, values,
                      iteration=self.iteration,
                      failure_log=self.history.failures)

        readings = caget_many(self.problem.all_obj_pvs)
        score, grp_scores = self.problem.compute_score(readings, caget)

        if np.isinf(score) or np.isnan(score):
            score = float('inf')

        elapsed_ms = (time.time() - t0) * 1000
        self.history.append(self.iteration, score, grp_scores, values, readings, elapsed_ms)

        self.progress_fn(score, self.history.best_score)
        return score
```

### 4. `core/optimizer.py` — 编排层（~80 行）

`_parse_objectives` 保留在此，结果注入 Problem 和 History。

```python
def _resolve_algorithm(algorithm_name: str, has_nevergrad: bool) -> str:
    """解析算法名称，处理默认值和降级"""
    defaults = ('NGOpt' if has_nevergrad else 'differential_evolution')
    return algorithm_name or defaults


class GenericOptimizer:
    """编排器"""

    def __init__(self, config: dict):
        self.config = config

        self.variable_mgr = VariableManager(config)
        self.hardware = HardwareController(config)

        # 解析 objectives（保留在 optimizer 中）
        self.objective_groups = self._parse_objectives(config.get('objectives', {}))
        self._build_pv_index()  # 就地设置 self._all_obj_pvs, self._group_indices
        aggregate_fn = self._weighted_sum_aggregate

        self.problem = OptimizationProblem(
            self.objective_groups, self._all_obj_pvs,
            self._group_indices, aggregate_fn
        )

        opt = config.get('optimization', {})
        self.algorithm = _resolve_algorithm(opt.get('algorithm', ''), _HAS_NEVERGRAD)
        self.algorithm_params = opt.get('algorithm_params', {})
        self.budget = opt.get('budget', 50)

    # _parse_objectives, _build_pv_index, _weighted_sum_aggregate 保持不变

    @property
    def all_obj_pvs(self) -> list[str]:
        """兼容旧接口 (run_optimization.py)"""
        return self.problem.all_obj_pvs

    def run(self) -> dict:
        var_mgr = self.variable_mgr
        initial_values = var_mgr.read_initial_values()
        var_mgr.initial_values = initial_values
        self.hardware.save_initial(var_mgr.pvs, initial_values)

        # Fix 4: 边界裁剪
        for i, val in enumerate(initial_values):
            lo, hi = var_mgr.ranges[i]
            if val < lo:
                initial_values[i] = lo
            elif val > hi:
                initial_values[i] = hi

        # Fix 1: Nevergrad 降级提醒
        if self.algorithm in ('ngopt', 'cma') and not _HAS_NEVERGRAD:
            print(f"  警告: Nevergrad 未安装，{self.algorithm} 算法不可用，自动降级到 differential_evolution")
            self.algorithm = 'differential_evolution'

        history = History(var_mgr.pvs, initial_values, self.algorithm, self.budget,
                          self.objective_groups, self._group_indices)

        print("评估初始点...")
        readings = caget_many(self.problem.all_obj_pvs)
        initial_score, grp_scores = self.problem.compute_score(readings, caget)
        print(f"初始评分: {initial_score:.4f}")
        history.add_initial(initial_score, grp_scores)

        objective = ObjectiveFunction(self.hardware, self.problem, history,
                                      var_mgr.pvs, self._default_progress)

        algo_cls = get_algorithm(self.algorithm)
        if algo_cls is None:
            print(f"算法 {self.algorithm} 未知，使用 DE")
            algo_cls = get_algorithm("de")

        algo = algo_cls()
        bounds = [(r[0], r[1]) for r in var_mgr.ranges]

        start = time.time()
        algo.run(objective, bounds, self.budget, self.algorithm_params, history, print)
        history.elapsed_sec = time.time() - start
        history.update_best()

        print(f"\n优化完成! 最佳评分: {history.best_score:.4f}")
        return history.to_dict()

    def rollback(self):
        self.hardware.rollback()
```

### 5. `core/algorithms/de.py` — 修复 seed

```python
result = spo.differential_evolution(
    objective, bounds, maxiter=budget,
    seed=None,          # ← 改为 None（计划 L27: 每次随机）
    callback=None,      # ← 移除无操作 callback
    tol=params.get('tol', 0.01),
    polish=False,
)
```

### 6. `core/algorithms/nelder_mead.py` — 修复迭代计数

NM 无法与 objective 内部的迭代计数器（`self.iteration`）通信。改用简单方案：追踪 objective 调用次数，不做 maxiter 猜测。

```python
def run(self, objective, bounds, budget, params, history, progress_fn):
    xatol = params.get('xatol', 0.0001)
    fatol = params.get('fatol', 0.0001)

    initial = history.parameters[0] if history.parameters else \
              [(b[0] + b[1]) / 2.0 for b in bounds]
    x0 = np.array(initial, dtype=float)

    count_before = len(history.iterations)

    res = spo.minimize(
        objective, x0, method='Nelder-Mead',
        options={'maxiter': budget, 'xatol': xatol, 'fatol': fatol, 'disp': False}
    )

    count_after = len(history.iterations)
    print("  NM 完成: 实际 {} 次函数调用".format(count_after - count_before))
    return history
```

### 7. `core/result_recorder.py` — 批量写入

`save_results` 签名不变。单连接 + executemany。

```python
def save_results(history_dict: dict, config: dict, results_dir='results') -> str:
    conn = _get_conn()
    try:
        _init_tables(conn)
        run_id = _save_run(conn, history_dict, config)
        _save_iterations_batch(conn, run_id, history_dict)
        _save_failures_batch(conn, run_id, history_dict)
        conn.commit()
    finally:
        conn.close()
    db_path = os.path.join(results_dir, 'optimizations.db')
    print(u"\u2713 结果已保存至: {}".format(db_path))
    return db_path
```

### 改动清单

| 文件 | 操作 | 行数 |
|------|------|------|
| `core/history.py` | **新建** | +110 |
| `core/objective.py` | **新建** | +45 |
| `core/problem.py` | **新建** | +45 |
| `core/optimizer.py` | **重写** 304→110 | -194 |
| `core/result_recorder.py` | **重写** 批量写入 | ~160 |
| `core/algorithms/de.py` | **修复** seed=None | ~3 |
| `core/algorithms/nelder_mead.py` | **修复** 简化迭代 | ~10 |
| `core/__init__.py` | **更新** 导出 | +3 |
| `run_optimization.py` | **不变** | 0 |

### 验证

```bash
# 重构后回归测试（用 test_benchmark.json 替换 orbit_example.json）
python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 30
python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 30 --algorithm nelder-mead
python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 5 --algorithm ngopt
# 预期: DE 从 ~233 降到 ~1-2；NM 陷在局部极小 ~180-200；降级警告打印 + 自动切 DE

# SQLite 验证
python -c "
from core.history import History
h = History(['pv1'], [0.5], 'de', 10, [], [])
h.add_initial(0.5, [0.5])
d = h.to_dict()
assert '_groups' in d and '_group_indices' in d
print('History.to_dict() OK')
"

# 查询结果
sqlite3 results/optimizations.db "SELECT run_id, algorithm, best_score, elapsed_sec FROM runs ORDER BY run_id DESC LIMIT 3;"
```
