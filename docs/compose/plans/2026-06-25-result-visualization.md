# 结果可视化实施计划

> 日期: 2026-06-25
> 状态: ✅ IMPLEMENTED
> 前置: Phase 1+2+3 完成，所有算法已跑通，SQLite 存储可用
> 目标: 从用户视角设计结果可视化，CLI 命令即可生成图表

## 用户需求分析

用户完成优化后，需要回答六个问题：

| 问题 | 可视化 | 优先级 |
|------|--------|--------|
| 优化有没有效？ | 评分收敛曲线 | 必做 |
| 目标 PV 读数是否趋近 target？ | PV 读数演化曲线 | 必做 |
| 哪个设备变化最大？ | 参数变化热图 | 必做 |
| 各目标改善了多少？ | 改善对比柱状图 | 必做 |
| 收敛质量如何？ | 评分分布 + 箱线图 | 必做 |
| 有没有故障？ | 失败记录 + 改善速率 | 必做 |

## 数据源

`results/optimizations.db` — SQLite 6 表，每次优化完整记录：

```
runs         — 元数据 (algorithm, budget, best_score, elapsed_sec)
iterations   — 每轮数据 (iteration, score, params, readings)
variables    — 设备 PV + 边界
objectives   — 目标 PV + target
group_mapping — readings 索引 → PV 名称
failure_log  — 异常记录
```

## 设计

### 命令

```bash
# 方法一：运行完自动出图
python run_optimization.py --config my.json --simulator -y --plot

# 方法二：对历史运行出图
python tools/plot_results.py --run-id 5

# 方法三：对比多次运行
python tools/plot_results.py --runs 5,8,12
```

### 图表布局

**单次运行（--run-id N）**：2×3 布局（6 张图），标题含摘要信息。

```
┌────────────────────────┬────────────────────────┬────────────────────────┐
│  1. Score Convergence  │  2. Top-5 PV Evolution │  3. Parameter Heatmap  │
│  收敛曲线 + 最优点     │  top-5 改善最大 PV     │  设备×迭代 热图         │
│  标注: best_iter       │  每条线对应一个 PV     │  标注: best_iter 列     │
│  失败点: 红色 'x'      │  灰色 region=其他 PV  │  N≤12 时标注数值       │
├────────────────────────┼────────────────────────┼────────────────────────┤
│  4. PV Improvement     │  5. Score Distribution │  6. Conv. Rate         │
│  水平条形图, 改善降序  │  直方图 + 箱线图      │  每10轮改善速率        │
│  标注: top-3 + worst-3 │  (上下分两面板)       │  标注: 平均改善线      │
└────────────────────────┴────────────────────────┴────────────────────────┘

标题: "Run #N | {algo} | budget={budget} | {init} -> {best} (-{pct:.1f}%) | {elapsed:.1f}s"
```

**多运行对比（--runs N,M,K）**：叠加收敛曲线 + 排名柱状图

```
┌────────────────────────┬────────────────────────┐
│  收敛曲线对比           │  最终评分排名          │
│  DE ──────             │  █ DE      0.79         │
│  NGOpt ─ · ─           │  █ NGOpt   1.41         │
│  Bayesian ······       │  █ Bayesian  22.74      │
└────────────────────────┴────────────────────────┘
```

### 各图数据密度控制

| 图表 | 最大数据量 | 超出时截断策略 |
|------|-----------|---------------|
| 1. Score Convergence | 无限制 | 曲线 + 标注：不截断 |
| 2. Top-5 PV Evolution | 20 PV | 展示 top-5（按 `|initial - best|` 降序），其余合并为浅蓝 min-max 带 `fill_between(alpha=0.15)`，避免覆盖曲线 |
| 3. Parameter Heatmap | 20 设备 | 展示全部，y 轴自动缩放；>12 时省略 cell 数值标签 |
| 4. PV Improvement | 20 PV | 展示 top-10 改善最大的 PV（水平条排序），其余归入"Others"聚合条；仅标注 top-3 + worst-3 |
| 5. Score Distribution | 无限制 | 直方图 + 箱线图上下分两面板，无遮挡 |
| 6. Convergence Rate | 无限制 | 折线图 + 平均值参考线 |

### 图表规范

| 要求 | 规范 |
|------|------|
| **语言** | 所有标签、标题、图例、坐标轴、注释统一使用英文 |
| **字体** | `plt.rcParams['font.size'] = 9`，标题 `fontsize=11`，图例 `fontsize=8` |
| **画布** | `figsize=(20, 13)`，`dpi=150`，PNG 输出（每子图约 6.6×4.3 英寸，9pt≈6pt，可读） |
| **背景** | `facecolor='white'`，`axes.facecolor='#fafafa'`（浅灰背景让网格可见） |
| **边框** | `axes.linewidth=0.8`，`axes.spines['top'].set_visible(False)`，`axes.spines['right'].set_visible(False)`（去掉上/右边框） |
| **网格** | `axes.grid(True, which='major', alpha=0.2, linewidth=0.5)`，仅主刻度；无 minor grid |
| **配色** | 全局统一 `tab10` 调色板；线型序列 `['-', '--', '-.', ':']`；>10 条线时组合 `(tab10[i], linestyles[i%4])` |
| **防遮挡** | `tight_layout(rect=[0, 0, 1, 0.95])`，标注用 `textcoords='offset points'`，字体 `fontsize=7` |
| **曲线平滑** | 迭代数 > 100 时用 `np.convolve(scores, np.ones(5)/5, mode='same')` 滚动平均叠加（`mode='same'` 保持长度一致） |
| **热图 y 轴** | 设备数 > 10 时 y 轴字体缩小至 `fontsize=6`；> 15 时只显示奇数索引标签 |

### 图表标注

| 图表 | 标注内容 | 方法 |
|------|----------|------|
| 1. Score Convergence | 最优迭代点 | `axvline(best_iter, color='r', ls='--', lw=1.5, alpha=0.7)` |
|                     | 失败点 | `scatter` 红色 'x' 标记（仅在 failure_log 非空时） |
| 2. Top-5 PV Evolution | target 参考线 | `axhline(0, color='gray', ls=':', lw=0.5)`（deviation = 0 line） |
|                       | PV 名图例 | 每个 PV 一条线，颜色区分，图例字体 8，右上角 `loc='upper right'` |
| 3. Parameter Heatmap | 最优列高亮 | `axvline(best_iter, color='r', ls='--', lw=2)` |
|                       | 数值标签 | N≤12 时每个 cell 居中标 `{val:.1f}`，字号 6 |
| 4. PV Improvement | top-3 + worst-3 | 条形顶部 +/→ 偏移标注 `{val} ({pct}%)` |
| 5. Score Distribution | 上下面板 | 上面板 = 直方图 (hist)；下面板 = 箱线图 (boxplot)，共享 x 轴 |
| 6. Convergence Rate | 改善速率 | 折线 + 平均值虚线 |

### 核心实现

```python
# tools/plot_results.py — 重写

plt.rcParams.update({
    'font.size': 9,
    'axes.titlesize': 10,
    'axes.labelsize': 9,
    'xtick.labelsize': 7,
    'ytick.labelsize': 7,
    'legend.fontsize': 8,
    'figure.titlesize': 11,
    'figure.facecolor': 'white',
    'axes.facecolor': '#fafafa',
    'axes.linewidth': 0.8,
    'axes.grid.alpha': 0.2,
})

def _ax_style(ax):
    """统一子图风格：去掉上/右边框"""
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

def plot_run(run_id, db_path=None):
    """单次运行的完整可视化"""
    conn = sqlite3.connect(db_path or 'results/optimizations.db')
    cur = conn.cursor()
    try:
        row = cur.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
        algo = row['algorithm']
        budget = row['budget']
        init_score = row['initial_score']
        best_score = row['best_score']
        elapsed = row['elapsed_sec'] or 0
        best_iter = row['best_iter']

        iters = [r['iteration'] for r in cur.execute(
            'SELECT iteration FROM iterations WHERE run_id=? ORDER BY iteration', (run_id,))]
        scores = [r['score'] for r in cur.execute(
            'SELECT score FROM iterations WHERE run_id=? ORDER BY iteration', (run_id,))]
        failures = cur.execute(
            'SELECT iteration, pv_name, error_msg FROM failure_log WHERE run_id=?', (run_id,))
    finally:
        conn.close()

    pct = (init_score - best_score) / init_score * 100 if init_score > 0 else 0

    fig, axes = plt.subplots(2, 3, figsize=(20, 13))

    # English summary title (handle negative improvement)
    sign = "+" if best_score > init_score else "-"
    title = (f"Run #{run_id} | {algo} | budget={budget} | "
             f"{init_score:.2f} -> {best_score:.4f} ({sign}{abs(pct):.1f}%) | {elapsed:.1f}s")
    fig.suptitle(title, fontsize=11, fontweight='bold', y=0.98)

    # 1. Score Convergence
    ax = axes[0,0]; _ax_style(ax)
    ax.plot(iters, scores, color='#1f77b4', lw=1.5, alpha=0.9)
    if best_iter is not None:
        ax.axvline(best_iter, color='#d62728', ls='--', lw=1.5, alpha=0.8,
                   label=f'Best iter {best_iter}')
        ax.legend(fontsize=7, loc='upper right')
    ax.set_title('Score Convergence')
    ax.set_xlabel('Iteration')
    ax.set_ylabel('Score')
    ax.grid(True, alpha=0.2)

    # 2-6: (implementations omitted for plan brevity)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out = f'results/run_{run_id}_plot.png'
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  {chr(0x2713)} chart saved: {out}")
```

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', type=int)
    parser.add_argument('--runs', help='comma-separated run IDs')
    parser.add_argument('--db', default='results/optimizations.db')
    parser.add_argument('--plot', action='store_true', help='auto-generate plot')
    args = parser.parse_args()

    if args.runs:
        compare_runs([int(x) for x in args.runs.split(',')], args.db)
    elif args.run_id:
        plot_run(args.run_id, args.db)
    else:
        with sqlite3.connect(args.db) as conn:
            row = conn.execute('SELECT run_id FROM runs ORDER BY run_id DESC LIMIT 1').fetchone()
        plot_run(row['run_id'], args.db)

def compare_runs(run_ids, db_path=None):
    """多运行对比：叠加收敛曲线 + 排名柱状图"""
    # ... (implementation)
```

### 运行后出图交互流

保存完成后，CLI 显示 run_id 并询问是否出图：

```bash
✓ run #39 → results/optimizations.db
  Generate plot? [y/N]: y
```

- `--plot` 参数：跳过询问，自动出图
- `-y` 参数：跳过询问（不自动出图）
- 默认：显示提示，用户输入 y/n

### 改动清单

| 文件 | 操作 |
|------|------|
| `tools/plot_results.py` | **重写** |
| `run_optimization.py` | 新增 `--plot` 参数 + 保存后询问出图 |

### 依赖

matplotlib 已在 `requirements.txt`（`matplotlib>=3.5.0,<3.8`），无新增依赖。

### 验证

```bash
# 1. 跑一次优化 + 自动出图
python run_optimization.py --config configs/test_benchmark.json --simulator -y --budget 50 --plot

# 2. 对已有运行出图
python tools/plot_results.py --run-id 1

# 3. 对比多次运行
python tools/plot_results.py --runs 1,2,3
```
