# Algorithm Video Generator

一个最小可运行的 Python GUI 工具：

- 输入 ACM 题目、标准题解、`std` 代码
- 通过 OpenAI Chat Completions 兼容接口生成 `Manim` 脚本
- 使用 SSE 流式显示生成过程
- 自动保存脚本
- 可选自动调用 `manim` 渲染视频

当前版本先不做配音，只完成“AI 生成 Manim 脚本 + 本地渲染”。

## 技术选型

- Python 3.12+
- GUI: `Flet`
- LLM 请求: 官方 `openai` Python SDK
- 动画渲染: `manim`（可选依赖）

## 安装

推荐先建虚拟环境再安装：

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

如果需要本地渲染视频，再安装 `manim` 依赖：

```bash
python -m pip install -e ".[render]"
```

说明：

- `manim` 在不同平台可能还需要系统级依赖。
- `Flet` 官方文档要求桌面端使用 Python 3.10+，并支持 Windows 10/11。
- 如果开启“自动渲染视频”，还需要本地可用的 `manim`。

## 安装 LaTeX 环境

如果脚本里会用到 `Tex`、`MathTex`、`BulletedList`、`Title` 等基于 LaTeX 的 Manim 组件，还需要额外安装 LaTeX 工具链。

Manim 官方文档将 LaTeX 视为可选依赖；在 Windows 上，官方推荐使用 [MiKTeX](https://miktex.org/download)。

### Windows（推荐）

1. 下载并安装 [MiKTeX](https://miktex.org/download)。
2. 安装完成后打开 `MiKTeX Console`，先执行一次更新。
3. 在 `Settings` 中把缺失宏包安装策略设置为 `Ask me first` 或 `Always`。
4. 重新打开一个 PowerShell 窗口，确认命令已经进入 `PATH`：

```powershell
where latex
where xelatex
where dvisvgm
```

至少应当能找到：

- `latex`：默认 `Tex` / `MathTex` / `BulletedList` 会用到。
- `dvisvgm`：Manim 需要它把 LaTeX 输出转换成 SVG。
- `xelatex`：如果你要在 LaTeX 里直接排中文，通常还需要它。

### macOS / Linux

- macOS：可按 Manim 官方建议安装 [MacTeX](https://www.tug.org/mactex/)。
- Linux：通常安装 TeX Live；Manim 官方示例给出的完整安装方式是 Debian/Ubuntu 使用 `texlive-full`，Fedora 使用 `texlive-scheme-full`。

### 验证是否可用

安装完成后，建议先用命令行验证：

```powershell
where latex
where xelatex
where dvisvgm
```

如果这些命令都能返回路径，再运行一个最小示例：

```python
from manim import *

class AlgorithmVideo(Scene):
    def construct(self):
        self.add(MathTex(r"x^2 + y^2 = z^2"))
```

然后执行：

```powershell
manim render .\demo.py AlgorithmVideo
```

### 中文 LaTeX 说明

如果只是显示中文说明文字，优先使用 `Text` 或 `Paragraph`，这比 LaTeX 更稳。

如果确实要在 `Tex`、`BulletedList` 中直接渲染中文，通常需要在脚本里改用 `xelatex` 模板，并启用 `xeCJK`。否则即使已经装了普通 LaTeX，也可能在中文文本上失败。

```python
from manim import *
from manim.utils.tex import TexTemplate

zh_tex = TexTemplate(tex_compiler="xelatex", output_format=".xdv")
zh_tex.add_to_preamble(r"\usepackage{xeCJK}")
zh_tex.add_to_preamble(r"\setCJKmainfont{Microsoft YaHei}")
```

更多背景可参考：

- [Manim 安装文档](https://docs.manim.community/en/stable/installation/uv.html)
- [MiKTeX Windows 安装说明](https://miktex.org/howto/install-miktex)

## 启动

```bash
algorithm-video-generator
```

或者：

```bash
python -m algorithm_video_generator
```

或者：

```bash
flet run main.py
```

## 使用流程

1. 在“题目与题解”里粘贴题目、标准题解、标准代码
2. 在“隐藏设置”里填好 API Base URL、API Key、模型名
3. 点击唯一主按钮“开始生成”
4. 右侧实时查看流式日志和生成中的脚本
5. 生成完成后脚本会自动保存到 `outputs/scripts/`

默认输出目录为项目下的 `outputs/`，设置会保存到 `storage/app_state.json`。

## OpenAI 兼容接口要求

默认基础地址示例：

```text
https://api.openai.com/v1
```

接口要求：

- 兼容 `POST /chat/completions`
- 支持 `stream: true`
- 使用标准 SSE 流返回 `data: ...`

当前实现基于官方 `openai` Python SDK 的 `base_url` 自定义能力和 SSE 流式能力。

## 当前范围

这个基础版本只做以下事情：

- 把题目材料整理成适合视频化展示的 Manim 脚本
- 支持单按钮 GUI、进度条、流式日志
- 自动保存脚本
- 可选本地调用 `manim` 渲染

暂时不做：

- TTS 配音
- 自动分镜优化
- 多场景模板管理
- 任务队列与批处理

## 测试

```bash
.venv/bin/python -m unittest discover -s tests
```

## Windows 启动

在项目根目录打开 PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m algorithm_video_generator
```

也可以用 Flet 官方推荐方式：

```powershell
flet run main.py
```


