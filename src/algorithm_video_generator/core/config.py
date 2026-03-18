from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from algorithm_video_generator.models.domain import ApiConfig, AppPreferences, TtsConfig

DEFAULT_ENV_PATH = Path.cwd() / ".env"


def _load_environment() -> None:
    load_dotenv(dotenv_path=DEFAULT_ENV_PATH, override=False)


def _read_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value is not None else default


def _read_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须是整数。") from exc


def _read_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value.strip())
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须是数字。") from exc


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"环境变量 {name} 必须是布尔值（true/false）。")


@dataclass(slots=True)
class AppSettings:
    host: str
    port: int
    reload: bool
    openai_base_url: str
    openai_api_key: str
    openai_model: str
    openai_temperature: float
    openai_timeout_seconds: int
    output_dir: str
    dashscope_api_key: str
    tts_model: str
    tts_voice: str


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    _load_environment()
    return AppSettings(
        host=_read_str("APP_HOST", "127.0.0.1"),
        port=_read_int("APP_PORT", 8000),
        reload=_read_bool("APP_RELOAD", False),
        openai_base_url=_read_str("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_api_key=_read_str("OPENAI_API_KEY", ""),
        openai_model=_read_str("OPENAI_MODEL", "gpt-4.1"),
        openai_temperature=_read_float("OPENAI_TEMPERATURE", 0.2),
        openai_timeout_seconds=_read_int("OPENAI_TIMEOUT_SECONDS", 180),
        output_dir=_read_str("APP_OUTPUT_DIR", "outputs"),
        dashscope_api_key=_read_str("DASHSCOPE_API_KEY", ""),
        tts_model=_read_str("TTS_MODEL", "qwen3-tts-instruct-flash"),
        tts_voice=_read_str("TTS_VOICE", "Serena"),
    )


def build_api_config(settings: AppSettings | None = None) -> ApiConfig:
    runtime_settings = settings or get_settings()
    return ApiConfig(
        base_url=runtime_settings.openai_base_url,
        api_key=runtime_settings.openai_api_key,
        model=runtime_settings.openai_model,
        temperature=runtime_settings.openai_temperature,
        timeout_seconds=runtime_settings.openai_timeout_seconds,
    )


def build_preferences(settings: AppSettings | None = None) -> AppPreferences:
    runtime_settings = settings or get_settings()
    return AppPreferences(
        output_dir=runtime_settings.output_dir,
    )


def build_tts_config(settings: AppSettings | None = None) -> TtsConfig:
    runtime_settings = settings or get_settings()
    return TtsConfig(
        api_key=runtime_settings.dashscope_api_key,
        model=runtime_settings.tts_model,
        voice=runtime_settings.tts_voice,
    )
