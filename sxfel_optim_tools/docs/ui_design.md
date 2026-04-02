# SXFEL 优化工具 UI 设计规范

## 1. 概述

### 1.1 设计目标

本规范为 SXFEL（软X射线自由电子激光）优化工具提供统一的 Web 界面视觉风格。

**核心要求：**
- **低饱和、不刺眼** - 适合加速器控制室环境，长时间盯屏不疲劳
- **清晰直观** - 科学仪器界面风格，信息层次分明
- **统一入口** - 用户只从欢迎页进入，再选择具体功能

### 1.2 设计原则

1. **仅使用 Gradio 主题参数** - 不添加自定义 CSS，保持代码简洁
2. **低饱和 slate 色系** - 沉稳专业，适合长时间使用
3. **居中卡片式布局** - 欢迎页采用现代仪表盘风格
4. **一致的布局比例** - 子页面保持固定的布局结构

---

## 2. 颜色规范

### 2.1 主色调 - Slate 色相

统一使用 Gradio 内置的 `slate` 色相，该色相为低饱和蓝灰色，适合专业控制室环境。

```python
gr.themes.Soft(
    primary_hue="slate",
    secondary_hue="slate",
)
```

### 2.2 主题参数配置

通过 `.spread()` 方法自定义主题参数：

```python
THEME_CONFIG = {
    "background_fill": "#F7FAFC",           # 极浅灰背景 (slate-50)
    "container_radius": "6px",              # 柔和圆角
    "body_text": "#2D3748",                # 深灰正文 (slate-800)
    "heading_text": "#1A202C",             # 近黑标题 (slate-900)
    "border": "#E2E8F0",                   # 淡边框 (slate-200)
    "shadow": "0 1px 4px rgba(0,0,0,0.06)" # 柔和阴影
}
```

### 2.3 颜色用途对照表

| 颜色代码 | 用途 | 使用场景 |
|----------|------|----------|
| `#F7FAFC` | 背景色 | 页面整体背景 |
| `#1A202C` | 标题色 | H1 页面标题 |
| `#2D3748` | 正文色 | H2/H3 区块标题、正文 |
| `#4A5568` | 辅助色 | 次要文字、标签 |
| `#718096` | 占位色 | placeholder、提示文字 |
| `#E2E8F0` | 边框色 | 分隔线、组件边框 |

### 2.4 Gradio 按钮 Variant

| Variant | 用途 | 说明 |
|---------|------|------|
| `variant="primary"` | 主要操作 | "开始优化"按钮 |
| `variant="secondary"` | 次要操作 | "停止"按钮 |

---

## 3. 字体规范

### 3.1 字号层级

| 层级 | Markdown 语法 | 默认样式 | 用途 |
|------|---------------|----------|------|
| H1 | `# 标题` | 28px, bold | 页面主标题 |
| H2 | `## 标题` | 20px, semibold | 大区块标题 |
| H3 | `### 标题` | 16px, semibold | 子区块标题 |
| Body | 正文 | 14px, regular | 说明文字 |

### 3.2 Markdown 使用规范

```python
# 页面主标题
gr.Markdown("# 束流尺寸优化")

# 页面描述
gr.Markdown("通过调整磁铁参数使束流尺寸最小化同时优化圆度")

# 区块标题（H3 层级）
gr.Markdown("### 优化参数")

# 说明文字
gr.Markdown("请输入设备 PV 地址")
```

---

## 4. 布局规范

### 4.1 页面布局比例

| 页面 | 布局 | 说明 |
|------|------|------|
| 欢迎页 | 居中卡片式 | 标题居中，按钮居中 |
| 束流优化 | 左1:右1 | 设备配置区与参数控制区占比相同 |
| 轨道优化 | 左1:右1 | 左右对称 |

### 4.2 欢迎页布局

```
┌──────────────────────────────────────────────────┐
│                                                  │
│              SXFEL 优化工具                       │
│    通用加速器优化框架，支持束流尺寸优化、轨道优化...    │
│                                                  │
│        ┌─────────────┐   ┌─────────────┐        │
│        │  束流尺寸优化 │   │   轨道优化   │        │
│        │     →       │   │     →       │        │
│        └─────────────┘   └─────────────┘        │
│                                                  │
│  ┌───────────────────────────────────────────┐  │
│  │  束流尺寸优化            轨道优化           │  │
│  │  · 调整四极磁铁...       · 调整校正子...    │  │
│  └───────────────────────────────────────────┘  │
│                                                  │
└──────────────────────────────────────────────────┘
```

### 4.3 束流优化页面布局

```
┌──────────────────────────────────────────────────┐
│  # 束流尺寸优化                                   │
│  通过调整磁铁参数使束流尺寸最小化同时优化圆度         │
├────────────────────────┬───────────────────────────┤
│  ### 设备配置         │  ### 优化参数             │
│                       │                           │
│  ▾ 四极磁铁           │  [算法 ▼]                │
│  ▾ 校正子             │  [迭代次数]               │
│  ▾ 相移器             │  [早停] [耐心度]         │
│  ▾ 放大器             │                           │
│                       │  [开始优化] [停止]        │
│                       │                           │
│                       │  ### 相机配置             │
│                       │  [相机 PV]               │
│                       │  [宽度] [高度]           │
├────────────────────────┴───────────────────────────┤
│  [实时束流图像]           [收敛曲线]                │
├──────────────────────────────────────────────────┤
│  [优化进度 Label]                                │
│  [最佳参数 Table]                                │
└──────────────────────────────────────────────────┘
```

### 4.4 轨道优化页面布局

```
┌──────────────────────────────────────────────────┐
│  # 轨道优化                                       │
│  通过调整校正子使 BPM 轨道接近零或参考值            │
├────────────────────────────┬─────────────────────┤
│  ### 校正子配置            │  ### 优化参数        │
│                            │                     │
│  ▾ 校正子列表               │  [算法 ▼]           │
│  [+ 添加校正子]            │  [迭代次数]         │
│                            │  [早停] [耐心度]    │
│  ### BPM PV 配置           │                     │
│  [+ 添加 BPM]             │  (模式选择 Radio)   │
│                            │                     │
│  [BPM PV Table]           │  [开始优化] [停止]  │
│                            │                     │
├────────────────────────────┴─────────────────────┤
│  [实时 BPM 读数 Table]                           │
│  [收敛曲线]                                      │
│  [最佳参数 Table]                                │
│  [优化进度 Label]                                │
└──────────────────────────────────────────────────┘
```

---

## 5. 组件规范

### 5.1 按钮组件

```python
# 主要操作按钮
start_btn = gr.Button(
    "开始优化",
    variant="primary",
    size="lg"
)

# 次要操作按钮
stop_btn = gr.Button(
    "停止",
    variant="secondary",
    size="lg"
)

# 添加按钮
add_btn = gr.Button(
    "+ 添加",
    size="sm"
)
```

### 5.2 输入组件

```python
# 文本输入
text_input = gr.Textbox(
    label="设备 PV",
    value="LA-BI:SBPM1:POS_X"
)

# 数字输入
number_input = gr.Number(
    label="迭代次数",
    value=50,
    minimum=10,
    maximum=500,
    step=5
)

# 下拉选择
dropdown = gr.Dropdown(
    label="优化算法",
    choices=["Compass", "NGOpt", "CMA", "PSO"],
    value="Compass"
)

# 复选框
checkbox = gr.Checkbox(
    label="启用早停",
    value=True
)

# 单选框
radio = gr.Radio(
    label="优化模式",
    choices=["zero", "ref"],
    value="zero"
)
```

### 5.3 展示组件

```python
# 数据表格（输入）
input_table = gr.Dataframe(
    headers=["PV", "最小值", "最大值"],
    label="设备列表",
    value=[["", 0, 0]],
    interactive=True
)

# 数据表格（输出/只读）
output_table = gr.Dataframe(
    headers=["设备", "最佳值"],
    label="最佳参数",
    value=[],
    interactive=False
)

# 图像显示
image = gr.Image(
    type="pil",
    label="实时束流图像"
)

# 图表显示
plot = gr.Plot(
    label="收敛曲线"
)

# 进度标签
progress_label = gr.Label(
    label="优化进度"
)

# 状态文本
status_text = gr.Textbox(
    label="状态",
    value="就绪",
    lines=2,
    interactive=False
)
```

### 5.4 布局组件

```python
# 折叠面板
with gr.Accordion("四极磁铁", open=True):
    add_btn = gr.Button("+ 添加四极磁铁", size="sm")
    table = gr.Dataframe(...)

# 水平布局
with gr.Row():
    with gr.Column(scale=2):
        # 左侧内容
    with gr.Column(scale=1):
        # 右侧内容
```

---

## 6. 状态显示规范

### 6.1 状态定义

| 状态 | 含义 | 触发场景 |
|------|------|----------|
| 就绪 | 等待用户操作 | 初始状态、用户停止后 |
| 运行中 | 优化正在进行 | 点击开始优化后 |
| 完成 | 优化成功结束 | 达到迭代上限或早停触发 |
| 错误 | 优化出错 | 连接超时、设备故障等 |

### 6.2 状态显示格式

```python
# 就绪状态
{"状态": "就绪"}

# 运行中状态
{
    "迭代": "25/100",
    "当前": "0.0234",
    "最佳": "0.0189",
    "进度": "25.0%"
}

# 完成状态
{
    "状态": "完成",
    "最佳评分": "0.0189"
}

# 错误状态
{
    "状态": "错误",
    "消息": "连接超时"
}
```

---

## 7. 主题模块

### 7.1 主题配置文件

```python
# ui/theme.py
import gradio as gr

def get_unified_theme():
    """统一低饱和主题 - 适合加速器控制室环境

    使用 slate 色相，低饱和蓝灰色系，长时间盯屏不疲劳。
    仅使用 Gradio 主题参数，不添加自定义 CSS。
    """
    return gr.themes.Soft(
        primary_hue="slate",
        secondary_hue="slate",
    ).spread({
        "background_fill": "#F7FAFC",
        "container_radius": "6px",
        "body_text": "#2D3748",
        "heading_text": "#1A202C",
        "border": "#E2E8F0",
        "shadow": "0 1px 4px rgba(0,0,0,0.06)",
    })
```

---

## 8. 文件结构规范

### 8.1 UI 模块结构

```
ui/
├── __init__.py              # 模块导出
├── theme.py                  # 主题配置 (新建)
├── beam_app.py              # 束流优化 UI
├── orbit_app.py             # 轨道优化 UI
└── components/
    ├── __init__.py
    ├── common.py            # 通用组件
    └── threading.py         # 线程管理
```

### 8.2 主题应用规范

所有 UI 页面必须使用 `get_unified_theme()` 创建 Blocks：

```python
from ui.theme import get_unified_theme

def create_page():
    theme = get_unified_theme()
    with gr.Blocks(title="页面标题", theme=theme) as app:
        # 页面内容
        pass
    return app
```

---

## 9. 实现清单

### 9.1 文件修改列表

| 序号 | 文件 | 操作 | 内容 |
|------|------|------|------|
| 1 | `ui/theme.py` | 新建 | 主题配置函数 |
| 2 | `run_ui.py` | 修改 | 应用主题 + 居中卡片布局 |
| 3 | `ui/beam_app.py` | 修改 | 应用主题 |
| 4 | `ui/orbit_app.py` | 修改 | 应用主题 |
| 5 | `ui/components/common.py` | 修改 | 应用主题 |
| 6 | `ui/__init__.py` | 修改 | 导出 theme |

### 9.2 验收标准

1. **欢迎页** - 标题居中，两个功能按钮居中显示
2. **束流优化页** - 左2:右1 布局，slate 主题
3. **轨道优化页** - 左1:右1 布局，slate 主题
4. **配色一致** - 所有页面使用相同的 slate 主题配置
5. **无自定义 CSS** - 仅通过 Gradio 主题参数实现

---

## 10. 附录：完整代码示例

### 欢迎页完整模板

```python
from ui.theme import get_unified_theme

def create_welcome_page():
    theme = get_unified_theme()

    with gr.Blocks(title="SXFEL 优化工具", theme=theme) as app:
        gr.Markdown("# SXFEL 优化工具")
        gr.Markdown("通用加速器优化框架，支持束流尺寸优化、轨道优化等多种优化任务。")

        gr.Markdown("---")

        gr.Markdown("## 选择优化工具")
        gr.Markdown("请点击下方按钮启动对应的优化界面：")

        with gr.Row():
            beam_btn = gr.Button("束流尺寸优化 →", variant="primary", size="lg")
            orbit_btn = gr.Button("轨道优化 →", variant="secondary", size="lg")

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

        with gr.Row():
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

        beam_btn.click(fn=open_beam, outputs=[beam_info])
        orbit_btn.click(fn=open_orbit, outputs=[orbit_info])

    return app
```
