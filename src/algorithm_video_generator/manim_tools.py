from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from shutil import which
from algorithm_video_generator.models import RenderResult
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
        cwd=str(source.parent),
        check=False,
    )

    video_path = find_rendered_video(media_dir, output_name)
    return RenderResult(
        return_code=process.returncode,
        video_path=str(video_path) if video_path else None,
        stdout=process.stdout,
        stderr=process.stderr,
    )


def find_rendered_video(media_dir: str | Path, output_name: str) -> Path | None:
    root = Path(media_dir)
    if not root.exists():
        return None

    matches = sorted(root.rglob(f"{output_name}.mp4"), key=lambda item: item.stat().st_mtime, reverse=True)
    if matches:
        return matches[0]
    return None
