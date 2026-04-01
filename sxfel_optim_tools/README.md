# SXFEL 优化工具箱
![version](https://img.shields.io/badge/version-v2.0-brightgreen)

通用加速器优化框架，支持束流尺寸优化、轨道优化等多种优化任务。

## 项目结构

```
sxfel_optim_tools/
├── run_optimization.py     # 统一入口
├── config_beam.json        # 束斑优化配置
├── config_orbit.json       # 轨道优化配置
├── core/                   # 核心模块
│   ├── objectives/         # 目标函数
│   ├── optimizer.py       # 优化器
│   └── simulator.py       # EPICS 模拟器
├── tools/                  # 辅助工具
├── docs/                   # 详细文档
└── results/               # 结果目录
```

详细项目结构说明请参阅：[详细文档 - 统一接口](docs/unified_interface.md)

## 快速开始

### 环境要求

安装依赖：

```bash
pip install -r requirements.txt
```

运行优化：

```bash
python run_optimization.py --config <config_file>
```

### 基本用法

```bash
# 束斑优化
python run_optimization.py --config config_beam.json --budget 50

# 轨道优化（全0模式）
python run_optimization.py --config config_orbit.json --mode zero --budget 50

# 轨道优化（参考轨道模式）
python run_optimization.py --config config_orbit.json --mode ref --budget 50
```

## 配置说明

详细配置参数说明：

- **[束斑优化配置](docs/beam_optimization.md)** - 束流尺寸优化的配置参数
- **[轨道优化配置](docs/orbit_optimization.md)** - 轨道优化的配置参数
- **[统一接口设计](docs/unified_interface.md)** - 如何添加新的目标函数

### 统一配置格式

```json
{
  "name": "任务名称",
  "objective": {
    "type": "beam_size|orbit",
    "read_pvs": ["PV列表"],
    "params": {}
  },
  "devices": {
    "correctors|quadrupoles": [
      {"pv": "地址", "range": [最小, 最大]}
    ]
  },
  "optimization": {
    "algorithm": "Compass|NGOpt|CMA|PSO",
    "budget": 50
  }
}
```

## 支持的优化类型

| 类型 | 说明 | 文档 |
|------|------|------|
| `beam_size` | 束流尺寸优化 | [详细说明](docs/beam_optimization.md) |
| `orbit` | 轨道优化 | [详细说明](docs/orbit_optimization.md) |

## 统一入口

`run_optimization.py` 是所有优化任务的统一入口，支持：

- `--config`: 配置文件路径（必需）
- `--budget`: 覆盖配置的迭代次数
- `--algorithm`: 覆盖配置的算法
- `--mode`: 轨道优化模式 (`zero`=全0, `ref`=参考轨道)

```bash
# 指定迭代次数
python run_optimization.py --config config_beam.json --budget 100

# 指定算法
python run_optimization.py --config config_beam.json --algorithm NGOpt
```

## 详细文档

- **[文档首页](docs/index.md)** - 文档目录
- **[束斑优化](docs/beam_optimization.md)** - 工作原理、配置参数
- **[轨道优化](docs/orbit_optimization.md)** - 两种模式、配置参数
- **[统一接口](docs/unified_interface.md)** - 添加新目标函数
- **[UI 设计](docs/ui_design.md)** - 界面规范（待补充）

## 扩展系统

新增优化任务只需：

1. 在 `core/objectives/` 下编写目标函数类
2. 使用 `@register_objective` 注册
3. 创建配置文件
4. 运行 `run_optimization.py --config <your_config.json>`

详细说明请参阅：[统一接口设计](docs/unified_interface.md)

## 结果输出

优化完成后：
- 结果保存至 `results/` 目录（HDF5 格式）
- 可视化图片自动生成
- 终端显示收敛曲线和最优参数

## 核心模块

| 模块 | 说明 |
|------|------|
| `core/objectives/` | 目标函数实现和注册机制 |
| `core/optimizer.py` | Nevergrad 优化器封装 |
| `core/simulator.py` | EPICS PV 模拟器（用于测试） |
| `tools/visualize.py` | 结果可视化 |

## 依赖安装

```bash
pip install -r requirements.txt
```

## 支持

- 常规问题: zhangny@sari.ac.cn, zhangbw@sari.ac.cn
- 版本: 2.0
