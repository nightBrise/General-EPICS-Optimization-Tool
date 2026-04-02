"""UI 主题配置

统一使用 slate 色相，低饱和蓝灰色系，适合加速器控制室环境。
仅使用 Gradio 主题参数，不添加自定义 CSS。
"""
import gradio as gr


def get_unified_theme():
    """统一低饱和主题 - 适合加速器控制室环境

    使用 slate 色相，低饱和蓝灰色系，长时间盯屏不疲劳。
    仅使用 Gradio 主题参数，不添加自定义 CSS。

    Returns:
        gr.Theme: 配置好的主题对象
    """
    # Gradio 6.x 使用 theme.set() 方法自定义主题参数
    return gr.themes.Soft(
        primary_hue="slate",
        secondary_hue="slate",
    ).set(
        background_fill_primary="#F7FAFC",
        container_radius="6px",
        body_text_color="#2D3748",
        block_title_text_color="#1A202C",
        border_color_primary="#E2E8F0",
        block_shadow="0 1px 4px rgba(0,0,0,0.06)",
    )
