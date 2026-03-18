from __future__ import annotations

import shutil
import wave
from pathlib import Path

from algorithm_video_generator.models.domain import AudioBeatResult

DEFAULT_SILENCE_MS = 250


def read_wav_duration(audio_path: str | Path) -> float:
    path = Path(audio_path).expanduser().resolve()
    with wave.open(str(path), "rb") as handle:
        frame_rate = handle.getframerate()
        frame_count = handle.getnframes()
    if frame_rate <= 0:
        raise ValueError(f"无效的音频采样率: {path}")
    return frame_count / frame_rate


def merge_wav_segments(
        segments: list[AudioBeatResult],
        target_path: str | Path,
        silence_ms: int = DEFAULT_SILENCE_MS,
) -> Path:
    if not segments:
        raise ValueError("没有可合并的音频分段。")

    target = Path(target_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if len(segments) == 1:
        shutil.copyfile(segments[0].audio_path, target)
        return target

    with wave.open(segments[0].audio_path, "rb") as first:
        params = first.getparams()
        frame_rate = first.getframerate()
        sample_width = first.getsampwidth()
        channels = first.getnchannels()
        sample_params = (channels, sample_width, frame_rate)

    silence_frame_count = int(frame_rate * silence_ms / 1000)
    silence_bytes = b"\x00" * silence_frame_count * channels * sample_width

    with wave.open(str(target), "wb") as output:
        output.setparams(params)

        for index, segment in enumerate(segments):
            with wave.open(segment.audio_path, "rb") as current:
                current_params = (
                    current.getnchannels(),
                    current.getsampwidth(),
                    current.getframerate(),
                )
                if current_params != sample_params:
                    raise ValueError("所有音频分段必须具有相同的声道数、位深和采样率。")
                output.writeframes(current.readframes(current.getnframes()))
            if index < len(segments) - 1 and silence_bytes:
                output.writeframes(silence_bytes)

    return target
