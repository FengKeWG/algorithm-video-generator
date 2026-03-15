from __future__ import annotations

import ast
import re


PYTHON_BLOCK_RE = re.compile(r"```python\s+(.*?)```", re.IGNORECASE | re.DOTALL)
CODE_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_-]*\s+(.*?)```", re.DOTALL)
NON_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
MANIM_IMPORT_RE = re.compile(r"from\s*manim\s*import\s*\*", re.IGNORECASE)
ALGORITHM_SCENE_RE = re.compile(r"class\s+AlgorithmVideo\s*\(\s*Scene\s*\)\s*:")


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
