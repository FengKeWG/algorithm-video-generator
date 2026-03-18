# Algorithm Video Generator

把 ACM 题目材料生成为讲解视频。

一次完整生成流程是：

1. 用 OpenAI 兼容接口规划分镜。
2. 把分镜拆成 beat 级短句。
3. 用阿里云千问 TTS 逐句合成配音。
4. 生成 `Manim` 脚本并渲染视频。
5. 用 `ffmpeg` 把音频和视频合成最终成品。

## 使用步骤

1. 安装 Python 3.12。
2. 安装 `ffmpeg`，并确认 `ffmpeg`、`ffprobe` 在 `PATH` 里。
3. 创建虚拟环境并安装项目依赖。
4. 新建 `.env`，填好 LLM 和阿里云 TTS 的 Key。
5. 启动服务。
6. 调 `POST /generate`，等待输出视频。

下面是完整步骤。

## 1. 环境要求

必须具备：

- Python `3.12+`
- `ffmpeg`
- `ffprobe`

说明：

- `manim` 已经在 Python 依赖里，会跟随 `pip install -e .` 一起安装。
- 如果你的系统安装 `manim` 失败，那不是本项目逻辑问题，而是你的机器缺少 Manim 运行所需的底层环境。先把 Manim Community 本身装通，再回来装本项目。

## 2. 安装项目

在项目根目录执行：

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Windows PowerShell 可以这样激活虚拟环境：

```powershell
.venv\Scripts\Activate.ps1
```

## 3. 检查外部命令

先确认这些命令可用：

```bash
python --version
ffmpeg -version
ffprobe -version
```

## 4. 配置 `.env`

先复制模板：

```bash
cp .env.example .env
```

最少要填这 6 个变量：

```env
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your_openai_or_compatible_key
OPENAI_MODEL=gpt-5

DASHSCOPE_API_KEY=your_dashscope_key
TTS_MODEL=qwen3-tts-instruct-flash
TTS_VOICE=Serena
```

如果你还想改服务监听地址或输出目录，可以额外配置：

```env
APP_HOST=127.0.0.1
APP_PORT=8000
APP_RELOAD=false
OPENAI_TEMPERATURE=0.2
OPENAI_TIMEOUT_SECONDS=180
APP_OUTPUT_DIR=outputs
```

## 5. 启动服务

推荐直接用包入口：

```bash
python -m algorithm_video_generator
```

也可以：

```bash
algorithm-video-generator
```

启动后访问：

```text
http://127.0.0.1:8000/docs
```

如果你改了 `APP_HOST` 或 `APP_PORT`，这里对应修改。

## 6. 发起一次生成

最简单的方式是直接打开 Swagger：

```text
http://127.0.0.1:8000/docs
```

然后调用 `POST /generate`。

请求体示例：

```json
{
  "title": "CF 123A - Prime Permutation",
  "language": "中文",
  "problem_statement": "题目描述",
  "official_solution": "标准题解",
  "reference_code": "int main() { return 0; }",
  "additional_requirements": "突出样例推演"
}
```

也可以直接用 `curl`：

```bash
curl -X POST "http://127.0.0.1:8000/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CF 123A - Prime Permutation",
    "language": "中文",
    "problem_statement": "题目描述",
    "official_solution": "标准题解",
    "reference_code": "int main() { return 0; }",
    "additional_requirements": "突出样例推演"
  }'
```

## 7. 生成结果

每次任务都会输出到：

```text
outputs/jobs/<job_id>/
```

目录：

- `storyboard/`：结构化分镜 JSON
- `script/`：生成后的 Manim 脚本
- `audio/`：逐 beat 音频和合并音频
- `media/`：Manim 原始渲染结果
- `final/`：最终成品视频

最终视频在：

```text
outputs/jobs/<job_id>/final/
```

## 8. 常见报错

### `未检测到 ffmpeg`

你没装 FFmpeg，或者没把 `ffmpeg`、`ffprobe` 放进 `PATH`。

### `未检测到 manim`

当前 Python 环境里没有装好 `manim`。重新确认你是在项目虚拟环境里执行，并且 `pip install -e .` 成功。

### TTS 400 / TTS 请求失败

优先检查这几件事：

- `DASHSCOPE_API_KEY` 是否正确
- `TTS_MODEL` 和 `TTS_VOICE` 是否是阿里云支持的组合
- 你的 Key 是否对应正确地域

### `POST /generate` 很慢

这是正常现象。一次生成要经过：

1. 分镜规划
2. 多次 TTS
3. Manim 渲染
4. FFmpeg 合成

真正最耗时的通常是 TTS 和 Manim 渲染。

## 9. 接口概览

可用接口：

- `GET /health`
- `GET /config`
- `POST /generate`

`/config` 只会告诉你 API Key 是否配置，不会把 Key 原文返回出来。

## 10. 项目结构

```text
src/algorithm_video_generator/
  api/         # FastAPI 入口、路由、schemas
  core/        # .env 配置
  models/      # 领域模型
  services/    # 生成主流程
  tts/         # 阿里云 TTS 与音频处理
  llm.py
  manim_tools.py
  prompts.py
  utils.py
```
