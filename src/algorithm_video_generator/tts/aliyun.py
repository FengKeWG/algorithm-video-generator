from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx

from algorithm_video_generator.models.domain import TtsConfig

BASE_HTTP_API_URL = "https://dashscope.aliyuncs.com/api/v1"
GENERATION_ENDPOINT = f"{BASE_HTTP_API_URL}/services/aigc/multimodal-generation/generation"
DEFAULT_INSTRUCTIONS = "语速中等，吐字清晰，像算法老师讲题，重点处稍作强调。"
DEFAULT_TIMEOUT_SECONDS = 180.0


class AliyunTTSClient:
    def __init__(self, config: TtsConfig) -> None:
        self._config = config

    def synthesize_to_file(self, text: str, target_path: str | Path, language_type: str) -> Path:
        if not self._config.api_key.strip():
            raise ValueError("未配置 DASHSCOPE_API_KEY。")
        if not text.strip():
            raise ValueError("TTS 文本不能为空。")

        payload = {
            "model": self._config.model,
            "input": {
                "text": text,
                "voice": self._config.voice,
                "language_type": language_type,
            },
        }

        if self._config.model.startswith("qwen3-tts-instruct"):
            payload["instructions"] = DEFAULT_INSTRUCTIONS
            payload["optimize_instructions"] = True

        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True, trust_env=False) as client:
            response = client.post(GENERATION_ENDPOINT, headers=headers, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(f"TTS 请求失败: {response.status_code} {response.text}")
            data = response.json()

            audio_url = (
                data.get("output", {})
                .get("audio", {})
                .get("url")
            )
            if not isinstance(audio_url, str) or not audio_url.strip():
                raise RuntimeError(f"TTS 响应里没有音频 URL: {data}")

            normalized_audio_url = _normalize_audio_url(audio_url)
            audio_response = client.get(normalized_audio_url)
            if audio_response.status_code >= 400:
                raise RuntimeError(f"TTS 音频下载失败: {audio_response.status_code} {audio_response.text}")
            content_type = audio_response.headers.get("content-type", "").lower()
            audio_bytes = audio_response.content
            if "audio" not in content_type and not _looks_like_wav(audio_bytes):
                snippet = audio_bytes[:200].decode("utf-8", errors="replace")
                raise RuntimeError(
                    "TTS 音频下载结果不是有效 wav 数据，"
                    f"url={normalized_audio_url} content_type={content_type!r} preview={snippet!r}"
                )

        target = Path(target_path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(audio_bytes)
        return target


def _normalize_audio_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "http" and parsed.netloc.endswith(".aliyuncs.com"):
        return urlunparse(parsed._replace(scheme="https"))
    return url


def _looks_like_wav(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
