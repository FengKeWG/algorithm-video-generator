from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from shutil import which
from algorithm_video_generator.models.domain import RenderResult
from algorithm_video_generator.utils import slugify_filename


def is_manim_installed() -> bool:
    return resolve_manim_invocation() is not None


def resolve_manim_invocation() -> list[str] | None:
    if importlib.util.find_spec("manim") is not None:
        return [sys.executable, "-m", "manim"]

    command_path = which("manim")
    if command_path:
        return [command_path]

    return None


def resolve_ffmpeg_invocation() -> list[str] | None:
    command_path = which("ffmpeg")
    if command_path:
        return [command_path]
    return None


def resolve_ffprobe_invocation() -> list[str] | None:
    command_path = which("ffprobe")
    if command_path:
        return [command_path]
    return None


def default_script_path(output_dir: str | Path, title: str) -> Path:
    base_dir = Path(output_dir).expanduser().resolve() / "scripts"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f"{slugify_filename(title)}.py"


def save_script(script_path: str | Path, content: str) -> Path:
    target = Path(script_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def render_script(script_path: str | Path, output_dir: str | Path) -> RenderResult:
    source = Path(script_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"脚本不存在: {source}")

    manim_invocation = resolve_manim_invocation()
    if manim_invocation is None:
        raise RuntimeError("未检测到 manim。请安装到当前 Python 环境，或确保 manim 命令在 PATH 中。")

    out_dir = Path(output_dir).expanduser().resolve()
    media_dir = out_dir / "media"
    output_name = slugify_filename(source.stem)

    command = [
        *manim_invocation,
        "render",
        "-qm",
        str(source),
        "AlgorithmVideo",
        "--media_dir",
        str(media_dir),
        "--output_file",
        output_name,
    ]

    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(source.parent),
        check=False,
    )

    video_path = find_rendered_video(media_dir, output_name)
    return RenderResult(
        return_code=process.returncode,
        video_path=str(video_path) if video_path else None,
        stdout=process.stdout or "",
        stderr=process.stderr or "",
    )


def find_rendered_video(media_dir: str | Path, output_name: str) -> Path | None:
    root = Path(media_dir)
    if not root.exists():
        return None

    matches = sorted(root.rglob(f"{output_name}.mp4"), key=lambda item: item.stat().st_mtime, reverse=True)
    if matches:
        return matches[0]
    return None


def read_media_duration_seconds(path: str | Path) -> float:
    target = Path(path).expanduser().resolve()
    ffprobe_invocation = resolve_ffprobe_invocation()
    if ffprobe_invocation is None:
        raise RuntimeError("未检测到 ffprobe，无法读取媒体时长。请安装 FFmpeg，并确保 ffmpeg/ffprobe 都在 PATH 中。")

    command = [
        *ffprobe_invocation,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(target),
    ]
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(f"ffprobe 执行失败: {process.stderr or process.stdout}")

    try:
        payload = json.loads(process.stdout)
        duration = float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法解析 ffprobe 输出: {process.stdout}") from exc
    return duration


def mux_audio_video(
        video_path: str | Path,
        audio_path: str | Path,
        output_path: str | Path,
) -> Path:
    video = Path(video_path).expanduser().resolve()
    audio = Path(audio_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg_invocation = resolve_ffmpeg_invocation()
    if ffmpeg_invocation is None:
        raise RuntimeError("未检测到 ffmpeg，无法合成最终视频。请安装 FFmpeg，并确保 ffmpeg/ffprobe 都在 PATH 中。")

    video_duration = read_media_duration_seconds(video)
    audio_duration = read_media_duration_seconds(audio)
    pad_seconds = max(0.0, audio_duration - video_duration)

    if pad_seconds > 0.05:
        command = [
            *ffmpeg_invocation,
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-filter:v",
            f"tpad=stop_mode=clone:stop_duration={pad_seconds:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]
    else:
        command = [
            *ffmpeg_invocation,
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]

    command.append(str(target))

    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg 合成失败: {process.stderr or process.stdout}")
    return target
