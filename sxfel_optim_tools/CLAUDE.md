# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本代码仓库中工作时提供指导。

## 对话语言限制

**与用户的所有对话必须使用中文。**

## 项目概述

**SXFEL 优化工具箱** - 通用加速器优化框架，支持束流尺寸优化、轨道优化等多种优化任务。

- 命令行入口：`python run_optimization.py --config <config_file>`
- Web UI 入口：`python run_ui.py`（Gradio 界面）
- 配置驱动：新增优化任务只需提供配置文件，无需修改代码
- EPICS/模拟器双模式：测试时使用模拟器，生产环境切换到真实 EPICS

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 命令行束流尺寸优化
python run_optimization.py --config config_beam.json --budget 50

# 命令行轨道优化（全0模式）
python run_optimization.py --config config_orbit.json --mode zero --budget 50

# 命令行轨道优化（参考轨道模式）
python run_optimization.py --config config_orbit.json --mode ref --budget 50

# 指定算法
python run_optimization.py --config config_beam.json --algorithm NGOpt

# Web UI 模式（Gradio）
python run_ui.py
```

## 项目结构

```
sxfel_optim_tools/
├── run_optimization.py          # 命令行统一入口
├── run_ui.py                    # Web UI 入口 (Gradio)
├── config_beam.json             # 束流优化配置
├── config_orbit.json            # 轨道优化配置
├── requirements.txt             # Python 依赖
├── core/                        # 核心模块
│   ├── epics_backend.py        # EPICS 后端选择器（单例模式）
│   ├── objectives/              # 目标函数（注册机制）
│   │   ├── base.py             # 基类 BaseObjective
│   │   ├── registry.py         # @register_objective 注册表
│   │   ├── beam.py             # 束流目标 (beam_size)
│   │   ├── orbit_zero.py       # 零点轨道 (orbit_zero)
│   │   ├── orbit_ref.py        # 参考轨道 (orbit_ref)
│   │   └── metrics.py          # 线程安全指标追踪器
│   ├── optimizer.py            # Nevergrad 封装
│   ├── simulator.py            # EPICS 模拟器
│   ├── step_manager.py        # 自适应步长管理器
│   ├── results.py              # 结果保存/加载 (HDF5)
│   └── utils.py               # 通用工具函数
├── tools/                      # 辅助工具
│   └── plot_results.py        # 结果可视化
├── ui/                         # Web UI 模块
│   ├── beam_app.py            # 束流优化 Web 界面
│   ├── orbit_app.py           # 轨道优化 Web 界面
│   └── theme.py              # UI 主题
├── docs/                       # 详细文档
└── legacy/                     # 历史版本（参考用）
```

## 架构

### 核心流程

```
run_optimization.py → create_objective(config) → Optimizer.run() → objective.get_score()
```

### 目标函数注册机制

```python
# 注册新目标函数
@register_objective("my_objective")
class MyObjective(BaseObjective):
    def get_score(self, params, device_pvs):
        # 评分逻辑
        return score

# 使用配置文件
{
  "objective": {"type": "my_objective", ...}
}
```

### EPICS/模拟器切换

通过 `core/epics_backend.py` 的单例模式 `EPICSBackend` 运行时切换：

```python
from core.epics_backend import set_backend, is_simulator

# 模拟器模式（默认）
set_backend(use_simulator=True)

# 真实 EPICS 模式
set_backend(use_simulator=False)
```

命令行使用 `--simulator` 参数切换：
```bash
python run_optimization.py --config config.json --simulator
```

## 配置格式

### 统一配置字段

| 字段 | 说明 |
|------|------|
| `name` | 任务名称 |
| `objective.type` | 目标函数类型（beam_size, orbit_zero, orbit_ref） |
| `objective.read_pvs` | 读取的 EPICS PV 列表 |
| `devices` | 设备配置（quadrupoles, correctors 等） |
| `optimization.algorithm` | 算法（Compass, NGOpt, CMA, PSO） |
| `optimization.budget` | 迭代次数 |

### 硬件参数（objective.params）

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `repetition_rate` | 束团重复频率（Hz），用于计算 BPM 采样间隔 | 10 |
| `num_averages` / `num_bpm_averages` | 采样平均次数 | 3/5 |
| `min_adjust_interval` | 校正子最小调整间隔（秒），硬件限制 | 6 |
| `poll_interval` | 轮询间隔（秒） | 0.2 |
| `tolerance` | 设定值容差 | 0.0001 |
| `max_wait` | 最大等待时间（秒） | 10 |

### 束流优化配置

```json
{
  "objective": {
    "type": "beam_size",
    "params": {"shape": [1392, 1040], "num_averages": 3}
  },
  "devices": {"quadrupoles": [...], "correctors": [...]}
}
```

### 轨道优化配置

```json
{
  "objective": {
    "type": "orbit",
    "params": {"reference_orbit": {...}}
  },
  "devices": {"correctors": [...]}
}
```

## 关键模块

- **`core/epics_backend.py`**：`EPICSBackend` 单例类，统一管理模拟器/真实 EPICS 切换
- **`core/objectives/registry.py`**：`@register_objective` 装饰器，`create_objective()` 工厂函数
- **`core/optimizer.py`**：`Optimizer` 类封装 Nevergrad 优化循环，支持早停和回滚
- **`core/simulator.py`**：`SimpleEPICSSimulator` 模拟 EPICS PV，支持相机图像、BPM 轨道、增益控制和越界检测
- **`core/step_manager.py`**：`StepManager` 自适应步长管理器，根据迭代阶段和光斑移动速度动态调整步长
- **`core/utils.py`**：`load_config`, `safe_device_operation`, `select_optimization_devices`, `wait_for_all_devices_settled`

## 评分公式

**束流优化**：
```
score = w_size × size_score + w_roundness × non_roundness_penalty + w_position × position_penalty
       + w_intensity × intensity_penalty + w_gaussian × gaussian_penalty
```
其中权重由 `beam_mode`（size_focus/balanced/roundness_focus）和 `fel_mode`（none/soft/both）控制。

**轨道优化**：
```
score = RMS + α×Peak + β×Roughness + γ×Coupling + δ×Skew
```
其中权重由 `mode`（smooth/balanced/aggressive）控制。

## 已知问题

- `core/epics_backend.py` 的 `EPICSBackend` 单例模式存在线程安全问题（`_use_simulator` 是类变量）
- 核心模块（objectives、optimizer、epics_backend 等）缺乏单元测试
- `beam.py` 中存在部分代码重复（`optimize_beam()` 与 `BeamObjective.get_score()`）

## 新增目标函数

1. 在 `core/objectives/` 下编写类，使用 `@register_objective` 注册
2. 继承 `BaseObjective`，实现 `get_score(params, device_pvs)`
3. 创建配置文件
4. 运行 `python run_optimization.py --config <your_config.json>`

## 开发规范

- 代码注释使用中文
- 遵循 Google Python 代码风格
- 导入顺序：标准库 → 第三方库 → 本地模块
