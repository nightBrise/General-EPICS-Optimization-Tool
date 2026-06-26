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
flowchart LR
    A["config.json<br/>━━━━━━━<br/>只填PV+range+target<br/>不写 Python"] -->|"①解析"| B["GenericOptimizer<br/>(编排器)"]
    B -->|"②创建"| C["Problem<br/>(PV索引+评分)"]
    B -->|"②创建"| D["History<br/>(迭代记录)"]
    B -->|"③构建"| E["Objective<br/>callable(x)→float<br/>一次调用=ask→apply→read→score"]
    B -->|"④分发"| F["@register_algorithm<br/>━━━━━━━<br/>追加不改核心↓"]
    F --> F1["DE"] & F2["NM"] & F3["NGOpt"] & F4["CMA"] & F5["Bayesian"]
    E -->|"apply(pvs,values)"| G["HardwareController<br/>(caput+验证+回滚)"]
    G -->|"caput/caget"| H["EPICSBackend (单例)<br/>━━━━━━━<br/>同一份代码<br/>simulator⇔real"]
    H --> H1["pyepics"] & H2["Griewank"]
    E -->|"⑤ append(iter,score,params)"| D
    D -->|"⑥ to_dict()"| I["SQLite · 6表<br/>━━━━━━━<br/>N次迭代<br/>一行SQL可查"]
    I -->|"⑦ plot_run(id)"| J["6图 PNG<br/>━━━━━━━<br/>一键出图<br/>--plot"]
    B -->|"⑧ to_dict()"| K["CLI打印<br/>run_id→询问出图"]

    style A fill:#1565c0,color:#fff
    style B fill:#e65100,color:#fff
    style C fill:#2e7d32,color:#fff
    style D fill:#2e7d32,color:#fff
    style E fill:#2e7d32,color:#fff
    style F fill:#c62828,color:#fff
    style H fill:#6a1b9a,color:#fff
    style I fill:#00695c,color:#fff
    style J fill:#f57f17,color:#fff
    style K fill:#e65100,color:#fff
```

> **图例**：数字 ①—⑧ 对应运行时的 8 个步骤。"━━━" 分隔线下是通用性说明。粉色节点 = 无需改核心代码即可扩展。

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
