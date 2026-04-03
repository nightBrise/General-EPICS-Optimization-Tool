# SXFEL 优化工具箱
![version](https://img.shields.io/badge/version-v2.5-brightgreen)

通用加速器优化框架，支持束流尺寸优化、轨道优化等多种优化任务。

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 基本使用

```bash
# 束斑优化
python run_optimization.py --config config_beam.json --budget 50

# 轨道优化（全0模式）
python run_optimization.py --config config_orbit.json --mode zero --budget 50

# 轨道优化（参考轨道模式）
python run_optimization.py --config config_orbit.json --mode ref --budget 50
```

## 主要功能

| 功能 | 说明 | 文档 |
|------|------|------|
| 束流尺寸优化 | 最小化束斑同时优化圆度，支持自适应步长 | [docs/beam_optimization.md](docs/beam_optimization.md) |
| 轨道优化 | 调整校正子使 BPM 接近零或参考轨道 | [docs/orbit_optimization.md](docs/orbit_optimization.md) |

### 核心特性

- **自适应步长**：历史平均法动态确定元件敏感度，敏感元件小步长，不敏感元件大步长
- **越界检测**：边缘预警+渐进惩罚，完全越界时回滚参数
- **EPICS/模拟器双模式**：无需硬件即可测试

## 结果可视化

优化完成后，结果自动保存为 HDF5 格式（`results/beam_YYYYMMDD_HHMMSS.h5` 或 `results/orbit_YYYYMMDD_HHMMSS.h5`）。

使用可视化工具查看结果：

```bash
# 交互式选择文件并可视化
python tools/plot_results.py
```

可视化工具会自动生成包含以下内容的图表：
- **收敛曲线**：评分随迭代次数的变化
- **束流尺寸/轨道偏差变化**：优化过程中各指标的变化
- **质心轨迹/轨道轮廓**：束流位置或轨道分布的变化
- **参数演化热图**：各设备参数在优化过程中的变化
- **最优图像对比**：初始与最优状态的束流图像对比

## 模拟器与真实 EPICS

默认使用**真实 EPICS** 模式。添加 `--simulator` 参数切换到模拟器模式（无需连接真实设备）：

```bash
python run_optimization.py --config config.json --simulator
```

模拟器支持：
- 相机图像生成（Fortran 顺序输出）
- BPM 轨道模拟
- CCD 增益控制
- 设备越界检测

## Web UI 界面

提供 Web UI 界面（Gradio），可通过浏览器访问：

```bash
# 启动 Web UI
python run_ui.py
```

Web UI 支持束流尺寸优化和轨道优化的图形化配置与实时监控。

## 详细文档

- [束斑优化](docs/beam_optimization.md) - 配置参数、评分公式、自适应步长
- [轨道优化](docs/orbit_optimization.md) - 全0/参考模式、配置参数
- [统一接口](docs/unified_interface.md) - 添加新目标函数
- [UI 设计](docs/ui_design.md) - Gradio 界面规范

## 支持

- 常规问题: zhangny@sari.ac.cn, zhangbw@sari.ac.cn
- 最后更新: 2026-04-04
