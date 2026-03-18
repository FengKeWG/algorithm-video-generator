from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from algorithm_video_generator.models.domain import (
    ApiConfig,
    GenerationRequest,
    GenerationResult,
    Storyboard,
    StoryboardBeat,
    StoryboardPlanResult,
    StoryboardSegment,
)
from algorithm_video_generator.prompts import (
    SCRIPT_SYSTEM_PROMPT,
    STORYBOARD_REPAIR_SYSTEM_PROMPT,
    STORYBOARD_SYSTEM_PROMPT,
    build_script_user_prompt,
    build_storyboard_repair_user_prompt,
    build_storyboard_user_prompt,
)
from algorithm_video_generator.utils import (
    coerce_message_text,
    extract_json_object,
    extract_python_code,
    has_required_manim_markers,
    repair_manim_code,
    slugify_filename,
    split_narration_into_beats,
)

StatusCallback = Callable[[str], None]
DeltaCallback = Callable[[str], None]
DebugCallback = Callable[[str], None]


class ChatCompletionsClient:
    def __init__(self, config: ApiConfig) -> None:
        self._config = config

    def plan_storyboard(
            self,
            request: GenerationRequest,
            on_status: StatusCallback | None = None,
    ) -> StoryboardPlanResult:
        if on_status:
            on_status("正在规划视频分镜...")

        raw_content = self._create_completion_text(
            system_prompt=STORYBOARD_SYSTEM_PROMPT,
            user_prompt=build_storyboard_user_prompt(request),
        )
        try:
            storyboard = self._parse_storyboard(raw_content, request)
        except ValueError as exc:
            if on_status:
                on_status("分镜 JSON 非法，正在请求模型修复格式...")
            repaired_content = self._create_completion_text(
                system_prompt=STORYBOARD_REPAIR_SYSTEM_PROMPT,
                user_prompt=build_storyboard_repair_user_prompt(raw_content, str(exc)),
            )
            storyboard = self._parse_storyboard(repaired_content, request)
            raw_content = repaired_content
        if on_status:
            on_status("分镜规划完成。")
        return StoryboardPlanResult(raw_content=raw_content, storyboard=storyboard)

    def generate_manim_script(
            self,
            request: GenerationRequest,
            storyboard: Storyboard,
            on_status: StatusCallback | None = None,
            on_delta: DeltaCallback | None = None,
            on_debug: DebugCallback | None = None,
    ) -> GenerationResult:
        return self.generate_manim_script_stream(
            request,
            storyboard,
            on_status=on_status,
            on_delta=on_delta,
            on_debug=on_debug,
        )

    def generate_manim_script_stream(
            self,
            request: GenerationRequest,
            storyboard: Storyboard,
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
            messages = [
                ChatCompletionSystemMessageParam(
                    role="system",
                    content=SCRIPT_SYSTEM_PROMPT
                ),
                ChatCompletionUserMessageParam(
                    role="user",
                    content=build_script_user_prompt(request, storyboard)
                ),
            ]
            response = client.chat.completions.create(
                model=self._config.model.strip(),
                temperature=self._config.temperature,
                stream=True,
                messages=messages,
            )
            if on_status:
                on_status("已连接，正在接收模型流式输出...")
            for chunk in response:
                # 提取增量文本
                if not chunk.choices:
                    continue
                delta_content = chunk.choices[0].delta.content
                if delta_content:
                    raw_parts.append(delta_content)
                    if on_delta:
                        on_delta(delta_content)

        if on_status:
            on_status("流式输出结束，正在整理脚本...")

        raw_content = "".join(raw_parts).strip()
        if not raw_content:
            raise ValueError("SSE 已结束，但没有收到有效文本内容。")

        manim_code = repair_manim_code(extract_python_code(raw_content))
        self._validate_generated_code(manim_code)
        return GenerationResult(raw_content=raw_content, manim_code=manim_code)

    def _create_completion_text(self, system_prompt: str, user_prompt: str) -> str:
        with OpenAI(
                api_key=self._config.api_key.strip() or "EMPTY",
                base_url=self._config.normalized_base_url(),
                timeout=float(self._config.timeout_seconds),
                max_retries=1,
        ) as client:
            response = client.chat.completions.create(
                model=self._config.model.strip(),
                temperature=self._config.temperature,
                stream=False,
                messages=[
                    ChatCompletionSystemMessageParam(role="system", content=system_prompt),
                    ChatCompletionUserMessageParam(role="user", content=user_prompt),
                ],
            )
        content = response.choices[0].message.content if response.choices else ""
        text = coerce_message_text(content).strip()
        if not text:
            raise ValueError("模型没有返回有效文本内容。")
        return text

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

    @staticmethod
    def _parse_storyboard(raw_content: str, request: GenerationRequest) -> Storyboard:
        payload_text = extract_json_object(raw_content)
        try:
            data = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise ValueError("模型返回的分镜不是合法 JSON。") from exc

        if not isinstance(data, dict):
            raise ValueError("模型返回的分镜 JSON 顶层必须是对象。")

        segments_data = data.get("segments")
        if not isinstance(segments_data, list) or not segments_data:
            raise ValueError("模型返回的分镜缺少有效的 segments。")

        segments: list[StoryboardSegment] = []
        for index, item in enumerate(segments_data, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"分镜第 {index} 项不是对象。")
            segment_id = str(item.get("id", f"segment_{index}")).strip() or f"segment_{index}"
            segment_id = slugify_filename(segment_id, fallback=f"segment_{index}").replace(".", "_").replace("-", "_")
            narration = str(item.get("narration", "")).strip()
            animation_notes = str(item.get("animation_notes", "")).strip()
            visual_goal = str(item.get("visual_goal", "")).strip()
            beats = ChatCompletionsClient._parse_beats(item.get("beats"), segment_id, narration, animation_notes)
            if not narration:
                narration = " ".join(beat.narration for beat in beats).strip()
            segments.append(
                StoryboardSegment(
                    id=segment_id,
                    title=str(item.get("title", f"第{index}段")).strip() or f"第{index}段",
                    visual_goal=visual_goal,
                    narration=narration,
                    animation_notes=animation_notes,
                    beats=beats,
                    target_duration_seconds=None,
                )
            )

        if len(segments) < 5:
            raise ValueError("模型返回的分镜段数过少，无法生成完整讲解视频。")
        if any(not segment.narration for segment in segments):
            raise ValueError("模型返回的分镜中存在空 narration。")
        if any(not segment.beats for segment in segments):
            raise ValueError("模型返回的分镜中存在没有 beats 的 segment。")

        return Storyboard(
            title=str(data.get("title", request.title)).strip() or request.title,
            language=str(data.get("language", request.language)).strip() or request.language,
            segments=segments,
        )

    @staticmethod
    def _parse_beats(
            raw_beats: object,
            segment_id: str,
            fallback_narration: str,
            fallback_visual_notes: str,
    ) -> list[StoryboardBeat]:
        beats: list[StoryboardBeat] = []

        if isinstance(raw_beats, list):
            for index, item in enumerate(raw_beats, start=1):
                if not isinstance(item, dict):
                    continue
                beat_id = str(item.get("id", f"beat_{index}")).strip() or f"beat_{index}"
                beat_id = slugify_filename(beat_id, fallback=f"beat_{index}").replace(".", "_").replace("-", "_")
                narration = str(item.get("narration", "")).strip()
                if not narration:
                    continue
                beats.extend(
                    ChatCompletionsClient._normalize_beat_group(
                        beat_id=beat_id,
                        title=str(item.get("title", f"第{index}拍")).strip() or f"第{index}拍",
                        narration=narration,
                        visual_notes=str(item.get("visual_notes", "")).strip() or fallback_visual_notes,
                    )
                )

        if beats:
            return beats

        fallback_beats: list[StoryboardBeat] = []
        for index, sentence in enumerate(split_narration_into_beats(fallback_narration, max_chars=26), start=1):
            beat_id = slugify_filename(f"{segment_id}_{index}", fallback=f"beat_{index}").replace(".", "_").replace("-", "_")
            fallback_beats.extend(
                ChatCompletionsClient._normalize_beat_group(
                    beat_id=beat_id,
                    title=f"第{index}拍",
                    narration=sentence,
                    visual_notes=fallback_visual_notes,
                )
            )
        return fallback_beats

    @staticmethod
    def _normalize_beat_group(
            beat_id: str,
            title: str,
            narration: str,
            visual_notes: str,
    ) -> list[StoryboardBeat]:
        sentences = split_narration_into_beats(narration, max_chars=26)
        if not sentences:
            return []

        normalized_beats: list[StoryboardBeat] = []
        multi_part = len(sentences) > 1
        for index, sentence in enumerate(sentences, start=1):
            normalized_id = beat_id if not multi_part else f"{beat_id}_{index}"
            normalized_title = title if not multi_part else f"{title}-{index}"
            normalized_beats.append(
                StoryboardBeat(
                    id=slugify_filename(normalized_id, fallback=f"beat_{index}").replace(".", "_").replace("-", "_"),
                    title=normalized_title,
                    narration=sentence,
                    must_show=sentence,
                    visual_notes=visual_notes,
                    target_duration_seconds=None,
                )
            )
        return normalized_beats
