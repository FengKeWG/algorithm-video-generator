from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ApiConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    timeout_seconds: int = 120

    def normalized_base_url(self) -> str:
        normalized = self.base_url.rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized[: -len("/chat/completions")]
        return normalized


@dataclass(slots=True)
class GenerationRequest:
    title: str
    language: str
    problem_statement: str
    official_solution: str
    reference_code: str
    additional_requirements: str = ""


@dataclass(slots=True)
class GenerationResult:
    raw_content: str
    manim_code: str


@dataclass(slots=True)
class AppPreferences:
    output_dir: str = "outputs"
    auto_render: bool = False


@dataclass(slots=True)
class RenderResult:
    return_code: int
    video_path: str | None
    stdout: str
    stderr: str
