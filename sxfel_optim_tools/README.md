# SXFEL 优化工具箱
![version](https://img.shields.io/badge/version-v2.3-brightgreen)

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
| 束流尺寸优化 | 最小化束斑同时优化圆度 | [docs/beam_optimization.md](docs/beam_optimization.md) |
| 轨道优化 | 调整校正子使 BPM 接近零或参考轨道 | [docs/orbit_optimization.md](docs/orbit_optimization.md) |

## 模拟器与真实 EPICS

默认使用**真实 EPICS** 模式。添加 `--simulator` 参数切换到模拟器模式（无需连接真实设备）：

```bash
python run_optimization.py --config config.json --simulator
```

## Web UI 界面

Web UI 界面（Gradio）正在开发中，暂不可用。命令行工具已完全可用。

## 详细文档

- [束斑优化](docs/beam_optimization.md) - 配置参数、评分公式
- [轨道优化](docs/orbit_optimization.md) - 全0/参考模式、配置参数
- [统一接口](docs/unified_interface.md) - 添加新目标函数
- [UI 设计](docs/ui_design.md) - Gradio 界面规范

## 支持

- 常规问题: zhangny@sari.ac.cn, zhangbw@sari.ac.cn
- 最后更新: 2026-04-02
