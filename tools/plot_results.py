#!/usr/bin/env python3
"""结果可视化工具 — 从 SQLite 读取数据，生成 6 图 2×3 布局的 PNG"""

import sqlite3
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

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
})


def _ax_style(ax):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def plot_run(run_id, db_path='results/optimizations.db'):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        row = cur.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if row is None:
            print(f"  Run #{run_id} not found")
            conn.close()
            return
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

        # Params: shape = (n_iters, n_vars)
        params_rows = cur.execute(
            'SELECT params FROM iterations WHERE run_id=? ORDER BY iteration', (run_id,))
        params_raw = [r['params'] for r in params_rows if r['params'] is not None]
        params = []
        for p in params_raw:
            v = unpack(p)
            if isinstance(v, list) and len(v) > 0 and isinstance(v[0], list):
                v = v[0]
            params.append(v)

        # Variables
        device_pvs = [r['pv_name'] for r in cur.execute(
            'SELECT pv_name FROM variables WHERE run_id=?', (run_id,))]

        # Readings + targets
        objectives_rows = list(cur.execute(
            'SELECT pv_name, target FROM objectives WHERE run_id=?', (run_id,)))
        obj_pvs = [r['pv_name'] for r in objectives_rows]
        obj_targets = [r['target'] for r in objectives_rows]

        readings_rows = cur.execute(
            'SELECT readings FROM iterations WHERE run_id=? ORDER BY iteration', (run_id,))
        readings_list = []
        for r in readings_rows:
            if r['readings'] is not None:
                readings_list.append(unpack(r['readings']))

        # Failures
        failures = list(cur.execute(
            'SELECT iteration, pv_name, error_msg FROM failure_log WHERE run_id=?', (run_id,)))
    finally:
        conn.close()

    if not iters:
        print(f"  Run #{run_id} has no iteration data")
        return

    # Compute improvement sign
    diff = init_score - best_score
    pct = diff / init_score * 100 if init_score > 0 else 0
    sign = "+" if diff < 0 else "-"

    fig, axes = plt.subplots(2, 3, figsize=(20, 13))

    title = (f"Run #{run_id} | {algo} | budget={budget} | "
             f"{init_score:.2f} -> {best_score:.4f} ({sign}{abs(pct):.1f}%) | {elapsed:.1f}s")
    fig.suptitle(title, fontsize=11, fontweight='bold', y=0.98)

    tab10 = plt.cm.tab10.colors

    # === 1. Score Convergence ===
    ax = axes[0, 0]
    _ax_style(ax)
    ax.plot(iters, scores, color='#1f77b4', lw=1.5, alpha=0.9, label='Score')
    if best_iter is not None:
        ax.axvline(best_iter, color='#d62728', ls='--', lw=1.5, alpha=0.8,
                   label=f'Best iter {best_iter}')
    if failures:
        fail_iters = [f['iteration'] for f in failures]
        ax.scatter(fail_iters, [max(scores)] * len(fail_iters),
                   marker='x', color='red', s=60, zorder=5, alpha=0.8,
                   label='Failure')
    ax.legend(fontsize=7, loc='upper right')
    ax.set_title('Score Convergence')
    ax.set_xlabel('Iteration')
    ax.set_ylabel('Score')
    ax.grid(True, alpha=0.2)

    # === 2. Top-5 PV Evolution ===
    ax = axes[0, 1]
    _ax_style(ax)
    if readings_list and len(readings_list) > 0 and obj_pvs:
        r0 = readings_list[0]
        r_last = readings_list[-1]
        if len(r0) == len(obj_pvs) and len(r_last) == len(obj_pvs):
            deltas = [abs(r_last[i] - r0[i]) if isinstance(r0[i], (int, float)) else 0
                      for i in range(len(obj_pvs))]
            top5 = sorted(range(len(deltas)), key=lambda i: deltas[i], reverse=True)[:5]
            pv_iters = list(range(len(readings_list)))
            for rank, idx in enumerate(top5):
                vals = [r[idx] if isinstance(r[idx], (int, float)) else np.nan for r in readings_list]
                ax.plot(pv_iters, vals, color=tab10[rank % 10], lw=1.2, alpha=0.8,
                        label=obj_pvs[idx][:20])
            # min-max band for others
            other_vals = []
            for i in range(len(obj_pvs)):
                if i not in top5:
                    ovals = [r[i] if isinstance(r[i], (int, float)) else np.nan for r in readings_list]
                    other_vals.append(ovals)
            if other_vals:
                arr = np.array(other_vals)
                mn = np.nanmin(arr, axis=0)
                mx = np.nanmax(arr, axis=0)
                ax.fill_between(pv_iters, mn, mx, alpha=0.12, color='gray', label='Others')
            ax.axhline(0, color='gray', ls=':', lw=0.5, alpha=0.5)
            ax.legend(fontsize=8, loc='upper right', ncol=2)
    ax.set_title('Top-5 PV Evolution')
    ax.set_xlabel('Iteration')
    ax.set_ylabel('Reading')
    ax.grid(True, alpha=0.2)

    # === 3. Parameter Heatmap ===
    ax = axes[0, 2]
    _ax_style(ax)
    if params and device_pvs:
        arr = np.array(params).T
        im = ax.imshow(arr, aspect='auto', cmap='viridis', interpolation='nearest')
        ax.set_yticks(range(len(device_pvs)))
        short_labels = [p[:15] for p in device_pvs]
        ax.set_yticklabels(short_labels, fontsize=6 if len(device_pvs) > 12 else 7)
        if len(device_pvs) > 15:
            for j, label in enumerate(ax.yaxis.get_ticklabels()):
                if j % 2 != 0:
                    label.set_visible(False)
        ax.set_xlabel('Iteration')
        ax.set_ylabel('Device')
        ax.set_title('Parameter Heatmap')
        if best_iter is not None:
            ax.axvline(best_iter, color='red', ls='--', lw=2, alpha=0.7)
        if len(device_pvs) <= 12 and arr.shape[0] <= 12:
            for i in range(arr.shape[0]):
                for j in range(arr.shape[1]):
                    ax.text(j, i, f'{arr[i, j]:.1f}',
                            ha='center', va='center', fontsize=5, color='white' if arr[i, j] > arr.mean() else 'black')
        plt.colorbar(im, ax=ax, shrink=0.7, pad=0.02)
    else:
        ax.text(0.5, 0.5, 'No parameter data', ha='center', va='center', transform=ax.transAxes)
        ax.set_title('Parameter Heatmap')

    # === 4. PV Improvement (horizontal bars) ===
    ax = axes[1, 0]
    _ax_style(ax)
    if readings_list and len(readings_list) > 1 and obj_pvs:
        r0 = readings_list[0]
        r_last = readings_list[-1]
        deltas = []
        for i in range(min(len(obj_pvs), len(r0), len(r_last))):
            if isinstance(r0[i], (int, float)) and isinstance(r_last[i], (int, float)):
                deltas.append(abs(r_last[i] - r0[i]))
            else:
                deltas.append(0)
        sorted_idx = sorted(range(len(deltas)), key=lambda i: deltas[i], reverse=True)
        top10 = sorted_idx[:10]
        other_sum = sum(deltas[i] for i in sorted_idx[10:])
        labels = [obj_pvs[i][:15] for i in top10]
        vals = [deltas[i] for i in top10]
        if other_sum > 0:
            labels.append('Others')
            vals.append(other_sum)
        colors = [tab10[i % 10] if i < 10 else '#888888' for i in range(len(labels))]
        bars = ax.barh(range(len(labels)), vals, color=colors, alpha=0.8)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=7)
        ax.set_xlabel('|initial - best|')
        ax.set_title('PV Improvement')
        ax.invert_yaxis()
        # Annotate top-3 and worst-3
        for i in range(len(bars)):
            if i < 3 or i >= max(len(bars) - 3, 3):
                ax.text(vals[i] + max(vals) * 0.02, i, f'{vals[i]:.2f}',
                        va='center', fontsize=6)
        ax.grid(True, axis='x', alpha=0.2)
    else:
        ax.text(0.5, 0.5, 'No reading data', ha='center', va='center', transform=ax.transAxes)
        ax.set_title('PV Improvement')

    # === 5. Score Distribution (hist + box) ===
    # Use gridspec_kw in plt.subplots? No, this is a 2x3 layout.
    # Instead, use the bottom-center chart for a combined hist+box
    ax = axes[1, 1]
    _ax_style(ax)
    if scores and len(scores) > 2:
        # Split into first half and second half
        n = len(scores)
        first_half = scores[:n // 2]
        second_half = scores[n // 2:]

        # Histogram
        bins = max(min(20, n // 3), 5)
        ax.hist(first_half, bins=bins, alpha=0.4, color='#1f77b4', label='First 50%')
        ax.hist(second_half, bins=bins, alpha=0.5, color='#d62728', label='Last 50%')

        # Box plot below
        ax2 = ax.twinx()
        bp = ax2.boxplot([first_half, second_half], positions=[n // 4, n * 3 // 4],
                          widths=2, patch_artist=True, manage_ticks=False)
        for patch, color in zip(bp['boxes'], ['#1f77b4', '#d62728']):
            patch.set_facecolor(color)
            patch.set_alpha(0.3)
        ax2.set_ylim(min(scores) * 0.9, max(scores) * 1.1)
        ax2.set_yticks([])

        ax.set_xlabel('Score')
        ax.set_ylabel('Count')
        ax.set_title('Score Distribution')
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.2)
    else:
        ax.text(0.5, 0.5, 'Not enough data', ha='center', va='center', transform=ax.transAxes)
        ax.set_title('Score Distribution')

    # === 6. Convergence Rate (per 10 iterations) ===
    ax = axes[1, 2]
    _ax_style(ax)
    if len(scores) >= 10:
        window = 10
        rates = []
        rate_iters = []
        for i in range(window, len(scores)):
            prev = scores[i - window]
            curr = scores[i]
            chg = (curr - prev) / prev * 100 if prev != 0 else 0
            rates.append(abs(chg))
            rate_iters.append(iters[i])
        ax.plot(rate_iters, rates, color='#2ca02c', lw=1.5, marker='.', markersize=3, alpha=0.8)
        avg_rate = np.mean(rates)
        ax.axhline(avg_rate, color='gray', ls='--', lw=1, alpha=0.6, label=f'Avg: {avg_rate:.1f}%')
        ax.legend(fontsize=7)
        ax.set_title('Convergence Rate')
        ax.set_xlabel('Iteration')
        ax.set_ylabel('|Change| / 10 iter (%)')
        ax.grid(True, alpha=0.2)
    else:
        ax.text(0.5, 0.5, '< 10 iterations', ha='center', va='center', transform=ax.transAxes)
        ax.set_title('Convergence Rate')

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out = f'results/run_{run_id}_plot.png'
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  {chr(0x2713)} chart saved: {out}")


def compare_runs(run_ids, db_path='results/optimizations.db'):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = []
    for rid in run_ids:
        row = cur.execute('SELECT * FROM runs WHERE run_id=?', (rid,)).fetchone()
        if row:
            rows.append(row)
    conn.close()

    if not rows:
        print("  No runs found")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    _ax_style(ax1)
    _ax_style(ax2)

    tab10 = plt.cm.tab10.colors
    for i, row in enumerate(rows):
        rid = row['run_id']
        algo = row['algorithm']
        best = row['best_score']
        conn2 = sqlite3.connect(db_path)
        conn2.row_factory = sqlite3.Row
        c2 = conn2.cursor()
        iters = [r['iteration'] for r in c2.execute(
            'SELECT iteration FROM iterations WHERE run_id=? ORDER BY iteration', (rid,))]
        scores = [r['score'] for r in c2.execute(
            'SELECT score FROM iterations WHERE run_id=? ORDER BY iteration', (rid,))]
        conn2.close()

        label = f'{algo} (run #{rid})'
        color = tab10[i % 10]
        linestyle = ['-', '--', '-.', ':'][i % 4]
        ax1.plot(iters, scores, color=color, ls=linestyle, lw=1.5, alpha=0.8, label=label)
        bar_h = 0.7 / max(len(rows), 1)
        ax2.barh(i * bar_h, best, height=bar_h * 0.7, color=color, alpha=0.8, label=label)

    ax1.set_title('Convergence Comparison')
    ax1.set_xlabel('Iteration')
    ax1.set_ylabel('Score')
    ax1.legend(fontsize=7)
    ax1.grid(True, alpha=0.2)

    ax2.set_title('Best Score Ranking')
    ax2.set_yticks([])
    ax2.set_xlabel('Best Score')
    ax2.legend(fontsize=7, loc='lower right')
    ax2.grid(True, axis='x', alpha=0.2)

    plt.tight_layout()
    out = 'results/compare_plot.png'
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  {chr(0x2713)} comparison saved: {out}")


# Local pack/unpack (matches core/result_recorder.py)
import json, zlib

def pack(v):
    return zlib.compress(json.dumps(v).encode())

def unpack(b):
    return json.loads(zlib.decompress(b))


def main():
    parser = argparse.ArgumentParser(description='Optimization Result Visualization')
    parser.add_argument('--run-id', type=int, help='Plot one run')
    parser.add_argument('--runs', help='Compare runs (comma-separated IDs)')
    parser.add_argument('--db', default='results/optimizations.db', help='SQLite database path')
    args = parser.parse_args()

    if args.runs:
        compare_runs([int(x) for x in args.runs.split(',')], args.db)
    elif args.run_id is not None:
        plot_run(args.run_id, args.db)
    else:
        import sqlite3
        conn = sqlite3.connect(args.db)
        row = conn.execute('SELECT run_id FROM runs ORDER BY run_id DESC LIMIT 1').fetchone()
        conn.close()
        if row:
            plot_run(row['run_id'], args.db)
        else:
            print("  No runs found in database")


if __name__ == '__main__':
    main()
