from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from algorithm_video_generator.models.domain import GenerationRequest


class StoryboardBeatPayload(BaseModel):
    id: str
    title: str
    narration: str
    must_show: str
    visual_notes: str
    target_duration_seconds: float | None = None


class StoryboardSegmentPayload(BaseModel):
    id: str
    title: str
    visual_goal: str
    narration: str
    animation_notes: str
    beats: list[StoryboardBeatPayload]
    target_duration_seconds: float | None = None


class StoryboardPayload(BaseModel):
    title: str
    language: str
    segments: list[StoryboardSegmentPayload]


class GenerateRequestPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1)
    language: str = Field(default="中文", min_length=1)
    problem_statement: str = Field(min_length=1)
    official_solution: str = Field(min_length=1)
    reference_code: str = Field(min_length=1)
    additional_requirements: str = ""

    def to_generation_request(self) -> GenerationRequest:
        return GenerationRequest(
            title=self.title,
            language=self.language,
            problem_statement=self.problem_statement,
            official_solution=self.official_solution,
            reference_code=self.reference_code,
            additional_requirements=self.additional_requirements,
        )


class GenerateResponsePayload(BaseModel):
    storyboard: StoryboardPayload
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
    output_dir: str
    model: str
    base_url: str
    tts_model: str
    tts_voice: str


class HealthResponsePayload(BaseModel):
    status: Literal["ok"]
    version: str
    manim_installed: bool


class RuntimeConfigPayload(BaseModel):
    host: str
    port: int
    reload: bool
    openai_base_url: str
    openai_model: str
    openai_temperature: float
    openai_timeout_seconds: int
    openai_api_key_configured: bool
    dashscope_api_key_configured: bool
    tts_model: str
    tts_voice: str
    output_dir: str
