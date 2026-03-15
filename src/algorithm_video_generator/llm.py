from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from openai import OpenAI

from algorithm_video_generator.models import ApiConfig, GenerationRequest, GenerationResult
from algorithm_video_generator.prompts import SYSTEM_PROMPT, build_user_prompt
from algorithm_video_generator.utils import (
    coerce_message_text,
    extract_python_code,
    has_required_manim_markers,
    repair_manim_code,
)


StatusCallback = Callable[[str], None]
DeltaCallback = Callable[[str], None]
DebugCallback = Callable[[str], None]


class ChatCompletionsClient:
    def __init__(self, config: ApiConfig) -> None:
        self._config = config

    def generate_manim_script(self, request: GenerationRequest) -> GenerationResult:
        return self.generate_manim_script_stream(request)

    def generate_manim_script_stream(
        self,
        request: GenerationRequest,
        on_status: StatusCallback | None = None,
        on_delta: DeltaCallback | None = None,
        on_debug: DebugCallback | None = None,
    ) -> GenerationResult:
        raw_parts: list[str] = []

        if on_status:
            on_status("正在建立 OpenAI 兼容 SSE 连接...")

        with OpenAI(
            api_key=self._config.api_key.strip() or "EMPTY",
            base_url=self._config.normalized_base_url(),
            timeout=float(self._config.timeout_seconds),
            max_retries=1,
        ) as client:
            with client.chat.completions.with_streaming_response.create(
                model=self._config.model.strip(),
                temperature=self._config.temperature,
                stream=True,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(request)},
                ],
            ) as response:
                if on_status:
                    on_status("已连接，正在接收模型流式输出...")

                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        if on_debug:
                            on_debug(f"SSE 原始行: {line}")
                        continue

                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break

                    event = self._parse_sse_payload(payload, on_debug)
                    if not event:
                        continue

                    error = event.get("error")
                    if isinstance(error, dict):
                        message = error.get("message")
                        if isinstance(message, str) and message.strip():
                            raise ValueError(message.strip())
                        raise ValueError("接口返回了 SSE 错误事件。")

                    delta_text = self._extract_chunk_text(event)
                    if delta_text:
                        raw_parts.append(delta_text)
                        if on_delta:
                            on_delta(delta_text)

        if on_status:
            on_status("流式输出结束，正在整理脚本...")

        raw_content = "".join(raw_parts).strip()
        if not raw_content:
            raise ValueError("SSE 已结束，但没有收到有效文本内容。")

        manim_code = repair_manim_code(extract_python_code(raw_content))
        self._validate_generated_code(manim_code)
        return GenerationResult(raw_content=raw_content, manim_code=manim_code)

    @staticmethod
    def _parse_sse_payload(payload: str, on_debug: DebugCallback | None) -> dict[str, Any] | None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            if on_debug:
                on_debug(f"无法解析的 SSE 数据: {payload}")
            return None
        if isinstance(data, dict):
            return data
        if on_debug:
            on_debug(f"忽略非对象 SSE 数据: {payload}")
        return None

    @staticmethod
    def _extract_chunk_text(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list):
            return ""

        parts: list[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue

            delta = choice.get("delta")
            if isinstance(delta, dict):
                text = coerce_message_text(delta.get("content"))
                if text:
                    parts.append(text)
                    continue

            message = choice.get("message")
            if isinstance(message, dict):
                text = coerce_message_text(message.get("content"))
                if text:
                    parts.append(text)

        return "".join(parts)

    @staticmethod
    def _validate_generated_code(manim_code: str) -> None:
        if not has_required_manim_markers(manim_code):
            raise ValueError("模型返回内容里没有找到完整的 Manim 入口骨架。")
