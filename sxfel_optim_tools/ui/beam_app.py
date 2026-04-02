"""束流优化 Gradio Web 界面

通过调整磁铁参数使束流尺寸最小化同时优化圆度。
"""
import gradio as gr

from ui.components.common import (
    create_common_config_panel,
    create_device_config_panel,
    parse_devices
)
from ui.components.threading import OptimizationRunner, OptimizationProgress
from ui.theme import get_unified_theme
from core.epics_backend import set_backend


# 全局优化运行器
runner = OptimizationRunner()


def build_config_from_ui(
    quadrupoles,
    correctors,
    phaseshifters,
    amplifiers,
    camera_pv,
    img_width,
    img_height,
    num_averages,
    algorithm,
    budget,
    early_stopping,
    patience,
    min_improvement
):
    """从 UI 配置构建优化配置字典"""
    config = {
        'name': 'beam_size',
        'description': '束流尺寸优化',
        'objective': {
            'type': 'beam_size',
            'read_pvs': [camera_pv],
            'params': {
                'shape': [int(img_width), int(img_height)],
                'num_averages': int(num_averages),
                'maintain_position': True
            }
        },
        'camera': {
            'pv': camera_pv,
            'shape': [int(img_width), int(img_height)]
        },
        'optimization': {
            'algorithm': algorithm,
            'budget': int(budget),
            'early_stopping': {
                'enabled': early_stopping,
                'patience': int(patience),
                'min_relative_improvement': float(min_improvement)
            }
        },
        'devices': {
            'quadrupoles': parse_devices(quadrupoles),
            'correctors': parse_devices(correctors),
            'phaseshifters': parse_devices(phaseshifters),
            'amplifiers': parse_devices(amplifiers)
        }
    }
    return config


def on_progress(iteration, budget, current_score, best_score):
    """进度更新回调"""
    return f"迭代 {iteration}/{budget}: 当前={current_score:.4f}, 最佳={best_score:.4f}"


def poll_progress():
    """轮询进度（供 app.load 使用）"""
    progress = runner.get_progress()

    if progress.error:
        return (
            {"状态": "错误", "消息": progress.error},
            None,
            None,
            None
        )

    if not progress.running and progress.history:
        # 优化完成
        history = progress.history
        best_params = history.get('best_params', [])
        device_names = history.get('device_names', [])

        # 生成参数表
        params_data = []
        if best_params and device_names:
            params_data = [[n, f"{v:.4f}"] for n, v in zip(device_names, best_params)]

        summary = {
            "状态": "完成",
            "最佳评分": f"{progress.best_score:.6f}" if progress.best_score else "N/A"
        }
        return (summary, None, params_data, "完成")

    if progress.running:
        # 运行中
        pct = progress.iteration / progress.budget if progress.budget else 0
        status = {
            "迭代": f"{progress.iteration}/{progress.budget}",
            "当前": f"{progress.current_score:.4f}" if progress.current_score else "N/A",
            "最佳": f"{progress.best_score:.4f}" if progress.best_score else "N/A",
            "进度": f"{pct*100:.1f}%"
        }
        return (status, None, None, "运行中...")

    # 空闲
    return (
        {"状态": "就绪"},
        None,
        None,
        "就绪"
    )


def create_beam_ui(default_backend='simulator'):
    """创建束流优化 UI

    Args:
        default_backend: 默认后端 ('simulator' 或 'epics')
    """
    # 初始化后端
    set_backend(default_backend == 'simulator')

    with gr.Blocks(title="束流尺寸优化") as app:
        gr.Markdown("# 束流尺寸优化")
        gr.Markdown("通过调整磁铁参数使束流尺寸最小化同时优化圆度")

        # 后端状态显示（只读）
        backend_label = "🟢 模拟器" if default_backend == 'simulator' else "🔴 真实 EPICS"
        gr.Markdown(f"**当前后端: {backend_label}**")

        with gr.Row():
            # 左侧：设备配置
            with gr.Column(scale=1):
                gr.Markdown("### 设备配置")

                quad_config = create_device_config_panel("四极磁铁")
                corr_config = create_device_config_panel("校正子")
                phase_config = create_device_config_panel("相移器")
                amp_config = create_device_config_panel("放大器")

            # 右侧：通用配置和状态
            with gr.Column(scale=1):
                gr.Markdown("### 优化参数")
                common = create_common_config_panel()

                gr.Markdown("### 相机配置")
                camera_pv = gr.Textbox(
                    label="相机 PV",
                    value="LA-BI:PRF22:RAW:ArrayData"
                )
                with gr.Row():
                    img_width = gr.Number(value=1392, label="图像宽度")
                    img_height = gr.Number(value=1040, label="图像高度")
                num_averages = gr.Number(value=3, label="平均帧数")

        # 实时显示
        with gr.Row():
            beam_image = gr.Image(type="pil", label="实时束流图像")
            convergence_plot = gr.Plot(label="收敛曲线")

        # 状态和进度
        progress_label = gr.Label(label="进度")

        # 最佳参数表格
        params_table = gr.Dataframe(
            headers=["设备", "最佳值"],
            label="最佳参数",
            value=[],
            interactive=False
        )

        # 事件绑定
        def start_optimization(
            quadrupoles, correctors, phaseshifters, amplifiers,
            camera_pv, img_width, img_height, num_averages,
            algorithm, budget, early_stopping, patience, min_improvement
        ):
            """开始优化"""
            config = build_config_from_ui(
                quadrupoles, correctors, phaseshifters, amplifiers,
                camera_pv, img_width, img_height, num_averages,
                algorithm, budget, early_stopping, patience, min_improvement
            )
            return runner.start(config, progress_callback=on_progress)

        common['start_btn'].click(
            fn=start_optimization,
            inputs=[
                quad_config['table'], corr_config['table'],
                phase_config['table'], amp_config['table'],
                camera_pv, img_width, img_height, num_averages,
                common['algorithm'], common['budget'],
                common['early_stopping'], common['patience'], common['min_improvement']
            ],
            outputs=[common['status_text']]
        )

        common['stop_btn'].click(
            fn=runner.stop,
            outputs=[common['status_text']]
        )

        # 定时更新进度
        timer = gr.Timer(value=0.5)
        timer.tick(
            fn=poll_progress,
            outputs=[progress_label, convergence_plot, params_table, common['status_text']]
        )

    return app


if __name__ == "__main__":
    app = create_beam_ui()
    app.launch(server_name="0.0.0.0", server_port=7860)
