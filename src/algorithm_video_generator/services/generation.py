from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from algorithm_video_generator.llm import ChatCompletionsClient
from algorithm_video_generator.manim_tools import (
    is_manim_installed,
    mux_audio_video,
    render_script,
    save_script,
)
from algorithm_video_generator.models.domain import (
    ApiConfig,
    AppPreferences,
    AudioBeatResult,
    GenerationRequest,
    Storyboard,
    StoryboardBeat,
    StoryboardSegment,
    TtsConfig,
)
from algorithm_video_generator.tts.aliyun import AliyunTTSClient
from algorithm_video_generator.tts.audio import merge_wav_segments, read_wav_duration
from algorithm_video_generator.utils import (
    build_fallback_manim_code,
    inject_segment_timing,
    slugify_filename,
    validate_storyboard_script_structure,
)


@dataclass(slots=True)
class GenerationPipelineResult:
    storyboard: Storyboard
    storyboard_path: str
    raw_content: str
    manim_code: str
    script_path: str
    audio_dir: str
    merged_audio_path: str
    raw_video_path: str
    video_path: str | None
    rendered: bool
    manim_available: bool
    logs: list[str]


logger = logging.getLogger(__name__)


class AlgorithmVideoGeneratorService:
    def __init__(self, config: ApiConfig, preferences: AppPreferences, tts_config: TtsConfig) -> None:
        self._config = config
        self._preferences = preferences
        self._tts_config = tts_config

    def generate(self, request: GenerationRequest) -> GenerationPipelineResult:
        logs: list[str] = []
        streamed_chars = 0
        stream_log_checkpoint = 0

        def append_log(message: str) -> None:
            line = message.rstrip()
            if line:
                logs.append(line)
                logger.info(line)

        def track_stream_delta(text: str) -> None:
            nonlocal streamed_chars, stream_log_checkpoint
            streamed_chars += len(text)
            next_checkpoint = streamed_chars // 500
            if next_checkpoint > stream_log_checkpoint:
                stream_log_checkpoint = next_checkpoint
                logger.info("模型流式输出中，已接收约 %s 字符", streamed_chars)

        append_log("开始新的生成任务。")
        append_log(f"模型: {self._config.model}")
        append_log(f"Base URL: {self._config.normalized_base_url()}")
        append_log(f"题目: {request.title}")

        job_dir = self._create_job_dir(request.title)
        append_log(f"任务目录: {job_dir}")

        llm_client = ChatCompletionsClient(self._config)
        storyboard_result = llm_client.plan_storyboard(
            request,
            on_status=append_log,
        )
        storyboard = storyboard_result.storyboard
        storyboard_path = self._save_storyboard(job_dir, storyboard)
        append_log(f"分镜已保存: {storyboard_path}")

        audio_beats = self._synthesize_storyboard_audio(job_dir, storyboard, request.language, append_log)
        merged_audio_path = merge_wav_segments(audio_beats, job_dir / "audio" / "merged.wav")
        append_log(f"旁白音频已合并: {merged_audio_path}")
        storyboard = self._attach_audio_durations(storyboard, audio_beats)
        storyboard_path = self._save_storyboard(job_dir, storyboard)
        append_log(f"分镜 beat 时长已回填: {storyboard_path}")

        append_log("开始根据分镜和真实配音时长生成 Manim 脚本...")
        result = llm_client.generate_manim_script_stream(
            request,
            storyboard,
            on_status=append_log,
            on_delta=track_stream_delta,
            on_debug=append_log,
        )
        generated_code = result.manim_code
        valid, issues = validate_storyboard_script_structure(generated_code, storyboard)
        if not valid:
            append_log("模型脚本未满足 beat 级结构，切换到保底脚本。")
            for issue in issues:
                append_log(f"[结构问题] {issue}")
            generated_code = build_fallback_manim_code(storyboard)
        timed_manim_code = inject_segment_timing(generated_code, storyboard)

        script_path = save_script(self._script_path(job_dir, request.title), timed_manim_code)
        append_log(f"脚本已保存: {script_path}")

        manim_available = is_manim_installed()
        if not manim_available:
            logger.error("未检测到 manim，无法完成强制渲染。")
            raise RuntimeError("未检测到 manim，无法完成强制渲染。")

        append_log("正在调用 Manim 渲染...")
        render_result = render_script(script_path, job_dir)
        if render_result.stdout.strip():
            append_log("[manim stdout]")
            append_log(render_result.stdout)
        if render_result.stderr.strip():
            append_log("[manim stderr]")
            append_log(render_result.stderr)
        if render_result.return_code != 0:
            logger.error("manim 渲染失败，退出码: %s", render_result.return_code)
            raise RuntimeError(f"manim 渲染失败，退出码: {render_result.return_code}")

        raw_video_path = render_result.video_path
        if not raw_video_path:
            logger.error("manim 渲染完成，但没有找到输出视频。")
            raise RuntimeError("manim 渲染完成，但没有找到输出视频。")
        append_log(f"原始视频已输出: {raw_video_path}")

        final_video_path = mux_audio_video(
            raw_video_path,
            merged_audio_path,
            job_dir / "final" / f"{slugify_filename(request.title)}.mp4",
        )
        append_log(f"成品视频已输出: {final_video_path}")

        return GenerationPipelineResult(
            storyboard=storyboard,
            storyboard_path=str(storyboard_path),
            raw_content=result.raw_content,
            manim_code=timed_manim_code,
            script_path=str(script_path),
            audio_dir=str((job_dir / "audio").resolve()),
            merged_audio_path=str(merged_audio_path),
            raw_video_path=str(raw_video_path),
            video_path=str(final_video_path),
            rendered=True,
            manim_available=manim_available,
            logs=logs,
        )

    def _create_job_dir(self, title: str) -> Path:
        base_dir = Path(self._preferences.output_dir).expanduser().resolve()
        job_id = f"{datetime.now():%Y%m%d_%H%M%S}_{slugify_filename(title)}"
        target = base_dir / "jobs" / job_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _script_path(job_dir: Path, title: str) -> Path:
        target = job_dir / "script" / f"{slugify_filename(title)}.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _save_storyboard(job_dir: Path, storyboard: Storyboard) -> Path:
        target = job_dir / "storyboard" / "storyboard.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "title": storyboard.title,
            "language": storyboard.language,
            "segments": [
                {
                    "id": segment.id,
                    "title": segment.title,
                    "visual_goal": segment.visual_goal,
                    "narration": segment.narration,
                    "animation_notes": segment.animation_notes,
                    "target_duration_seconds": segment.target_duration_seconds,
                    "beats": [
                        {
                            "id": beat.id,
                            "title": beat.title,
                            "narration": beat.narration,
                            "must_show": beat.must_show,
                            "visual_notes": beat.visual_notes,
                            "target_duration_seconds": beat.target_duration_seconds,
                        }
                        for beat in segment.beats
                    ],
                }
                for segment in storyboard.segments
            ],
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    @staticmethod
    def _attach_audio_durations(
            storyboard: Storyboard,
            audio_beats: list[AudioBeatResult],
    ) -> Storyboard:
        duration_by_beat_key = {
            (beat.segment_id, beat.beat_id): beat.duration_seconds
            for beat in audio_beats
        }
        updated_segments: list[StoryboardSegment] = []
        for segment in storyboard.segments:
            updated_beats: list[StoryboardBeat] = []
            segment_total = 0.0
            for index, beat in enumerate(segment.beats):
                beat_duration = duration_by_beat_key.get((segment.id, beat.id))
                if beat_duration is not None:
                    segment_total += beat_duration
                    if index < len(segment.beats) - 1:
                        segment_total += 0.25
                updated_beats.append(
                    StoryboardBeat(
                        id=beat.id,
                        title=beat.title,
                        narration=beat.narration,
                        must_show=beat.must_show,
                        visual_notes=beat.visual_notes,
                        target_duration_seconds=beat_duration,
                    )
                )
            updated_segments.append(
                StoryboardSegment(
                    id=segment.id,
                    title=segment.title,
                    visual_goal=segment.visual_goal,
                    narration=segment.narration,
                    animation_notes=segment.animation_notes,
                    beats=updated_beats,
                    target_duration_seconds=round(segment_total, 3) if segment_total > 0 else None,
                )
            )

        return Storyboard(
            title=storyboard.title,
            language=storyboard.language,
            segments=updated_segments,
        )

    def _synthesize_storyboard_audio(
            self,
            job_dir: Path,
            storyboard: Storyboard,
            request_language: str,
            append_log: Callable[[str], None],
    ) -> list[AudioBeatResult]:
        append_log("开始合成旁白音频...")
        audio_dir = job_dir / "audio" / "beats"
        audio_dir.mkdir(parents=True, exist_ok=True)

        client = AliyunTTSClient(self._tts_config)
        language_type = self._infer_tts_language_type(request_language)
        results: list[AudioBeatResult] = []

        beat_index = 0
        for segment in storyboard.segments:
            for beat in segment.beats:
                beat_index += 1
                audio_path = audio_dir / f"{beat_index:03d}_{slugify_filename(segment.id)}_{slugify_filename(beat.id)}.wav"
                append_log(f"正在合成旁白: {segment.title} / {beat.title}")
                client.synthesize_to_file(beat.narration, audio_path, language_type)
                duration_seconds = read_wav_duration(audio_path)
                append_log(f"旁白已生成: {audio_path} ({duration_seconds:.2f}s)")
                results.append(
                    AudioBeatResult(
                        segment_id=segment.id,
                        beat_id=beat.id,
                        title=f"{segment.title} / {beat.title}",
                        text=beat.narration,
                        audio_path=str(audio_path),
                        duration_seconds=duration_seconds,
                    )
                )

        return results

    @staticmethod
    def _infer_tts_language_type(language: str) -> str:
        normalized = language.strip().lower()
        if normalized.startswith("en"):
            return "English"
        if "english" in normalized:
            return "English"
        return "Chinese"
