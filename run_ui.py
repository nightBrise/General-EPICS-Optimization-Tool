#!/usr/bin/env python3
"""SXFEL 优化工具 Web 界面启动器

使用方法:
    python run_ui.py                              # 启动欢迎页
    python run_ui.py --type beam --port 7860      # 启动束流优化 UI
    python run_ui.py --type orbit --port 7861     # 启动轨道优化 UI
    python run_ui.py --type beam --backend epics  # 使用真实 EPICS 后端
"""
import argparse
import socket


def find_available_port(start_port, max_attempts=10):
    """查找可用端口，从 start_port 开始尝试"""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"无法在 {start_port}-{start_port + max_attempts - 1} 范围内找到可用端口")


def main():
    parser = argparse.ArgumentParser(
        description='SXFEL 优化工具 Web 界面',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python run_ui.py                        # 启动欢迎页
    python run_ui.py --type beam            # 启动束流优化 UI (端口 7860)
    python run_ui.py --type orbit          # 启动轨道优化 UI (端口 7861)
    python run_ui.py --type all            # 启动所有 UI（需要多个终端）
        """
    )
    parser.add_argument(
        '--type',
        choices=['beam', 'orbit', 'all'],
        default='all',
        help='启动哪种 UI (beam=束流优化, orbit=轨道优化, all=欢迎页)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=7860,
        help='服务端口 (默认 7860)'
    )
    parser.add_argument(
        '--backend',
        choices=['simulator', 'epics'],
        default='simulator',
        help='数据后端 (simulator=模拟器, epics=真实 EPICS)'
    )
    args = parser.parse_args()

    if args.type == 'beam':
        from ui.beam_app import create_beam_ui
        from ui.theme import get_unified_theme
        from core.epics_backend import set_backend
        set_backend(args.backend == 'simulator')
        port = find_available_port(args.port)
        if port != args.port:
            print(f"端口 {args.port} 被占用，自动使用端口 {port}")
        print(f"启动束流尺寸优化 UI，访问地址: http://localhost:{port}")
        print(f"后端模式: {'模拟器' if args.backend == 'simulator' else '真实 EPICS'}")
        app = create_beam_ui(default_backend=args.backend)
        app.launch(server_name="0.0.0.0", server_port=port, theme=get_unified_theme())

    elif args.type == 'orbit':
        from ui.orbit_app import create_orbit_ui
        from ui.theme import get_unified_theme
        from core.epics_backend import set_backend
        set_backend(args.backend == 'simulator')
        port = find_available_port(args.port)
        if port != args.port:
            print(f"端口 {args.port} 被占用，自动使用端口 {port}")
        print(f"启动轨道优化 UI，访问地址: http://localhost:{port}")
        print(f"后端模式: {'模拟器' if args.backend == 'simulator' else '真实 EPICS'}")
        app = create_orbit_ui(default_backend=args.backend)
        app.launch(server_name="0.0.0.0", server_port=port, theme=get_unified_theme())

    else:  # all - 欢迎页
        from ui.theme import get_unified_theme

        with gr.Blocks(title="SXFEL 优化工具", theme=get_unified_theme()) as main_app:
            gr.Markdown("# SXFEL 优化工具")
            gr.Markdown("通用加速器优化框架，支持束流尺寸优化、轨道优化等多种优化任务。")

            gr.Markdown("---")

            gr.Markdown("## 选择优化工具")
            gr.Markdown("请点击下方按钮启动对应的优化界面：")

            with gr.Row():
                with gr.Column(scale=1):
                    pass
                with gr.Column(scale=1):
                    beam_btn = gr.Button("束流尺寸优化 →", variant="primary", size="lg")
                with gr.Column(scale=1):
                    pass
                with gr.Column(scale=1):
                    orbit_btn = gr.Button("轨道优化 →", variant="secondary", size="lg")
                with gr.Column(scale=1):
                    pass

            gr.Markdown("---")

            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 束流尺寸优化")
                    gr.Markdown("""
                    - 调整四极磁铁、校正子等设备
                    - 最小化束流尺寸同时优化圆度
                    - 实时显示束流图像
                    - 端口: 7860
                    """)

                with gr.Column(scale=1):
                    gr.Markdown("### 轨道优化")
                    gr.Markdown("""
                    - 调整校正子使 BPM 轨道接近零
                    - 支持参考轨道模式
                    - 实时显示 BPM 读数
                    - 端口: 7861
                    """)

            beam_info = gr.Textbox(
                label="束流优化状态",
                value="请点击上方「束流尺寸优化」按钮启动",
                interactive=False
            )
            orbit_info = gr.Textbox(
                label="轨道优化状态",
                value="请点击上方「轨道优化」按钮启动",
                interactive=False
            )

            def open_beam():
                return "请在浏览器新标签页打开: http://localhost:7860"

            def open_orbit():
                return "请在浏览器新标签页打开: http://localhost:7861"

            beam_btn.click(fn=open_beam, outputs=[beam_info])
            orbit_btn.click(fn=open_orbit, outputs=[orbit_info])

        print(f"启动欢迎页，访问地址: http://localhost:{args.port}")
        print("请在浏览器中打开欢迎页，然后点击按钮启动具体的优化界面")
        print()
        print("提示：要同时使用两种优化，需要：")
        print("  1. 终端1: python run_ui.py --type beam --port 7860")
        print("  2. 终端2: python run_ui.py --type orbit --port 7861")
        print("  3. 浏览器中打开两个标签页")

        main_app.launch(
            server_name="0.0.0.0",
            server_port=args.port,
            prevent_thread_lock=True
        )


if __name__ == "__main__":
    main()
