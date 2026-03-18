from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from algorithm_video_generator import __version__
from algorithm_video_generator.api.schemas import (
    GenerateRequestPayload,
    GenerateResponsePayload,
    HealthResponsePayload,
    RuntimeConfigPayload,
    StoryboardBeatPayload,
    StoryboardPayload,
    StoryboardSegmentPayload,
)
from algorithm_video_generator.core.config import build_api_config, build_preferences, build_tts_config, get_settings
from algorithm_video_generator.manim_tools import is_manim_installed
from algorithm_video_generator.services.generation import AlgorithmVideoGeneratorService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", tags=["meta"])
def read_root() -> dict[str, str]:
    return {
        "name": "Algorithm Video Generator API",
        "docs": "/docs",
        "health": "/health",
        "generate": "/generate",
    }


@router.get("/health", response_model=HealthResponsePayload, tags=["meta"])
def read_health() -> HealthResponsePayload:
    return HealthResponsePayload(
        status="ok",
        version=__version__,
        manim_installed=is_manim_installed(),
    )


@router.get("/config", response_model=RuntimeConfigPayload, tags=["meta"])
def read_config() -> RuntimeConfigPayload:
    settings = get_settings()
    return RuntimeConfigPayload(
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        openai_base_url=settings.openai_base_url,
        openai_model=settings.openai_model,
        openai_temperature=settings.openai_temperature,
        openai_timeout_seconds=settings.openai_timeout_seconds,
        openai_api_key_configured=bool(settings.openai_api_key),
        dashscope_api_key_configured=bool(settings.dashscope_api_key),
        tts_model=settings.tts_model,
        tts_voice=settings.tts_voice,
        output_dir=settings.output_dir,
    )


@router.post("/generate", response_model=GenerateResponsePayload, tags=["generation"])
def generate(payload: GenerateRequestPayload) -> GenerateResponsePayload:
    settings = get_settings()
    api_config = build_api_config(settings)
    service = AlgorithmVideoGeneratorService(
        config=api_config,
        preferences=build_preferences(settings),
        tts_config=build_tts_config(settings),
    )

    logger.info("收到生成请求: title=%s language=%s", payload.title, payload.language)

    try:
        result = service.generate(payload.to_generation_request())
    except ValueError as exc:
        logger.exception("生成请求参数错误: title=%s", payload.title)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        logger.exception("生成流程文件缺失: title=%s", payload.title)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("生成流程失败: title=%s", payload.title)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("生成完成: title=%s video_path=%s", payload.title, result.video_path)

    return GenerateResponsePayload(
        storyboard=StoryboardPayload(
            title=result.storyboard.title,
            language=result.storyboard.language,
            segments=[
                StoryboardSegmentPayload(
                    id=segment.id,
                    title=segment.title,
                    visual_goal=segment.visual_goal,
                    narration=segment.narration,
                    animation_notes=segment.animation_notes,
                    beats=[
                        StoryboardBeatPayload(
                            id=beat.id,
                            title=beat.title,
                            narration=beat.narration,
                            must_show=beat.must_show,
                            visual_notes=beat.visual_notes,
                            target_duration_seconds=beat.target_duration_seconds,
                        )
                        for beat in segment.beats
                    ],
                    target_duration_seconds=segment.target_duration_seconds,
                )
                for segment in result.storyboard.segments
            ],
        ),
        storyboard_path=result.storyboard_path,
        raw_content=result.raw_content,
        manim_code=result.manim_code,
        script_path=result.script_path,
        audio_dir=result.audio_dir,
        merged_audio_path=result.merged_audio_path,
        raw_video_path=result.raw_video_path,
        video_path=result.video_path,
        rendered=result.rendered,
        manim_available=result.manim_available,
        output_dir=settings.output_dir,
        model=settings.openai_model,
        base_url=api_config.normalized_base_url(),
        tts_model=settings.tts_model,
        tts_voice=settings.tts_voice,
    )
