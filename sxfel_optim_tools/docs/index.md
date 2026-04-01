# SXFEL 优化工具箱文档

## 目录

- [快速开始](index.md) - 项目简介和快速使用
- [束斑优化](beam_optimization.md) - 束流尺寸优化系统
- [轨道优化](orbit_optimization.md) - 轨道优化系统（全0/参考模式）
- [统一接口](unified_interface.md) - 如何添加新的目标函数
- [UI 设计](ui_design.md) - 界面设计规范（待补充）

---

## 快速导航

### 束斑优化
适用于最小化束流在 YAG 相机上的尺寸，同时优化圆度。

```bash
python run_optimization.py --config config_beam.json --budget 50
```

详细说明请参阅：[束斑优化文档](beam_optimization.md)

### 轨道优化
适用于调整校正子（corrector）使轨道接近零或参考轨道。

```bash
# 优化到全0轨道
python run_optimization.py --config config_orbit.json --mode zero --budget 50

# 优化到参考轨道
python run_optimization.py --config config_orbit.json --mode ref --budget 50
```

详细说明请参阅：[轨道优化文档](orbit_optimization.md)

### 添加新目标函数
通过注册新的目标函数类，可以扩展系统支持新的优化任务。

详细说明请参阅：[统一接口文档](unified_interface.md)
