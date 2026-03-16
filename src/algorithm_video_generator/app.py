from __future__ import annotations

import time
import traceback
import flet as ft
from algorithm_video_generator.llm import ChatCompletionsClient
from algorithm_video_generator.manim_tools import (
    default_script_path,
    is_manim_installed,
    render_script,
    save_script,
)
from algorithm_video_generator.models import ApiConfig, AppPreferences, GenerationRequest
from algorithm_video_generator.settings_store import load_state, save_state


class AlgorithmVideoGeneratorApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.busy = False
        self.last_script_path: str | None = None
        self.last_video_path: str | None = None
        self._stream_buffer = ""
        self._last_stream_flush = 0.0

        self.api_config, self.request, self.preferences = load_state()

        self._configure_page()
        self._build_controls()
        self._apply_loaded_state()
        self._append_log("应用已准备就绪。")
        self.page.run_task(self._position_window)

    def _configure_page(self) -> None:
        self.page.title = "Algorithm Video Generator"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.bgcolor = "#F3F6FB"
        self.page.padding = 24
        self.page.scroll = ft.ScrollMode.HIDDEN
        self.page.theme = ft.Theme(
            color_scheme_seed="#0F766E",
            use_material3=True,
        )
        self.page.window.width = 1500
        self.page.window.height = 980
        self.page.window.min_width = 1180
        self.page.window.min_height = 820

    async def _position_window(self) -> None:
        await self.page.window.wait_until_ready_to_show()
        await self.page.window.center()

    def _build_controls(self) -> None:
        self.status_label = ft.Text(
            "等待开始",
            size=13,
            color="#4B5563",
        )
        self.progress_bar = ft.ProgressBar(
            value=0.0,
            bar_height=10,
            border_radius=999,
            color="#0F766E",
            bgcolor="#DDE6F2",
            year_2023=False,
        )
        self.busy_ring = ft.ProgressRing(
            visible=False,
            width=18,
            height=18,
            color="#0F766E",
            stroke_width=3,
            year_2023=False,
        )
        self.run_button = ft.FilledButton(
            content=ft.Row(
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.AUTO_AWESOME),
                    ft.Text("开始生成", size=16, weight=ft.FontWeight.W_700),
                ],
            ),
            height=56,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=18),
                padding=ft.Padding.symmetric(horizontal=20, vertical=18),
            ),
            on_click=self.start_generation,
        )

        self.title_input = ft.TextField(
            label="题目标题",
            hint_text="例如：CF 123A - Prime Permutation",
            border_radius=18,
            expand=True,
        )
        self.language_input = ft.Dropdown(
            label="视频语言",
            width=170,
            border_radius=18,
            options=[
                ft.dropdown.Option("中文"),
                ft.dropdown.Option("English"),
            ],
        )
        self.problem_input = self._multiline_input("题目描述", 22)
        self.solution_input = self._multiline_input("标准题解", 22)
        self.code_input = self._multiline_input("标准代码（std）", 24, code=True)
        self.extra_input = self._multiline_input("额外要求（可选）", 16)

        self.base_url_input = ft.TextField(
            border_radius=18,
            hint_text="https://api.openai.com/v1",
            expand=True,
        )
        self.api_key_input = ft.TextField(
            border_radius=18,
            password=True,
            can_reveal_password=True,
            hint_text="输入 API Key",
            expand=True,
        )
        self.model_input = ft.TextField(
            border_radius=18,
            hint_text="例如 qwen-plus",
            expand=True,
        )
        self.temperature_input = ft.Slider(
            min=0.0,
            max=1.0,
            divisions=10,
            label="{value}",
            expand=True,
        )
        self.temperature_value = ft.Text(size=12, color="#4B5563")
        self.temperature_input.on_change = self.on_temperature_change
        self.timeout_input = ft.TextField(
            width=140,
            border_radius=18,
            hint_text="180",
            value="180",
            text_align=ft.TextAlign.CENTER,
        )
        self.output_dir_input = ft.TextField(
            border_radius=18,
            hint_text="默认 outputs",
            expand=True,
        )
        self.auto_render_input = ft.Switch(
            value=False,
        )

        self.script_output = ft.TextField(
            label="Manim 脚本预览",
            multiline=True,
            read_only=True,
            expand=True,
            border_radius=20,
            text_style=ft.TextStyle(font_family="Consolas", size=13),
        )
        self.log_output = ft.TextField(
            label="运行日志",
            multiline=True,
            read_only=True,
            expand=True,
            border_radius=20,
            text_style=ft.TextStyle(font_family="Consolas", size=12),
        )
        self.result_path_text = ft.Text(
            "脚本会自动保存到 outputs/scripts。",
            size=12,
            color="#4B5563",
        )

        hero = ft.Container(
            border_radius=28,
            padding=28,
            bgcolor="#0F172A",
            content=ft.Column(
                spacing=18,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Column(
                                spacing=6,
                                controls=[
                                    ft.Text(
                                        "Algorithm Video Generator",
                                        size=28,
                                        weight=ft.FontWeight.W_700,
                                        color="#F8FAFC",
                                    ),
                                    ft.Text(
                                        "单按钮启动，流式接收 OpenAI 兼容 SSE，自动保存生成的 Manim 脚本。",
                                        size=14,
                                        color="#CBD5E1",
                                    ),
                                ],
                            ),
                            ft.Container(
                                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                                border_radius=999,
                                bgcolor="#0B5F55",
                                content=ft.Text("Flet + OpenAI SDK", color="#ECFDF5", size=12),
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self.run_button,
                            self.busy_ring,
                            ft.Column(
                                spacing=8,
                                expand=True,
                                controls=[
                                    self.status_label,
                                    self.progress_bar,
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

        editor_tabs = ft.Tabs(
            length=4,
            expand=True,
            content=ft.Column(
                expand=True,
                spacing=14,
                controls=[
                    ft.TabBar(
                        scrollable=False,
                        tab_alignment=ft.TabAlignment.FILL,
                        label_color="#0F172A",
                        unselected_label_color="#64748B",
                        divider_color="#D8E0EC",
                        indicator_color="#0F766E",
                        tabs=[
                            ft.Tab(label="题目描述"),
                            ft.Tab(label="标准题解"),
                            ft.Tab(label="标准代码"),
                            ft.Tab(label="额外要求"),
                        ],
                    ),
                    ft.Container(
                        expand=True,
                        padding=20,
                        border_radius=20,
                        bgcolor="#F8FAFC",
                        border=ft.border.all(1, "#D8E0EC"),
                        content=ft.TabBarView(
                            expand=True,
                            controls=[
                                self.problem_input,
                                self.solution_input,
                                self.code_input,
                                self.extra_input,
                            ],
                        ),
                    ),
                ],
            ),
        )

        settings_tile = ft.ExpansionTile(
            title=ft.Text("隐藏设置"),
            subtitle=ft.Text("模型、SSE 接口、输出目录、自动渲染"),
            expanded=False,
            maintain_state=True,
            controls=[
                ft.Container(
                    padding=20,
                    border_radius=20,
                    bgcolor="#F8FAFC",
                    border=ft.border.all(1, "#D8E0EC"),
                    content=ft.Column(
                        spacing=18,
                        controls=[
                            self._settings_section(
                                "连接设置",
                                "OpenAI 兼容接口与鉴权信息",
                                [
                                    self._field_block("API Base URL", self.base_url_input),
                                    self._field_block("API Key", self.api_key_input),
                                ],
                            ),
                            self._settings_section(
                                "模型设置",
                                "模型名、采样参数和超时",
                                [
                                    ft.Row(
                                        spacing=14,
                                        vertical_alignment=ft.CrossAxisAlignment.START,
                                        controls=[
                                            self._field_block("Model", self.model_input, expand=True),
                                            self._field_block(
                                                "Temperature",
                                                ft.Column(
                                                    spacing=6,
                                                    controls=[
                                                        self.temperature_input,
                                                        ft.Row(
                                                            alignment=ft.MainAxisAlignment.END,
                                                            controls=[self.temperature_value],
                                                        ),
                                                    ],
                                                ),
                                                expand=True,
                                            ),
                                            self._field_block("超时（秒）", self.timeout_input),
                                        ],
                                    ),
                                ],
                            ),
                            self._settings_section(
                                "输出设置",
                                "脚本目录与渲染策略",
                                [
                                    self._field_block("输出目录", self.output_dir_input),
                                    ft.Container(
                                        padding=16,
                                        border_radius=16,
                                        bgcolor="#FFFFFF",
                                        border=ft.border.all(1, "#D8E0EC"),
                                        content=ft.Row(
                                            spacing=14,
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            controls=[
                                                self.auto_render_input,
                                                ft.Column(
                                                    spacing=2,
                                                    controls=[
                                                        ft.Text(
                                                            "生成后自动调用 Manim 渲染",
                                                            size=14,
                                                            weight=ft.FontWeight.W_600,
                                                            color="#0F172A",
                                                        ),
                                                        ft.Text(
                                                            "如果当前环境未安装 manim，会自动跳过渲染。",
                                                            size=12,
                                                            color="#64748B",
                                                        ),
                                                    ],
                                                ),
                                            ],
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
            ],
        )

        materials_card = self._card(
            "输入素材",
            "左侧只保留当前编辑所需内容，不再把所有大文本框堆在一列。",
            [
                ft.Row(
                    tight=False,
                    controls=[
                        self.title_input,
                        self.language_input,
                    ],
                ),
                ft.Container(height=460, content=editor_tabs),
                settings_tile,
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

        output_card = self._card(
            "实时输出",
            "左侧是脚本实时预览，右侧是流式日志和执行轨迹。",
            [
                ft.Row(
                    expand=True,
                    spacing=18,
                    controls=[
                        ft.Container(
                            expand=3,
                            height=640,
                            content=self.script_output,
                        ),
                        ft.Container(
                            expand=2,
                            height=640,
                            content=self.log_output,
                        ),
                    ],
                ),
                self.result_path_text,
            ],
            expand=True,
        )

        left_panel = ft.Container(
            width=540,
            height=760,
            content=materials_card,
        )
        right_panel = ft.Container(
            expand=True,
            height=760,
            content=output_card,
        )

        layout = ft.Column(
            expand=True,
            spacing=22,
            controls=[
                hero,
                ft.Row(
                    expand=True,
                    spacing=22,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        left_panel,
                        right_panel,
                    ],
                ),
            ],
        )

        self.page.add(layout)

    def _apply_loaded_state(self) -> None:
        self.base_url_input.value = self.api_config.base_url
        self.api_key_input.value = self.api_config.api_key
        self.model_input.value = self.api_config.model
        self.temperature_input.value = self.api_config.temperature
        self.temperature_value.value = f"{self.api_config.temperature:.1f}"
        self.timeout_input.value = str(self.api_config.timeout_seconds)
        self.output_dir_input.value = self.preferences.output_dir
        self.auto_render_input.value = self.preferences.auto_render

        self.title_input.value = self.request.title
        self.language_input.value = self.request.language
        self.problem_input.value = self.request.problem_statement
        self.solution_input.value = self.request.official_solution
        self.code_input.value = self.request.reference_code
        self.extra_input.value = self.request.additional_requirements
        self.page.update()

    def _card(
            self,
            title: str,
            subtitle: str,
            controls: list[ft.Control],
            expand: bool = False,
            scroll: ft.ScrollMode | None = None,
    ) -> ft.Container:
        return ft.Container(
            expand=expand,
            padding=24,
            border_radius=28,
            bgcolor="#FFFFFF",
            border=ft.border.all(1, "#D8E0EC"),
            content=ft.Column(
                expand=expand,
                scroll=scroll,
                spacing=18,
                controls=[
                    ft.Column(
                        spacing=4,
                        controls=[
                            ft.Text(title, size=22, weight=ft.FontWeight.W_700, color="#0F172A"),
                            ft.Text(subtitle, size=13, color="#64748B"),
                        ],
                    ),
                    *controls,
                ],
            ),
        )

    def _settings_section(
            self,
            title: str,
            subtitle: str,
            controls: list[ft.Control],
    ) -> ft.Container:
        return ft.Container(
            padding=18,
            border_radius=18,
            bgcolor="#FFFFFF",
            border=ft.border.all(1, "#E2E8F0"),
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text(title, size=15, weight=ft.FontWeight.W_700, color="#0F172A"),
                            ft.Text(subtitle, size=12, color="#64748B"),
                        ],
                    ),
                    *controls,
                ],
            ),
        )

    def _field_block(
            self,
            label: str,
            control: ft.Control,
            expand: bool = False,
    ) -> ft.Column:
        return ft.Column(
            expand=expand,
            spacing=6,
            controls=[
                ft.Text(label, size=12, weight=ft.FontWeight.W_600, color="#334155"),
                control,
            ],
        )

    def _multiline_input(self, label: str, lines: int, code: bool = False) -> ft.TextField:
        style = ft.TextStyle(font_family="Consolas", size=13) if code else None
        return ft.TextField(
            label=label,
            multiline=True,
            min_lines=lines,
            max_lines=lines + 4,
            border_radius=18,
            text_style=style,
        )

    def on_temperature_change(self, event: ft.ControlEvent) -> None:
        value = float(event.control.value or 0.0)
        self.temperature_value.value = f"{value:.1f}"
        self.page.update()

    def start_generation(self, _: ft.ControlEvent) -> None:
        if self.busy:
            return

        validation_error = self._validate_inputs()
        if validation_error:
            self._notify(validation_error, error=True)
            return

        self.busy = True
        self._stream_buffer = ""
        self._last_stream_flush = 0.0
        self.script_output.value = ""
        self.log_output.value = ""
        self.last_script_path = None
        self.last_video_path = None

        self._set_status("正在准备任务...", 0.05)
        self._set_busy(True)
        self._append_log("开始新的生成任务。")
        self.page.run_thread(self._run_generation_pipeline)

    def _run_generation_pipeline(self) -> None:
        config = self._read_api_config()
        request = self._read_generation_request()
        preferences = self._read_preferences()

        try:
            save_state(config, request, preferences)
            self._set_status("正在连接模型...", 0.12)
            self._append_log(f"模型: {config.model}")
            self._append_log(f"Base URL: {config.normalized_base_url()}")

            result = ChatCompletionsClient(config).generate_manim_script_stream(
                request,
                on_status=self._handle_stream_status,
                on_delta=self._handle_stream_delta,
                on_debug=self._append_log,
            )
            self._flush_stream_buffer(force=True)

            self._set_status("正在自动保存脚本...", 0.9)
            script_path = save_script(default_script_path(preferences.output_dir, request.title), result.manim_code)
            self.last_script_path = str(script_path)
            self.script_output.value = result.manim_code
            self.result_path_text.value = f"脚本已自动保存到: {script_path}"
            self._append_log(f"脚本已保存: {script_path}")
            self._safe_update()

            if preferences.auto_render:
                if not is_manim_installed():
                    self.result_path_text.value = f"脚本已保存到: {script_path}（已跳过渲染：未安装 manim）"
                    self._append_log("未检测到 manim，已跳过自动渲染。")
                    self._safe_update()
                    self._set_status("脚本已生成，未渲染。", 1.0)
                    self._notify("脚本已生成；当前环境未安装 manim，已跳过渲染。")
                    return

                self._set_status("正在调用 Manim 渲染...", None)
                render_result = render_script(script_path, preferences.output_dir)
                if render_result.stdout.strip():
                    self._append_log("[manim stdout]")
                    self._append_log(render_result.stdout)
                if render_result.stderr.strip():
                    self._append_log("[manim stderr]")
                    self._append_log(render_result.stderr)
                if render_result.return_code != 0:
                    raise RuntimeError(f"manim 渲染失败，退出码: {render_result.return_code}")
                if render_result.video_path:
                    self.last_video_path = render_result.video_path
                    self.result_path_text.value = f"视频已输出到: {render_result.video_path}"
                    self._append_log(f"视频已输出: {render_result.video_path}")
                    self._safe_update()

            self._set_status("完成。", 1.0)
            self._notify("Manim 脚本已生成并保存。")
        except Exception as exc:  # noqa: BLE001
            self._flush_stream_buffer(force=True)
            self._set_status("失败。", 1.0, error=True)
            self._append_log("[错误]")
            self._append_log(format_exception(exc))
            self._notify(str(exc), error=True)
        finally:
            self.busy = False
            self._set_busy(False)

    def _handle_stream_status(self, message: str) -> None:
        self._set_status(message, None)
        self._append_log(message)

    def _handle_stream_delta(self, text: str) -> None:
        self._stream_buffer += text
        now = time.monotonic()
        if len(self._stream_buffer) >= 160 or now - self._last_stream_flush >= 0.12:
            self._flush_stream_buffer()

    def _flush_stream_buffer(self, force: bool = False) -> None:
        if not self._stream_buffer and not force:
            return
        if self._stream_buffer:
            self.script_output.value += self._stream_buffer
            self._stream_buffer = ""
            self._last_stream_flush = time.monotonic()
        self._safe_update()

    def _read_api_config(self) -> ApiConfig:
        timeout_text = (self.timeout_input.value or "180").strip()
        return ApiConfig(
            base_url=(self.base_url_input.value or "").strip(),
            api_key=(self.api_key_input.value or "").strip(),
            model=(self.model_input.value or "").strip(),
            temperature=float(self.temperature_input.value or 0.2),
            timeout_seconds=int(timeout_text or "180"),
        )

    def _read_generation_request(self) -> GenerationRequest:
        return GenerationRequest(
            title=(self.title_input.value or "").strip(),
            language=(self.language_input.value or "中文").strip(),
            problem_statement=(self.problem_input.value or "").strip(),
            official_solution=(self.solution_input.value or "").strip(),
            reference_code=(self.code_input.value or "").strip(),
            additional_requirements=(self.extra_input.value or "").strip(),
        )

    def _read_preferences(self) -> AppPreferences:
        output_dir = (self.output_dir_input.value or "").strip() or "outputs"
        return AppPreferences(
            output_dir=output_dir,
            auto_render=bool(self.auto_render_input.value),
        )

    def _validate_inputs(self) -> str | None:
        config = self._read_api_config()
        request = self._read_generation_request()

        if not config.base_url:
            return "请填写 API Base URL。"
        if not config.model:
            return "请填写模型名。"
        if not request.title:
            return "请填写题目标题。"
        if not request.problem_statement:
            return "请填写题目描述。"
        if not request.official_solution:
            return "请填写标准题解。"
        if not request.reference_code:
            return "请填写标准代码。"
        try:
            int((self.timeout_input.value or "180").strip())
        except ValueError:
            return "超时必须是整数秒。"
        return None

    def _set_busy(self, busy: bool) -> None:
        self.run_button.disabled = busy
        self.busy_ring.visible = busy
        self.page.window.progress_bar = None if busy else 1.0
        self._safe_update()

    def _set_status(self, text: str, progress: float | None, error: bool = False) -> None:
        self.status_label.value = text
        self.status_label.color = "#B42318" if error else "#334155"
        self.progress_bar.value = progress
        self.progress_bar.color = "#D92D20" if error else "#0F766E"
        self.page.window.progress_bar = progress
        self._safe_update()

    def _append_log(self, message: str) -> None:
        existing = self.log_output.value or ""
        line = message.rstrip()
        self.log_output.value = f"{existing}{line}\n" if existing else f"{line}\n"
        self._safe_update()

    def _notify(self, message: str, error: bool = False) -> None:
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor="#B42318" if error else "#0F766E",
        )
        self.page.snack_bar.open = True
        self._safe_update()

    def _safe_update(self) -> None:
        self.page.update()


def format_exception(exc: Exception) -> str:
    return "".join(traceback.format_exception(exc)).strip()


def main(page: ft.Page) -> None:
    AlgorithmVideoGeneratorApp(page)


def run() -> None:
    ft.run(main)


if __name__ == "__main__":
    run()
