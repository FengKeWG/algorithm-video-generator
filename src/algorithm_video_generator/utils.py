from __future__ import annotations

import ast
import json
import re

from algorithm_video_generator.models.domain import Storyboard, StoryboardBeat


PYTHON_BLOCK_RE = re.compile(r"```python\s+(.*?)```", re.IGNORECASE | re.DOTALL)
CODE_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_-]*\s+(.*?)```", re.DOTALL)
JSON_BLOCK_RE = re.compile(r"```json\s+(.*?)```", re.IGNORECASE | re.DOTALL)
NON_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
MANIM_IMPORT_RE = re.compile(r"from\s*manim\s*import\s*\*", re.IGNORECASE)
ALGORITHM_SCENE_RE = re.compile(r"class\s+AlgorithmVideo\s*\(\s*Scene\s*\)\s*:")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])\s*|\n+")
CLAUSE_SPLIT_RE = re.compile(r"(?<=[，,：:])\s*")


def _is_code_constructor_result(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "Code"
    if isinstance(func, ast.Attribute):
        return _is_code_constructor_result(func.value)
    return False


def slugify_filename(value: str, fallback: str = "algorithm_video") -> str:
    cleaned = NON_FILENAME_RE.sub("_", value.strip()).strip("._")
    return cleaned or fallback


def coerce_message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def extract_python_code(text: str) -> str:
    python_match = PYTHON_BLOCK_RE.search(text)
    if python_match:
        return python_match.group(1).strip()

    code_match = CODE_BLOCK_RE.search(text)
    if code_match:
        return code_match.group(1).strip()

    return text.strip()


def extract_json_object(text: str) -> str:
    json_match = JSON_BLOCK_RE.search(text)
    if json_match:
        return json_match.group(1).strip()

    start = text.find("{")
    if start == -1:
        return text.strip()

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1].strip()

    return text[start:].strip()


def split_narration_into_beats(text: str, max_chars: int = 26) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    sentences = [item.strip() for item in SENTENCE_SPLIT_RE.split(normalized) if item.strip()]
    if not sentences:
        sentences = [normalized]

    beats: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            beats.append(sentence)
            continue

        clauses = [item.strip() for item in CLAUSE_SPLIT_RE.split(sentence) if item.strip()]
        if len(clauses) <= 1:
            beats.append(sentence)
            continue

        current = ""
        for clause in clauses:
            candidate = f"{current}{clause}" if current else clause
            if len(candidate) <= max_chars or not current:
                current = candidate
                continue
            beats.append(current)
            current = clause
        if current:
            beats.append(current)

    return [beat for beat in beats if beat]


def build_segment_method_name(segment_id: str) -> str:
    return f"segment_{segment_id}"


def build_beat_method_name(segment_id: str, beat_id: str) -> str:
    return f"beat_{segment_id}_{beat_id}"


def validate_storyboard_script_structure(manim_code: str, storyboard: Storyboard) -> tuple[bool, list[str]]:
    issues: list[str] = []

    try:
        module = ast.parse(manim_code)
    except SyntaxError as exc:
        return False, [f"脚本不是合法 Python: {exc.msg}"]

    scene_class = next(
        (
            node for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "AlgorithmVideo"
        ),
        None,
    )
    if scene_class is None:
        return False, ["缺少 AlgorithmVideo 场景类。"]

    methods = {
        node.name: node
        for node in scene_class.body
        if isinstance(node, ast.FunctionDef)
    }

    def collect_self_calls(function_node: ast.FunctionDef) -> list[str]:
        calls: list[str] = []
        for node in ast.walk(function_node):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "self"
            ):
                calls.append(func.attr)
        return calls

    construct = methods.get("construct")
    if construct is None:
        issues.append("缺少 construct 方法。")
    else:
        construct_calls = collect_self_calls(construct)
        expected_segments = [build_segment_method_name(segment.id) for segment in storyboard.segments]
        actual_segments = [name for name in construct_calls if name in expected_segments]
        if actual_segments != expected_segments:
            issues.append(f"construct 中的 segment 调用顺序不匹配，期望 {expected_segments}，实际 {actual_segments}")

    for segment in storyboard.segments:
        segment_method = build_segment_method_name(segment.id)
        segment_function = methods.get(segment_method)
        if segment_function is None:
            issues.append(f"缺少方法定义: {segment_method}")
            continue

        expected_beats = [build_beat_method_name(segment.id, beat.id) for beat in segment.beats]
        for beat_method in expected_beats:
            if beat_method not in methods:
                issues.append(f"缺少方法定义: {beat_method}")

        segment_calls = collect_self_calls(segment_function)
        actual_beats = [name for name in segment_calls if name in expected_beats]
        if actual_beats != expected_beats:
            issues.append(f"{segment_method} 中的 beat 调用顺序不匹配，期望 {expected_beats}，实际 {actual_beats}")

    return not issues, issues


def inject_segment_timing(manim_code: str, storyboard: Storyboard, inter_beat_gap: float = 0.25) -> str:
    if "_run_timed_beat" in manim_code:
        return manim_code

    scene_match = ALGORITHM_SCENE_RE.search(manim_code)
    if not scene_match:
        return manim_code

    beat_targets: dict[str, float] = {}
    ordered_beats: list[tuple[str, StoryboardBeat]] = []
    for segment in storyboard.segments:
        for beat in segment.beats:
            ordered_beats.append((segment.id, beat))

    for index, (segment_id, beat) in enumerate(ordered_beats):
        if beat.target_duration_seconds is None:
            continue
        method_name = build_beat_method_name(segment_id, beat.id)
        target = float(beat.target_duration_seconds)
        if index < len(ordered_beats) - 1:
            target += inter_beat_gap
        beat_targets[method_name] = round(target, 3)

    helper_block = (
        "\n"
        "    _BEAT_TARGETS = "
        f"{json.dumps(beat_targets, ensure_ascii=False, sort_keys=True)}\n"
        "\n"
        "    def _run_timed_beat(self, beat_key, callback):\n"
        "        target = float(self._BEAT_TARGETS.get(beat_key, 0.0) or 0.0)\n"
        "        start_time = float(getattr(self.renderer, 'time', 0.0))\n"
        "        callback()\n"
        "        elapsed = float(getattr(self.renderer, 'time', 0.0)) - start_time\n"
        "        remaining = target - elapsed\n"
        "        if remaining > 0.05:\n"
        "            self.wait(remaining)\n"
    )

    insertion_point = scene_match.end()
    timed_code = manim_code[:insertion_point] + helper_block + manim_code[insertion_point:]
    replacement_count = 0

    for segment in storyboard.segments:
        for beat in segment.beats:
            method_name = build_beat_method_name(segment.id, beat.id)
            timed_code, count = re.subn(
                rf"self\.{re.escape(method_name)}\(\)",
                rf'self._run_timed_beat("{method_name}", self.{method_name})',
                timed_code,
            )
            replacement_count += count

    if replacement_count < len(beat_targets):
        fallback_code = build_fallback_manim_code(storyboard)
        if fallback_code != manim_code:
            return inject_segment_timing(fallback_code, storyboard, inter_beat_gap)
        return manim_code
    return timed_code


def build_fallback_manim_code(storyboard: Storyboard) -> str:
    lines: list[str] = [
        "from manim import *",
        "",
        "",
        "class AlgorithmVideo(Scene):",
        "    def construct(self):",
        "        self._header = None",
        "        self._body = None",
    ]
    for segment in storyboard.segments:
        lines.append(f"        self.{build_segment_method_name(segment.id)}()")

    lines.extend(
        [
            "",
            "    def _make_text_block(self, text, font_size=28, color=WHITE, max_chars=18):",
            "        text = str(text or '').strip()",
            "        chunks = [text[i:i + max_chars] for i in range(0, len(text), max_chars)] or ['']",
            "        group = VGroup(*[Text(chunk, font_size=font_size, color=color) for chunk in chunks if chunk])",
            "        if len(group) == 0:",
            "            group = VGroup(Text('', font_size=font_size, color=color))",
            "        group.arrange(DOWN, aligned_edge=LEFT, buff=0.15)",
            "        return group",
            "",
            "    def _set_header(self, text):",
            "        new_header = Text(text, font_size=36, color=YELLOW).to_edge(UP)",
            "        if self._header is None:",
            "            self.play(FadeIn(new_header, shift=UP * 0.2), run_time=0.4)",
            "            self._header = new_header",
            "            return",
            "        self.play(ReplacementTransform(self._header, new_header), run_time=0.4)",
            "        self._header = new_header",
            "",
            "    def _show_beat(self, beat_title, beat_text):",
            "        title_block = self._make_text_block(beat_title, font_size=30, color=BLUE_B, max_chars=14)",
            "        main_block = self._make_text_block(beat_text, font_size=28, color=WHITE, max_chars=18)",
            "        content = VGroup(title_block, main_block).arrange(DOWN, aligned_edge=LEFT, buff=0.35)",
            "        frame = SurroundingRectangle(content, color=GREY_B, buff=0.35, corner_radius=0.12)",
            "        body = VGroup(frame, content).move_to(ORIGIN)",
            "        if self._body is None:",
            "            self.play(FadeIn(body, shift=UP * 0.15), run_time=0.45)",
            "            self._body = body",
            "            return",
            "        self.play(FadeOut(self._body, shift=UP * 0.08), FadeIn(body, shift=UP * 0.08), run_time=0.45)",
            "        self._body = body",
        ]
    )

    for segment in storyboard.segments:
        lines.extend(
            [
                "",
                f"    def {build_segment_method_name(segment.id)}(self):",
                f"        self._set_header({segment.title!r})",
            ]
        )
        for beat in segment.beats:
            lines.append(f"        self.{build_beat_method_name(segment.id, beat.id)}()")

        for beat in segment.beats:
            lines.extend(
                [
                    "",
                    f"    def {build_beat_method_name(segment.id, beat.id)}(self):",
                    f"        self._show_beat({beat.title!r}, {beat.narration!r})",
                    "        self.play(Indicate(self._body, color=YELLOW, scale_factor=1.02), run_time=0.35)",
                ]
            )

    lines.append("")
    return "\n".join(lines)


class _ManimCompatTransformer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.changed = False

    def _normalize_formatter_style(self, value: ast.expr) -> ast.expr:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            normalized = value.value.lower()
            if normalized != value.value:
                self.changed = True
                return ast.Constant(normalized)
        return value

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name != "Code":
            return node

        has_code_keyword = any(keyword.arg in {"code_file", "code_string"} for keyword in node.keywords)
        if node.args and not has_code_keyword:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str) and "\n" in first_arg.value:
                node.args = node.args[1:]
                node.keywords.insert(0, ast.keyword(arg="code_string", value=first_arg))
                self.changed = True

        paragraph_dict: ast.Dict | None = None
        paragraph_items: list[tuple[str, ast.expr]] = []
        rewritten_keywords: list[ast.keyword] = []

        for keyword in node.keywords:
            if keyword.arg == "code":
                rewritten_keywords.append(ast.keyword(arg="code_string", value=keyword.value))
                self.changed = True
                continue
            if keyword.arg == "style":
                rewritten_keywords.append(ast.keyword(arg="formatter_style", value=self._normalize_formatter_style(keyword.value)))
                self.changed = True
                continue
            if keyword.arg == "formatter_style":
                rewritten_keywords.append(ast.keyword(arg="formatter_style", value=self._normalize_formatter_style(keyword.value)))
                continue
            if keyword.arg == "insert_line_no":
                rewritten_keywords.append(ast.keyword(arg="add_line_numbers", value=keyword.value))
                self.changed = True
                continue
            if keyword.arg in {"font_size", "line_spacing", "font", "alignment", "disable_ligatures"}:
                paragraph_items.append((keyword.arg, keyword.value))
                self.changed = True
                continue
            if keyword.arg == "paragraph_config" and isinstance(keyword.value, ast.Dict):
                paragraph_dict = keyword.value
            rewritten_keywords.append(keyword)

        if paragraph_items:
            if paragraph_dict is None:
                paragraph_dict = ast.Dict(keys=[], values=[])
                rewritten_keywords.append(ast.keyword(arg="paragraph_config", value=paragraph_dict))
                self.changed = True

            existing_keys = {
                key.value
                for key in paragraph_dict.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            for key_name, value in paragraph_items:
                if key_name in existing_keys:
                    continue
                paragraph_dict.keys.append(ast.Constant(key_name))
                paragraph_dict.values.append(value)
                self.changed = True

        node.keywords = rewritten_keywords
        return node


class _CodeLineAccessAnalyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self._scope_stack: list[set[str]] = [set()]
        self.zero_based_names: set[str] = set()

    @property
    def _code_names(self) -> set[str]:
        return self._scope_stack[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope_stack.append(set())
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scope_stack.append(set())
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        if _is_code_constructor_result(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._code_names.add(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if _is_code_constructor_result(node.value) and isinstance(node.target, ast.Name):
            self._code_names.add(node.target.id)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.value, ast.Attribute):
            base = node.value.value
            if (
                isinstance(base, ast.Name)
                and base.id in self._code_names
                and node.value.attr in {"code", "code_lines"}
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, int)
                and node.slice.value == 0
            ):
                self.zero_based_names.add(base.id)
        self.generic_visit(node)


class _CodeLineCompatTransformer(ast.NodeTransformer):
    def __init__(self, zero_based_names: set[str]) -> None:
        self.changed = False
        self.requires_helper = False
        self.zero_based_names = zero_based_names
        self._scope_stack: list[set[str]] = [set()]

    @property
    def _code_names(self) -> set[str]:
        return self._scope_stack[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self._scope_stack.append(set())
        node = self.generic_visit(node)
        self._scope_stack.pop()
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        self._scope_stack.append(set())
        node = self.generic_visit(node)
        self._scope_stack.pop()
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        node = self.generic_visit(node)
        if _is_code_constructor_result(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._code_names.add(target.id)
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        node = self.generic_visit(node)
        if _is_code_constructor_result(node.value) and isinstance(node.target, ast.Name):
            self._code_names.add(node.target.id)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        node = self.generic_visit(node)
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "code"
            and isinstance(node.value, ast.Name)
            and node.value.id in self._code_names
        ):
            node.attr = "code_lines"
            self.changed = True
        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        node = self.generic_visit(node)
        if not isinstance(node, ast.Subscript):
            return node

        if not isinstance(node.value, ast.Attribute):
            return node

        base = node.value.value
        if (
            not isinstance(base, ast.Name)
            or base.id not in self._code_names
            or node.value.attr not in {"code", "code_lines"}
        ):
            return node

        self.changed = True
        self.requires_helper = True
        return ast.Call(
            func=ast.Name(id="_safe_code_line", ctx=ast.Load()),
            args=[
                ast.Name(id=base.id, ctx=ast.Load()),
                node.slice,
                ast.Constant(base.id in self.zero_based_names),
            ],
            keywords=[],
        )


SAFE_CODE_LINE_HELPER = """
def _safe_code_line(code_obj, line_ref, zero_based=False):
    lines = getattr(code_obj, "code_lines", None)
    if lines is None:
        lines = getattr(code_obj, "code", None)
    if lines is None:
        return code_obj
    total = len(lines)
    if total == 0:
        return code_obj
    if isinstance(line_ref, int):
        index = line_ref if zero_based else line_ref - 1
        if index < 0:
            index = 0
        elif index >= total:
            index = total - 1
        return lines[index]
    return lines[line_ref]
""".strip()


def normalize_manim_code(text: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text

    transformer = _ManimCompatTransformer()
    tree = transformer.visit(tree)

    analyzer = _CodeLineAccessAnalyzer()
    analyzer.visit(tree)

    code_line_transformer = _CodeLineCompatTransformer(analyzer.zero_based_names)
    tree = code_line_transformer.visit(tree)

    if code_line_transformer.requires_helper:
        helper_exists = any(
            isinstance(node, ast.FunctionDef) and node.name == "_safe_code_line" for node in tree.body
        )
        if not helper_exists:
            helper_module = ast.parse(SAFE_CODE_LINE_HELPER)
            tree.body = [*helper_module.body, *tree.body]
            code_line_transformer.changed = True

    if not transformer.changed and not code_line_transformer.changed:
        return text

    ast.fix_missing_locations(tree)
    normalized = ast.unparse(tree)
    if text.endswith("\n"):
        return normalized + "\n"
    return normalized


def repair_manim_code(text: str) -> str:
    repaired = text
    repaired = MANIM_IMPORT_RE.sub("from manim import *", repaired, count=1)
    repaired = ALGORITHM_SCENE_RE.sub("class AlgorithmVideo(Scene):", repaired, count=1)
    repaired = normalize_manim_code(repaired)
    return repaired


def has_required_manim_markers(text: str) -> bool:
    return bool(MANIM_IMPORT_RE.search(text) and ALGORITHM_SCENE_RE.search(text))
