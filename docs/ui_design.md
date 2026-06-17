# Web UI

## 状态

⚠️ Web UI 模块（`run_ui.py`, `ui/`）基于旧架构，待更新以适配新的 `GenericOptimizer` API。

当前推荐使用命令行接口：

```bash
python run_optimization.py --config configs/orbit_full.json
python run_optimization.py --config config.json --simulator -y
```

## 组件

- `run_ui.py` — Gradio 入口
- `ui/beam_app.py` — 束流优化界面
- `ui/orbit_app.py` — 轨道优化界面
- `ui/theme.py` — 主题
- `ui/components/` — 通用组件
