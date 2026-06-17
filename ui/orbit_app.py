"""轨道优化 Gradio Web 界面

通过调整校正子使 BPM 轨道接近零或参考值。
"""
import gradio as gr

from ui.components.common import (
    create_common_config_panel,
    create_device_config_panel,
    parse_devices
)
from ui.components.threading import OptimizationRunner
from ui.theme import get_unified_theme
from core.epics_backend import set_backend


# 全局优化运行器
runner = OptimizationRunner()


def build_orbit_config_from_ui(
    correctors,
    bpm_pvs,
    reference_orbit,
    algorithm,
    budget,
    mode,
    early_stopping,
    patience,
    min_improvement
):
    """从 UI 配置构建轨道优化配置"""
    # 解析校正子
    corrector_list = parse_devices(correctors)

    # 解析 BPM PV 列表
    bpm_list = []
    for row in bpm_pvs:
        if row[0]:  # PV 不为空
            bpm_list.append(row[0])

    # 构建参考轨道字典
    ref_orbit = {}
    if mode == 'ref' and reference_orbit:
        for pv, value in zip(bpm_list, reference_orbit):
            try:
                ref_orbit[pv] = float(value) if value else 0.0
            except (ValueError, TypeError):
                ref_orbit[pv] = 0.0

    config = {
        'name': 'orbit',
        'description': '轨道优化',
        'objective': {
            'type': 'orbit',
            'read_pvs': bpm_list,
            'params': {
                'reference_orbit': ref_orbit if mode == 'ref' else {}
            }
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
            'correctors': corrector_list
        }
    }
    return config


def create_orbit_ui(default_backend='simulator'):
    """创建轨道优化 UI

    Args:
        default_backend: 默认后端 ('simulator' 或 'epics')
    """
    # 初始化后端
    set_backend(default_backend == 'simulator')

    with gr.Blocks(title="轨道优化") as app:
        gr.Markdown("# 轨道优化")
        gr.Markdown("通过调整校正子使 BPM 轨道接近零或参考值")

        # 后端状态显示（只读）
        backend_label = "🟢 模拟器" if default_backend == 'simulator' else "🔴 真实 EPICS"
        gr.Markdown(f"**当前后端: {backend_label}**")

        with gr.Row():
            # 左侧：设备配置
            with gr.Column(scale=1):
                gr.Markdown("### 校正子配置")
                corr_config = create_device_config_panel("校正子")

                gr.Markdown("### BPM PV 配置")
                bpm_add_btn = gr.Button("+ 添加 BPM", size="sm")

                # BPM PV 表格（简化版：每行一个 PV）
                bpm_pvs_data = []
                for i in range(1, 11):
                    bpm_pvs_data.append([f"LA-BI:SBPM{i}:POS_X"])
                    bpm_pvs_data.append([f"LA-BI:SBPM{i}:POS_Y"])

                bpm_table = gr.Dataframe(
                    headers=["BPM PV"],
                    label="BPM PV 列表（每个 PV 占一行）",
                    value=bpm_pvs_data,
                    interactive=True
                )

            # 右侧：通用配置
            with gr.Column(scale=1):

                gr.Markdown("### 优化参数")
                common = create_common_config_panel()

                gr.Markdown("### 模式选择")
                mode = gr.Radio(
                    ["zero", "ref"],
                    value="zero",
                    label="优化模式",
                    info="zero=优化到全0, ref=优化到参考轨道"
                )

                # 参考轨道表格
                ref_values_data = [[0.0] for _ in range(len(bpm_pvs_data))]
                ref_orbit_table = gr.Dataframe(
                    headers=["参考轨道值"],
                    label="参考轨道（ref 模式）",
                    value=ref_values_data,
                    visible=False
                )

                def toggle_ref_table(selected_mode):
                    """切换参考轨道表格可见性"""
                    return gr.update(visible=(selected_mode == 'ref'))

                mode.change(
                    fn=toggle_ref_table,
                    inputs=[mode],
                    outputs=[ref_orbit_table]
                )

        # BPM 实时读数表格
        bpm_readings = gr.Dataframe(
            headers=["BPM", "X", "Y"],
            label="实时 BPM 读数",
            value=[],
            interactive=False
        )

        # 收敛曲线
        convergence_plot = gr.Plot(label="收敛曲线")

        # 最佳参数表格
        params_table = gr.Dataframe(
            headers=["校正子", "最佳值"],
            label="最佳校正子参数",
            value=[],
            interactive=False
        )

        # 进度
        progress_label = gr.Label(label="进度")

        # 事件绑定
        def start_optimization(
            correctors,
            bpm_pvs,
            reference_orbit,
            algorithm,
            budget,
            mode,
            early_stopping,
            patience,
            min_improvement
        ):
            """开始优化"""
            config = build_orbit_config_from_ui(
                correctors,
                bpm_pvs,
                reference_orbit,
                algorithm,
                budget,
                mode,
                early_stopping,
                patience,
                min_improvement
            )
            return runner.start(config)

        common['start_btn'].click(
            fn=start_optimization,
            inputs=[
                corr_config['table'],
                bpm_table,
                ref_orbit_table,
                common['algorithm'],
                common['budget'],
                mode,
                common['early_stopping'],
                common['patience'],
                common['min_improvement']
            ],
            outputs=[common['status_text']]
        )

        common['stop_btn'].click(
            fn=runner.stop,
            outputs=[common['status_text']]
        )

        # 定时更新进度
        def poll_progress():
            """轮询进度"""
            progress = runner.get_progress()

            if progress.error:
                return (
                    {"状态": "错误", "消息": progress.error},
                    None,
                    None,
                    "错误"
                )

            if not progress.running and progress.history:
                history = progress.history
                best_params = history.get('best_params', [])
                device_names = history.get('device_names', [])

                params_data = []
                if best_params and device_names:
                    params_data = [[n, f"{v:.4f}"] for n, v in zip(device_names, best_params)]

                summary = {
                    "状态": "完成",
                    "最佳评分": f"{progress.best_score:.6f}" if progress.best_score else "N/A"
                }
                return (summary, None, params_data, "完成")

            if progress.running:
                pct = progress.iteration / progress.budget if progress.budget else 0
                status = {
                    "迭代": f"{progress.iteration}/{progress.budget}",
                    "当前": f"{progress.current_score:.4f}" if progress.current_score else "N/A",
                    "最佳": f"{progress.best_score:.4f}" if progress.best_score else "N/A",
                    "进度": f"{pct*100:.1f}%"
                }
                return (status, None, None, "运行中...")

            return (
                {"状态": "就绪"},
                None,
                None,
                "就绪"
            )

        timer = gr.Timer(value=0.5)
        timer.tick(
            fn=poll_progress,
            outputs=[progress_label, convergence_plot, params_table, common['status_text']]
        )

    return app


if __name__ == "__main__":
    app = create_orbit_ui()
    app.launch(server_name="0.0.0.0", server_port=7861)
