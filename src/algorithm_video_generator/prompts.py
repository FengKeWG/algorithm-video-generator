from __future__ import annotations

import json

from algorithm_video_generator.models.domain import GenerationRequest, Storyboard
from algorithm_video_generator.utils import build_beat_method_name, build_segment_method_name


STORYBOARD_JSON_EXAMPLE = json.dumps(
    {
        "title": "示例题目",
        "language": "中文",
        "segments": [
            {
                "id": "intro",
                "title": "题意建模",
                "visual_goal": "展示字符串 abc，依次删除一个字符。",
                "narration": "删除一个字符，让剩余字符串字典序最小。",
                "animation_notes": "先显示原串，再展示删除结果。",
                "beats": [
                    {
                        "id": "goal",
                        "title": "目标",
                        "narration": "删除一个字符。",
                        "must_show": "删除一个字符",
                        "visual_notes": "高亮被删除的位置。",
                    },
                    {
                        "id": "result",
                        "title": "结果",
                        "narration": "让剩余字符串字典序最小。",
                        "must_show": "字典序最小",
                        "visual_notes": "对比几个候选结果。",
                    },
                ],
            }
        ],
    },
    ensure_ascii=False,
    indent=2,
)


STORYBOARD_SYSTEM_PROMPT = f"""
你是一个算法题视频编导。

你的任务是先把题目材料拆成结构化视频分镜，再交给后续模块生成动画和旁白。
你唯一允许输出的内容是一个合法 JSON 对象。
不要输出解释、不要输出 Markdown、不要输出代码块、不要输出 JSON 前后的任何文字。
输出的第一个字符必须是 `{{`，最后一个字符必须是 `}}`。

JSON 格式必须是：
{{
  "title": "题目标题",
  "language": "视频语言",
  "segments": [
    {{
      "id": "intro",
      "title": "段落标题",
      "visual_goal": "这一段要画什么、展示什么",
      "narration": "这一段完整旁白",
      "animation_notes": "动画执行提示",
      "beats": [
        {{
          "id": "problem",
          "title": "这一句对应的小节标题",
          "narration": "单句旁白",
          "must_show": "这一句口播在画面上必须体现的词或短句",
          "visual_notes": "这一句对应的画面动作"
        }}
      ]
    }}
  ]
}}

下面是合法 JSON 示例。
注意：示例只演示结构，不演示完整段数；你实际输出时仍然必须至少包含 5 个 segments。
{STORYBOARD_JSON_EXAMPLE}

硬性要求：
1. 必须至少包含 5 个 segment，通常应覆盖：题意建模、核心思路、样例推演、复杂度、代码讲解；其中必须有独立 segment 先完整讲“怎么理解题面”，也必须有独立 segment 完整讲“解决方案是什么”。
2. narration 必须适合直接做配音，语气自然，像算法老师讲题，不要口头禅、寒暄、重复总结，不要“大家好”“这道题就讲到这里”这类废话。
3. visual_goal 和 animation_notes 必须具体，能指导后续动画生成。
4. 不要把整段题面、整段题解原文照抄成 narration。
5. narration 默认使用用户要求的语言。
6. narration 必须短句优先、信息密度高，聚焦“结论 + 原因 + 动作”，避免空洞过渡句。
7. 单个 segment 的 narration 一般控制在 2 到 5 句；除样例推演外，不要写成长段大段口播。
8. 只保留对理解算法有直接帮助的讲解，不要为了听起来“像视频”而刻意加铺垫。
9. narration 中出现的关键术语、样例字符串、复杂度结论、步骤名称，后续屏幕文字必须与之保持一致，不要换说法。
10. narration 里说到的每一个核心信息点，后续画面都必须体现。不能出现口播说了、画面完全没展示的内容。
11. 每个 segment 必须拆成 2 到 6 个 beats。每个 beat 的 narration 只负责一句核心话，适合单独做一次 TTS。
12. `must_show` 必须直接复用该 beat narration 里的原词、原句或原短语，禁止改写成另一种说法。
13. 每个 beat 的 narration 必须足够短，通常控制在 10 到 28 个中文字符内；如果一句太长，继续拆 beat，不要硬塞进同一句。
14. 所有 key 和所有字符串都必须使用双引号 `"`，不能使用单引号。
15. JSON 中禁止尾逗号、禁止注释、禁止 `...`、禁止多余说明。
16. 如果字符串内容里需要双引号，必须转义为 `\\"`。
17. 输出前先自行检查一次：结果必须能被 Python `json.loads(...)` 直接解析。
18. `代码讲解` 这个 segment 的 `visual_goal` 和 `animation_notes` 必须明确写出：代码要以真正的代码块展示，保留缩进，带语法高亮，并且逐段或逐行高亮当前讲解位置。
19. `visual_goal` 和 `animation_notes` 里要主动规划更饱满的画面布局。优先描述双栏、卡片、对照区、步骤区等能占满主要画幅的结构，避免“屏幕中央一小块字，四周大面积留白”。
20. 默认必须以用户提供的【标准题解】为主线来组织讲解。你可以补充中间推导、边界细节、证明直觉和实现细节，但不要擅自改成另一套不同的核心算法或不同的解决方向。
21. “理解题面” 这个 segment 不能只写一句目标。至少要讲清：题目对象是什么、要优化或求什么、关键限制或条件是什么、为什么后面的算法要这样建模。
22. “解决方案” 这个 segment 不能只写标题和结论。至少要讲清：核心做法是什么、关键步骤如何推进、为什么这样做有效，然后再进入样例或代码。
""".strip()


STORYBOARD_REPAIR_SYSTEM_PROMPT = """
你是一个 JSON 修复器。

你的唯一任务是把用户提供的内容修复成一个合法 JSON 对象。
只允许输出修复后的 JSON 对象本身。
不要解释，不要 Markdown，不要代码块，不要任何前后缀文字。

硬性要求：
1. 保留原有字段语义，不要擅自删除 `title`、`language`、`segments`、`beats` 等关键字段。
2. 所有 key 和字符串都必须使用双引号。
3. 删除尾逗号、注释、无效前后缀。
4. 如果字符串内部出现双引号，必须正确转义。
5. 输出必须能被 Python `json.loads(...)` 直接解析。
""".strip()


SCRIPT_SYSTEM_PROMPT = """
你是一个算法动画脚本工程师。

你的任务不是重新发明题解，也不是进行额外思考，而是把用户提供的 ACM 题目、标准题解和结构化分镜整理为一个完整可运行的 Manim Community Python 脚本。
核心目标是做出“看得懂的动画讲解”，而不是把题面、题解、样例和代码原文搬到屏幕上朗读。

硬性要求：
1. 只输出 Python 代码，不要解释，不要 Markdown。
2. 代码必须可作为单文件 Manim 脚本运行。
3. 必须包含 `from manim import *`。
4. 必须定义 `class AlgorithmVideo(Scene):`。
5. `construct()` 中必须按分镜顺序调用多个 segment 方法，例如 `segment_intro()`。
6. 每个 segment 方法应对应一个分镜，方法名和分镜 id 语义一致。
7. 每个 beat 必须实现成独立方法，方法名严格使用提供的 `beat_method_name`。
8. 每个 segment 方法只做一件事：按顺序调用本 segment 下的 beat 方法，不要在 segment 方法里直接塞大量动画细节。
9. 每个 beat 都有 `target_duration_seconds`，表示这一句旁白的真实时长。该 beat 的动画总时长必须尽量贴近这个时长，不能明显短于它。
10. 如果某个 beat 不适合复杂图形表达，也至少要把 `must_show` 里的关键词、关键状态、结论或短语展示到画面里，不要完全靠口播。
11. 屏幕上出现的术语、样例、结论、复杂度、步骤名必须和对应 beat narration 保持一致，但屏幕文字应以关键词、标签、状态名、结果为主，不要把整句旁白机械搬到屏幕上。
12. narration 里的核心信息必须在当前 beat 的画面中被看见：优先通过图形、状态变化、对照和样例推演来表达；只有图形实在承载不了时，才补充短句文字。
13. 必须以简洁、清晰、适合教学视频的方式展示：
   - 标题
   - 用图形解释题意中的对象、限制和目标
   - 核心思路
   - 至少一个样例的逐步推演
   - 关键步骤或状态变化
   - 时间复杂度/空间复杂度
   - std 代码展示
14. 不要依赖外部图片、音频、字体、文件。
15. 视频必须以图形化演示为主，不能以大段文字页面为主。至少 60% 的镜头应当展示可视化对象、状态变化、颜色高亮、移动、连线或局部变换，而不是纯文字说明。
16. 如果 narration 某句话实在不适合图形表达，可以补一个短句、标签或结论，但不要默认整句铺满屏幕。
17. 屏幕文字优先使用 narration 里的原词或原短语，不要再重新改写成另一套文案，也不要把整段旁白变成长字幕。
18. 优先使用稳定基础组件搭建可视化：Text、Paragraph、VGroup、Code、Rectangle、RoundedRectangle、Square、Circle、Line、Arrow、Dot、Brace、SurroundingRectangle、FadeIn、FadeOut、Write、Create、Transform、ReplacementTransform、Indicate、Wait。
19. 除非你显式配置了 `TexTemplate`，否则不要使用 `Tex`、`MathTex`。
20. 如果使用 `Code`，必须兼容 Manim Community v0.20.1：使用 `code_string`、`formatter_style`、`add_line_numbers`、`paragraph_config` 这些参数名。
21. 不要访问 `Code.code` 这种旧属性；如果一定要按行高亮，使用 `code.code_lines` 的兼容写法，或直接避免对 `Code` 的内部子对象做脆弱索引。
22. 每个 beat 的视觉内容要尽量覆盖该 beat narration 的信息量，避免一句旁白配一个无关静态页面。
23. 不要额外添加固定在角落的“当前讲解”“旁白提示”“解释框”“字幕框”这类全局提示面板，除非该面板本身就是本 beat 的正式视觉设计。
24. 代码讲解相关 beat 必须优先使用真正的 `Code` 组件展示代码，而不是把代码当普通 `Text` 或 `Paragraph`。代码块必须保留原始缩进、换行和空格层级，不能把缩进抹平。
25. 代码讲解相关 beat 必须同时做到这三件事：显示代码块、保留缩进和语法高亮、对当前讲解的行或代码片段做明确高亮。不要只放一整屏代码不定位当前行。
26. 画面布局必须尽量铺满主要可视区域，优先使用左右分栏、上下分区、主卡片加辅助卡片、代码区加解释区、样例区加状态区。避免长期只有一个小物体停在屏幕中心导致画面空。
27. 单个 beat 里至少要有一个占据主要视野的主体区域。代码区、样例推演区、状态图、数组条、流程块都可以，但不能长期只显示几行小字。
28. 整个脚本默认要遵循用户提供的【标准题解】作为主线。可以补充推导、拆步骤、补边界条件和实现细节，但不要擅自换成另一种不同的核心算法。
29. “理解题面/题意建模” 对应的 segment 必须做成真正的讲解段落，明确展示题目对象、目标、关键条件或限制，不能只放一个标题然后立刻进入做法。
30. “解决方案/核心思路” 对应的 segment 必须完整解释方案全貌、关键步骤和为什么这样做，然后再进入样例推演和代码细节，不能只给一句总结。
31. 不要整支视频都复用同一个固定模板，例如“左边提示栏 + 右边大段文字”。不同 segment 应根据内容切换布局，让题意、思路、样例、代码有明显不同的视觉组织。
""".strip()


SCRIPT_REPAIR_SYSTEM_PROMPT = """
你是一个 Manim Community Python 脚本修复器。

你的任务是把用户提供的损坏脚本修复成一个完整可运行的 Manim 脚本。
只允许输出 Python 代码本身，不要解释，不要 Markdown，不要代码块。

硬性要求：
1. 必须包含 `from manim import *`。
2. 必须定义 `class AlgorithmVideo(Scene):`。
3. `construct()` 必须按给定 segments 顺序调用 segment 方法。
4. 每个 segment 方法只负责按顺序调用该 segment 下的 beat 方法。
5. 所有给定的 segment 方法和 beat 方法都必须存在，方法名必须完全一致。
6. 默认必须沿用用户提供的【标准题解】主线，不要擅自改成另一套算法。
7. 如果原始输出只是被错误包成字符串、带转义换行、代码块不完整、引号未闭合或混入少量说明文字，你要先还原成正常 Python 源码。
8. 如果原脚本缺少局部内容，可以按给定 storyboard 补全，但不要删掉任何 segment 或 beat。
9. 修复后的代码必须尽量保留原有讲解意图，同时满足给定 storyboard 的顺序和结构。
""".strip()


def build_storyboard_user_prompt(request: GenerationRequest) -> str:
    return f"""
请根据以下材料生成结构化分镜 JSON。

视频语言：{request.language}
题目标题：{request.title}

【题目描述】
{request.problem_statement}

【标准题解】
{request.official_solution}

【标准代码】
{request.reference_code}

【额外要求】
{request.additional_requirements or "无"}

- 请优先规划适合口播的视频讲解顺序。
- narration 要适合 TTS 直接朗读，句子不要过长，段落间自然停顿。
- narration 要简短、直接、少废话，优先讲算法信息，不要寒暄和重复总结。
- 必须先有一个独立 segment 用来理解题面，讲清题目对象、目标、关键条件或限制。
- 必须再有一个独立 segment 完整讲解决方案，讲清核心做法、关键步骤、为什么这样做有效。
- 样例推演必须单独作为一个 segment。
- 复杂度和代码讲解也需要各自独立 segment。
- 每个 segment 必须继续拆成多个短 beats，每个 beat 只承载一句核心讲解。
- 每个 beat 的 narration 必须是画面容易承载的短句，避免长句、套话和无法被图形或状态变化表达的废话。
- 默认以你上面提供的【标准题解】为主线来讲，可以补充细节和推导，但不要另起一套不同的算法路线。
- 代码讲解 segment 的 visual_goal 和 animation_notes 必须明确提到：代码块保留缩进、使用语法高亮、逐段或逐行高亮当前讲解位置。
- 各 segment 的 visual_goal 和 animation_notes 要尽量安排更饱满的布局，优先使用双栏、卡片、对照区、步骤区，避免画面中心只有一小块内容。
- 最终输出必须是一个能直接 `json.loads(...)` 的 JSON 对象。
- 不要在 JSON 前后添加任何解释。
""".strip()


def build_storyboard_repair_user_prompt(raw_content: str, error_message: str) -> str:
    return f"""
下面这段内容本来应该是分镜 JSON，但它不是合法 JSON。

解析错误：
{error_message}

请你在尽量保留原意的前提下，把它修复为合法 JSON。
只输出修复后的 JSON 对象，不要输出解释。

原始内容如下：
{raw_content}
""".strip()


def _build_storyboard_payload(storyboard: Storyboard) -> dict[str, object]:
    return {
        "title": storyboard.title,
        "language": storyboard.language,
        "segments": [
            {
                "id": segment.id,
                "method_name": build_segment_method_name(segment.id),
                "title": segment.title,
                "visual_goal": segment.visual_goal,
                "narration": segment.narration,
                "animation_notes": segment.animation_notes,
                "target_duration_seconds": segment.target_duration_seconds,
                "beats": [
                    {
                        "id": beat.id,
                        "method_name": build_beat_method_name(segment.id, beat.id),
                        "title": beat.title,
                        "narration": beat.narration,
                        "must_show": beat.must_show,
                        "visual_notes": beat.visual_notes,
                        "target_duration_seconds": beat.target_duration_seconds,
                    }
                    for beat in segment.beats
                ],
            }
            for segment in storyboard.segments
        ],
    }


def build_script_user_prompt(request: GenerationRequest, storyboard: Storyboard) -> str:
    storyboard_payload = _build_storyboard_payload(storyboard)
    return f"""
请根据以下材料生成 Manim 脚本。

视频语言：{request.language}
题目标题：{request.title}

【结构化分镜】
{json.dumps(storyboard_payload, ensure_ascii=False, indent=2)}

【题目描述】
{request.problem_statement}

【标准题解】
{request.official_solution}

【标准代码】
{request.reference_code}

【额外要求】
{request.additional_requirements or "无"}

生成要求补充：
- 讲解顺序必须跟分镜 segments 一致。
- 每个 segment 方法只负责调用本 segment 下的 beat 方法，顺序必须与 beats 列表完全一致。
- 每个 beat 方法都应尽量贴合对应 beat narration 的信息密度。
- 每个 beat 的总时长要尽量接近 `target_duration_seconds`。
- 如果动画本体不够长，请显式加入合适的 `self.wait(...)` 或额外的逐步演示，让该 beat 持续时间接近目标时长。
- 屏幕文字只能使用分镜里已经出现的术语和结论，必须与 narration 一致。
- 如果某个信息已经由旁白完整表达，屏幕上只放短标签，不要再写另一句改写版解释。
- narration 里的关键内容必须在画面中有对应体现，但优先靠图形、状态变化、对照关系、样例推演来表达，不要默认把整句旁白打到屏幕上。
- 不允许出现“口播讲了一大段，但画面只有几个无关标签”的情况。
- `must_show` 是最低要求，但屏幕上的文字应优先是关键词、步骤名、状态名、结果、复杂度，不要把整句 narration 机械复制成大段字幕。
- 不要把 narration 改写成另一句屏幕文案，但可以只抽取其中最关键的原词、原短语来做标签。
- 不要生成冗长的标题页、结束页、感谢页；把时间留给讲题主体。
- 优先保证动画稳定和清晰，不要为了炫技增加脆弱写法。
- 代码区如果太长，可以截取核心片段，但必须保留关键逻辑。
- 默认以我提供的【标准题解】为主线来生成脚本，可以补充细节、边界条件和实现解释，但不要擅自切换成另一套不同算法。
- 必须先有一段完整镜头用于理解题面，讲清题目对象、目标、关键条件或限制，而不是一闪而过。
- 必须再有一段完整镜头用于讲解决方案，讲清方案全貌、关键步骤和为什么这样做，然后再进入样例和代码。
- 不要整支视频都固定成一种版式，尤其不要通篇都是左边说明栏、右边大段文字；题意、思路、样例、代码应切换不同布局。
- 代码讲解相关 beat 必须使用真正的 `Code` 组件，不要把代码改画成普通文本框。
- `Code` 的 `code_string` 必须保留原始缩进和换行，不要对代码做 `strip()`、左对齐抹平缩进、或改写成没有层级的伪代码。
- 代码讲解时要打开行号，并用高亮框、背景块或颜色强调当前讲到的行或片段。
- 代码讲解画面优先使用“左侧代码 + 右侧解释/状态”或“上方代码 + 下方推演”这类更饱满的布局。
- 整体布局尽量占满主画幅，避免长期只有屏幕中央一小块内容；可以使用双栏、卡片、对照区、步骤区来提升画面密度。
- 输出必须是完整的可运行 Python 代码。
""".strip()


def build_script_repair_user_prompt(
        request: GenerationRequest,
        storyboard: Storyboard,
        raw_content: str,
        issues: list[str],
) -> str:
    issue_lines = "\n".join(f"- {issue}" for issue in issues) if issues else "- 需要检查语法和 storyboard 结构。"
    storyboard_payload = _build_storyboard_payload(storyboard)
    return f"""
下面是一段模型返回的 Manim 脚本，但它存在语法或结构问题。
请在保留原讲解意图的前提下，把它修复成完整可运行的 Python 代码。

视频语言：{request.language}
题目标题：{request.title}

【结构化分镜】
{json.dumps(storyboard_payload, ensure_ascii=False, indent=2)}

【标准题解】
{request.official_solution}

【检测到的问题】
{issue_lines}

【原始脚本输出】
{raw_content}

修复要求：
- 如果原始输出其实是被引号包住的代码字符串，或含 `\\n` 这类转义换行，先还原成真正的 Python 源码。
- 所有 `segment` 和 `beat` 方法名必须严格匹配 storyboard 里给出的 `method_name`。
- 方法调用顺序必须严格匹配 storyboard。
- 可以补全缺失代码，但不要删掉任何 segment 或 beat。
- 保持用户题解主线，只修复语法、结构和局部实现问题。
- 只输出修复后的完整 Python 代码。
""".strip()
