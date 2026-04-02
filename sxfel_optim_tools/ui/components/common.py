"""通用 UI 组件

提供束流优化和轨道优化共用的 Gradio 组件。
"""
import gradio as gr


def create_common_config_panel():
    """创建通用配置面板（算法、迭代次数、早停）

    Returns:
        dict: 包含各组件引用的字典
    """
    with gr.Column(scale=1):
        gr.Markdown("**优化参数**")

        algorithm = gr.Dropdown(
            ["Compass", "NGOpt", "CMA", "PSO"],
            value="Compass",
            label="优化算法"
        )

        budget = gr.Number(
            value=50,
            minimum=10,
            maximum=500,
            step=5,
            label="迭代次数"
        )

        with gr.Row():
            early_stopping = gr.Checkbox(value=True, label="早停")
            patience = gr.Number(value=10, minimum=3, maximum=50, label="耐心度")
            min_improvement = gr.Number(
                value=0.005,
                minimum=0.0001,
                maximum=0.1,
                label="最小改进"
            )

        with gr.Row():
            start_btn = gr.Button("开始优化", variant="primary")
            stop_btn = gr.Button("停止", variant="secondary", interactive=False)

        status_text = gr.Textbox(
            label="状态",
            lines=2,
            value="就绪"
        )

    return {
        'algorithm': algorithm,
        'budget': budget,
        'early_stopping': early_stopping,
        'patience': patience,
        'min_improvement': min_improvement,
        'start_btn': start_btn,
        'stop_btn': stop_btn,
        'status_text': status_text
    }


def create_device_config_panel(device_type: str, devices: list = None):
    """创建设备配置面板

    Args:
        device_type: 设备类型（如 "四极磁铁", "校正子"）
        devices: 初始设备列表，每个设备为 dict: {'pv': str, 'range': [min, max]}

    Returns:
        dict: 包含 add_btn 和 table 引用的字典
    """
    with gr.Accordion(device_type, open=True):
        add_btn = gr.Button(f"+ 添加 {device_type}", size="sm")

        # 设备表格：PV, 最小值, 最大值
        devices_data = []
        if devices:
            for dev in devices:
                if isinstance(dev, dict):
                    devices_data.append([dev['pv'], dev['range'][0], dev['range'][1]])

        table = gr.Dataframe(
            headers=["PV", "最小值", "最大值"],
            label=f"{device_type} 列表",
            value=devices_data if devices_data else [["", 0, 0]],
            interactive=True
        )

    return {'add_btn': add_btn, 'table': table}


def parse_devices(device_list: list) -> list:
    """解析设备表格数据

    Args:
        device_list: Dataframe 返回的设备列表

    Returns:
        list: 设备字典列表 [{'pv': str, 'range': [min, max]}, ...]
    """
    devices = []
    for row in device_list:
        if row[0]:  # PV 不为空
            try:
                devices.append({
                    'pv': row[0],
                    'range': [float(row[1]), float(row[2])]
                })
            except (ValueError, TypeError):
                continue
    return devices
