from __future__ import annotations

import json
from pathlib import Path

from algorithm_video_generator.models import ApiConfig, AppPreferences, GenerationRequest


STATE_PATH = Path.cwd() / "storage" / "app_state.json"


def load_state(path: str | Path | None = None) -> tuple[ApiConfig, GenerationRequest, AppPreferences]:
    state_path = _resolve_path(path)
    if not state_path.exists():
        return default_api_config(), default_request(), AppPreferences()

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_api_config(), default_request(), AppPreferences()

    api = payload.get("api", {}) if isinstance(payload, dict) else {}
    content = payload.get("content", {}) if isinstance(payload, dict) else {}
    app = payload.get("app", {}) if isinstance(payload, dict) else {}

    return (
        ApiConfig(
            base_url=str(api.get("base_url", "https://api.openai.com/v1")),
            api_key=str(api.get("api_key", "")),
            model=str(api.get("model", "gpt-4.1")),
            temperature=float(api.get("temperature", 0.2)),
            timeout_seconds=int(api.get("timeout_seconds", 180)),
        ),
        GenerationRequest(
            title=str(content.get("title", "")),
            language=str(content.get("language", "中文")),
            problem_statement=str(content.get("problem_statement", "")),
            official_solution=str(content.get("official_solution", "")),
            reference_code=str(content.get("reference_code", "")),
            additional_requirements=str(content.get("additional_requirements", "")),
        ),
        AppPreferences(
            output_dir=str(app.get("output_dir", "outputs")),
            auto_render=bool(app.get("auto_render", False)),
        ),
    )


def save_state(
    config: ApiConfig,
    request: GenerationRequest,
    preferences: AppPreferences,
    path: str | Path | None = None,
) -> Path:
    state_path = _resolve_path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "api": {
            "base_url": config.base_url,
            "api_key": config.api_key,
            "model": config.model,
            "temperature": config.temperature,
            "timeout_seconds": config.timeout_seconds,
        },
        "content": {
            "title": request.title,
            "language": request.language,
            "problem_statement": request.problem_statement,
            "official_solution": request.official_solution,
            "reference_code": request.reference_code,
            "additional_requirements": request.additional_requirements,
        },
        "app": {
            "output_dir": preferences.output_dir,
            "auto_render": preferences.auto_render,
        },
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return state_path


def default_api_config() -> ApiConfig:
    return ApiConfig(
        base_url="https://api.openai.com/v1",
        api_key="",
        model="gpt-4.1",
        temperature=0.2,
        timeout_seconds=180,
    )


def default_request() -> GenerationRequest:
    return GenerationRequest(
        title="",
        language="中文",
        problem_statement="",
        official_solution="",
        reference_code="",
        additional_requirements="",
    )


def _resolve_path(path: str | Path | None) -> Path:
    return Path(path).expanduser().resolve() if path else STATE_PATH.resolve()

