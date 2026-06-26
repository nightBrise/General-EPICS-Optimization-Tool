# SXFEL 通用 EPICS 优化工具箱 <img src="https://img.shields.io/badge/version-v4.0-blue" alt="v4.0">

通用加速器优化框架，JSON 配置驱动，支持模拟器和真实 EPICS。5 种算法，SQLite 存储，自动可视化。

## 快速开始

```bash
pip install -r requirements.txt

# 模拟器模式（无硬件）
python run_optimization.py --config configs/test_benchmark.json --simulator -y

# 真实 EPICS 模式
python run_optimization.py --config my_config.json
```

## 用户指南

### 第一步：选配置文件

| 如果你要... | 用这个文件 |
|------------|-----------|
| **从零开始写新任务** | [`configs/template.minimal.json`](configs/template.minimal.json) — 复制一份，填 PV 即可 |
| **了解每个字段含义** | [`configs/config_reference.json`](configs/config_reference.json) — 完整参考手册 |
| **看一个已有的轨道示例** | [`configs/orbit_example.json`](configs/orbit_example.json) |
| **看束流尺寸优化示例** | [`configs/beam_example.json`](configs/beam_example.json) |
| **测试算法效果** | [`configs/test_benchmark.json`](configs/test_benchmark.json) — Griewank 10D 基准 |

### 第二步：运行

```bash
# 模拟器调试（不接机器）
python run_optimization.py --config my_config.json --simulator -y

# 确认无误 → 去掉 --simulator 接真实 EPICS
python run_optimization.py --config my_config.json
```

### 第三步：选算法

```bash
# 所有算法统一通过 --algorithm 切换
python run_optimization.py --config my_config.json --simulator -y --algorithm de           # Differential Evolution（默认）
python run_optimization.py --config my_config.json --simulator -y --algorithm nelder-mead  # Nelder-Mead
python run_optimization.py --config my_config.json --simulator -y --algorithm ngopt        # Nevergrad NGOpt（需安装）
python run_optimization.py --config my_config.json --simulator -y --algorithm cma          # Nevergrad CMA（需安装）
python run_optimization.py --config my_config.json --simulator -y --algorithm bayesian     # Bayesian（需 scikit-learn）
```

## 配置结构速览

```jsonc
{
    "variables": [{"pv": "PV:NAME", "range": [-1, 1]}],
    "objectives": {"groups": [{
        "pvs": [{"pv": "PV:TARGET", "target": 0.0}],
        "scoring": {"method": "l2"}
    }]},
    "optimization": {"algorithm": "differential_evolution", "budget": 50}
}
```

详见 [`config_reference.json`](configs/config_reference.json)。

## 架构

```mermaid
flowchart TB
    subgraph CLI["入口"]
        CLI_ARG["--config file.json<br/>--budget N --algorithm X<br/>--simulator --plot"]
    end

    subgraph Core["核心层"]
        direction TB
        OPTIMIZER["GenericOptimizer<br/>(编排器 · 225行)"]
        PROBLEM["OptimizationProblem<br/>(PV索引 + 评分)"]
        HISTORY["History<br/>(类型化迭代记录)"]
        OBJECTIVE["ObjectiveFunction<br/>(callable(x) → float)"]
        HW["HardwareController<br/>(caput + 验证 + 回滚)"]
        VM["VariableManager<br/>(PV管理 + 边界)"]
    end

    subgraph Algo["算法插件"]
        direction LR
        DE["DE<br/>(scipy)"]
        NM["Nelder-Mead<br/>(scipy)"]
        NG["NGOpt<br/>(Nevergrad)"]
        CMA["CMA<br/>(Nevergrad)"]
        BO["Bayesian<br/>(skopt→sklearn→DE)"]
    end

    subgraph Backend["后端路由"]
        BACKEND["EPICSBackend<br/>(单例)"]
        EPICS["pyepics<br/>(真实EPICS)"]
        SIM["TestFunctionSimulator<br/>(Griewank)"]
    end

    subgraph Storage["存储层"]
        direction LR
        SQLITE["SQLite · 6表<br/>runs · variables · objectives<br/>group_mapping · iterations<br/>failure_log"]
        PLOT["6图 2×3 PNG<br/>收敛曲线 · PV演化<br/>热图 · 分布 · 改善"]
    end

    CLI_ARG -->|"config.json"| OPTIMIZER
    OPTIMIZER -->|"解析 objectives"| PROBLEM
    OPTIMIZER -->|"创建"| HISTORY
    OPTIMIZER -->|"构建"| OBJECTIVE
    OPTIMIZER -->|"分发"| Algo

    OBJECTIVE -->|"apply(pvs, values)"| HW
    OBJECTIVE -->|"caget_many / compute_score"| PROBLEM
    OBJECTIVE -->|"append(iter, score, params)"| HISTORY

    HW -->|"caput / caget"| BACKEND
    BACKEND -->|"use_simulator=True"| SIM
    BACKEND -->|"use_simulator=False"| EPICS

    HISTORY -->|"to_dict()"| SQLITE
    SQLITE -->|"plot_run(run_id)"| PLOT

    style CLI_ARG fill:#e1f5fe
    style OPTIMIZER fill:#fff3e0
    style PROBLEM fill:#e8f5e9
    style HISTORY fill:#e8f5e9
    style OBJECTIVE fill:#e8f5e9
    style Algo fill:#fce4ec
    style BACKEND fill:#f3e5f5
    style SQLITE fill:#e0f2f1
    style PLOT fill:#fff8e1
```

### 数据流详解

```
   config.json                    ← 用户填写: variables[], objectives{}, optimization{}, hardware{}
       │
       ▼
   GenericOptimizer.__init__()    ← 解析配置 → 创建 Problem + 初始化 History
       │
       ▼  run() ──────────────────────────────────────────┐
       │                                                   │
       ├─ ① 读取初始值                                     │
       │    var_mgr.read_initial_values() → caget(pvs)     │
       │    Fix: 边界裁剪 (initial ∈ [lo, hi])              │
       │                                                   │
       ├─ ② 初始评估                                       │
       │    caget_many(obj_pvs) → problem.compute_score()  │
       │    → history.add_initial(score, group_scores)    │
       │                                                   │
       ├─ ③ 构建目标函数                                   │
       │    ObjectiveFunction(hw, problem, history, pvs)  │
       │       └─ __call__(x) → 每次迭代:                  │
       │            hw.apply() → caget_many() → score     │
       │            → history.append(...)                  │
       │                                                   │
       ├─ ④ 算法分发                                       │
       │    algo = get_algorithm("de")                    │
       │    algo.run(objective, bounds, budget, history)   │
       │       └─ DE/NM/NGOpt/CMA/Bayesian 统一接口       │
       │                                                   │
       ├─ ⑤ 结果提取                                       │
       │    history.update_best() → best_score, best_params │
       │                                                   │
       └─ ⑥ 持久化 + 可视化                                │
            history.to_dict() → save_results() → SQLite    │
            → "Generate plot?" → plot_run(run_id) → PNG   │
```

## CLI

```bash
python run_optimization.py --config config.json                # 基础用法
python run_optimization.py --config config.json -y             # 跳过确认
python run_optimization.py --config config.json --budget 100   # 覆盖迭代次数
python run_optimization.py --config config.json --algorithm de # 覆盖算法
python run_optimization.py --config config.json --simulator    # 模拟器模式
python run_optimization.py --config config.json --plot         # 自动生成图表
```

## 支持

zhangny@sari.ac.cn, zhangbw@sari.ac.cn
