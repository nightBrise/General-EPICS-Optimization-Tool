# UI 设计规范

## 状态：待补充

此文档待 UI 实现后补充详细规范。

---

## 计划中的 UI 组件

### 1. 统一入口界面

- 配置文件选择器
- 算法选择下拉框
- 迭代次数滑块
- 开始/停止按钮
- 实时收敛曲线
- 结果数据表格

### 2. Gradio 界面结构

```python
# ui/app.py
import gradio as gr

def create_app():
    with gr.Blocks(title="SXFEL Optimization Tools") as app:
        gr.Markdown("# SXFEL Optimization Tools")

        with gr.Row():
            config_file = gr.FileExplorer(...)
            config_preview = gr.JSON(...)

        with gr.Row():
            algorithm = gr.Dropdown([...])
            budget = gr.Slider(...)

        run_btn = gr.Button("开始优化", variant="primary")

    return app
```

### 3. 组件列表

- `ui/__init__.py`
- `ui/app.py` - 统一 UI 入口
- `ui/components/__init__.py`
- `ui/components/threading.py` - 线程管理
- `ui/components/file_handler.py` - 文件处理
- `ui/components/plots.py` - 绘图组件

## 设计原则

待补充。
