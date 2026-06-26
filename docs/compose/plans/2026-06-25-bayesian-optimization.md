# 贝叶斯优化 Phase 3 实施计划

> 日期: 2026-06-25
> 前置: Phase 1+1b+2 完成，DE/NM/NGOpt/CMA 四种算法已跑通
> 目标: 实现贝叶斯优化，支持双路径（skopt / 自定义），评估效果

## 设计目标

贝叶斯优化（BO）通过高斯过程代理模型 + 采集函数，在最少评估次数内逼近全局最优。特别适合 EPICS 场景中每次评估耗时长的特点。

### 三级降级策略

```
BayesianAlgorithm.run()
    │
    ├─ try: import skopt → 路径 A: skopt.gp_minimize()
    │   └─ 成熟库，自动 GP 建模 + 采集函数优化
    │
    ├─ except ImportError → try: import sklearn → 路径 B: 自定义实现
    │   └─ sklearn.GaussianProcessRegressor + 手写 EI 采集函数
    │
    └─ except ImportError → 路径 C: 降级到 DE
        └─ print 警告 → get_algorithm("de").run()
```

**当前环境**：`sklearn 1.3.2` 已装（通过 nevergrad），`skopt` 未装。路径 B 直接可用。

## 路径 A：skopt（优先）

| 项目 | 内容 |
|------|------|
| 库 | `scikit-optimize.gp_minimize` |
| 安装 | `pip install scikit-optimize>=0.9.0` |
| GP 核 | 自动 `Matern(nu=2.5) + WhiteKernel` |
| 采集函数 | `"EI"` / `"LCB"` / `"gp_hedge"` |
| 适配器 | bounds → `[Real(lo, hi), ...]` |

```python
def _run_skopt(self, objective, bounds, budget, params, history, progress_fn):
    import skopt

    dimensions = [skopt.space.Real(lo, hi) for lo, hi in bounds]
    acq = params.get('acq_func', 'EI')
    n_init = params.get('n_initial_points', min(10, budget // 2))
    xi = params.get('xi', 0.01)

    x0 = history.parameters if history.parameters else None
    y0 = history.scores if history.scores else None

    result = skopt.gp_minimize(
        objective, dimensions,
        n_calls=budget, n_initial_points=n_init,
        acq_func=acq, xi=xi,
        x0=x0, y0=y0,
        verbose=False,
    )
    return history
```

**适配要点**：skopt 的 `objective(x)` 期望 `x` 是一个 list（变量值）。`ObjectiveFunction.__call__` 已支持 list/numpy array。无需改动。

## 路径 B：自定义实现（回退方案）

### 代理模型

```python
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel

kernel = Matern(nu=2.5, length_scale=1.0, length_scale_bounds=(1e-2, 1e3))
kernel += WhiteKernel(noise_level=alpha, noise_level_bounds=(1e-5, 1e2))
gp = GaussianProcessRegressor(kernel=kernel, alpha=alpha, normalize_y=True,
                               n_restarts_optimizer=3)
```

### 采集函数：Expected Improvement (EI)

```python
from scipy.stats import norm

def _expected_improvement(mu, sigma, y_best, xi=0.01):
    with np.errstate(divide='ignore'):
        imp = y_best - mu - xi
        Z = imp / sigma
        ei = imp * norm.cdf(Z) + sigma * norm.pdf(Z)
        ei[sigma < 1e-9] = 0.0
    return ei
```

### 采集函数优化：随机采样 + top-N 精修

```python
import numpy as np

def _acq_optimize(gp, y_best, bounds, n_candidates=5000, xi=0.01):
    # 1. 随机采样
    dim = len(bounds)
    X_candidates = np.random.uniform(
        [b[0] for b in bounds],
        [b[1] for b in bounds],
        size=(n_candidates, dim)
    )
    # 2. GP 预测
    mu, sigma = gp.predict(X_candidates, return_std=True)
    # 3. 计算 EI
    ei = _expected_improvement(mu, sigma, y_best, xi=xi)
    # 4. 选最佳
    best_idx = np.argmax(ei)
    return X_candidates[best_idx].tolist()
```

### 主循环

```python
def _run_custom(self, objective, bounds, budget, params, history, progress_fn):
    alpha = params.get('alpha', 0.1)
    n_candidates = params.get('n_candidates', 5000)
    xi = params.get('xi', 0.01)

    X = np.array(history.parameters, dtype=float)
    y = np.array(history.scores, dtype=float)

    kernel = Matern(nu=2.5) + WhiteKernel(noise_level=alpha)
    gp = GaussianProcessRegressor(
        kernel=kernel, alpha=alpha, normalize_y=True, n_restarts_optimizer=3)

    for _ in range(budget):
        gp.fit(X, y)
        x_next = _acq_optimize(gp, y.min(), bounds, n_candidates, xi)
        objective(x_next)
        X = np.array(history.parameters, dtype=float)
        y = np.array(history.scores, dtype=float)

    return history
```

**注意**：每次迭代调用 `objective(x)` 后，`history` 自动追加新数据。下一轮 `gp.fit(X, y)` 使用更新后的全部数据。

## 可调参数（`algorithm_params`）

| 参数 | 默认 | 路径 | 说明 |
|------|------|------|------|
| `acq_func` | `"EI"` | A | skopt 采集函数：EI / LCB / gp_hedge |
| `alpha` | 0.1 | A+B | GP 观测噪声标准差 |
| `xi` | 0.01 | A+B | EI 改进阈值（越大探索越强） |
| `n_initial_points` | `min(10, budget/2)` | A | skopt 初始随机探索点数 |
| `n_candidates` | 5000 | B | 自定义采集优化的随机采样数 |

## 与现有架构集成

```python
@register_algorithm("bayesian")
class BayesianAlgorithm:
    def run(self, objective, bounds, budget, params, history, progress_fn):
        try:
            import skopt
            return self._run_skopt(objective, bounds, budget, params, history, progress_fn)
        except ImportError:
            pass

        try:
            from sklearn.gaussian_process import GaussianProcessRegressor
            return self._run_custom(objective, bounds, budget, params, history, progress_fn)
        except ImportError:
            print("  警告: Bayesian 算法需要 scikit-learn，降级到 differential_evolution")
            from .registry import get_algorithm
            return get_algorithm("de")().run(objective, bounds, budget, params, history, progress_fn)
```

## 实施步骤

1. **安装 skopt**
   ```bash
   conda activate epics-opt
   pip install scikit-optimize>=0.9.0
   ```

2. **创建 `core/algorithms/bayesian.py`**
   - 路径 A：`_run_skopt` (~30 行)
   - 路径 B：`_run_custom` (~40 行)
   - EI 采集函数 (~10 行)
   - 采集优化器 (~15 行)

3. **更新 `core/algorithms/__init__.py`**
   ```python
   from . import bayesian
   ```

4. **验证路径 A**（skopt 已安装）
   ```bash
   python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 50 --algorithm bayesian
   ```

5. **验证路径 B**（skopt 未安装时回退）
   ```bash
   # 临时卸载 skopt 后测试
   pip uninstall scikit-optimize -y
   python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 50 --algorithm bayesian
   ```

6. **对比所有算法**
   ```bash
   for algo in de nelder-mead ngopt cma bayesian; do
       python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 50 --algorithm $algo
   done
   ```

## 预期结果（Griewank 10D, 50 budget）

| 算法 | 预期初始 ~1000 | 预计最佳 | 特点 |
|------|---------------|----------|------|
| DE | → | 0.5 — 2 | 全局搜索 |
| NM | → | 100 — 300 | 局部极小 |
| NGOpt | → | 1 — 3 | 自适应元算法 |
| CMA | → | 3 — 50 | 预算不足 |
| **Bayesian (skopt)** | → | **1 — 5** | GP-EI |
| **Bayesian (custom)** | → | **1.5 — 6** | 简化版（~85-95% skopt 效果） |

## 与现有代码的接口兼容

| 接口 | 兼容性 | 说明 |
|------|--------|------|
| `ObjectiveFunction.__call__(x) → float` | ✅ | x.tolist() 支持 numpy array |
| `History.parameters / History.scores` | ✅ | X/y 数据直接可用 |
| `history.append()` | ✅ | objective 自动追加，下一轮 gp.fit 读取最新数据 |
| `algo.run()` 签名 | ✅ | 与其他算法完全一致 |
| `configs/test_benchmark.json` | ✅ | 无需修改 |

## 路径 A vs 路径 B 性能对比

| 环节 | skopt (Path A) | 手写 EI (Path B) |
|------|---------------|------------------|
| GP 拟合 | sklearn.GaussianProcessRegressor | 相同（同底层） |
| 核函数 | Matern5/2 + WhiteKernel | Matern2.5 + WhiteKernel |
| 采集优化 | L-BFGS-B 精修 + 随机采样 | 仅随机采样（5000 候选） |
| 数值稳定性 | 边界情况处理完善 | 可能遇到 sigma=0 退化 |
| 10D+50 budget 预估 | 100% | ~85-95% |
| 依赖 | 需安装 scikit-optimize | 仅需 scikit-learn（通常已装） |

**结论**：手写版本对 10 维场景足够有效。采集优化是主要差距，但 5000 候选点已覆盖大部分搜索空间。实际 EPICS 加速器优化中两者性能差异可忽略。
