"""Text comparison without GUI dependencies.

Indices and spans use Python Unicode codepoints, not UTF-16 positions. CRLF and
CR are normalized to LF; a final newline is retained as an empty source line.

Practical limits: after stripping common prefixes/suffixes, line comparisons
above 4 million candidate pairs or 20,000 lines per side use one conservative
replacement hunk. Intraline matching above 1 million candidate pairs or 10,000
characters per side highlights the unmatched middle instead. These limits keep
difflib's quadratic cases (especially repeated text) bounded. Fallbacks preserve
all original text and merge ranges, but may align changes less finely.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, unified_diff
from time import perf_counter
from typing import Optional


@dataclass(frozen=True)
class DiffOptions:
    ignore_whitespace: bool = False
    ignore_case: bool = False


@dataclass(frozen=True)
class Span:
    start: int
    end: int


@dataclass(frozen=True)
class DiffRow:
    left_index: Optional[int]
    right_index: Optional[int]
    kind: str
    left_spans: tuple[Span, ...] = ()
    right_spans: tuple[Span, ...] = ()


@dataclass(frozen=True)
class DiffChange:
    start_row: int
    end_row: int
    tag: str
    left_start: int
    left_end: int
    right_start: int
    right_end: int


@dataclass(frozen=True)
class DiffResult:
    left_lines: tuple[str, ...]
    right_lines: tuple[str, ...]
    rows: tuple[DiffRow, ...]
    changes: tuple[DiffChange, ...]
    added_lines: int
    deleted_lines: int
    modified_lines: int
    elapsed_ms: float

    @property
    def identical(self) -> bool:
        return not self.changes

    @property
    def total_changes(self) -> int:
        return len(self.changes)


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_lines(text: str) -> tuple[str, ...]:
    normalized = _lf(text)
    return tuple(normalized.split("\n")) if normalized else ()


def _normalize(text: str, options: DiffOptions) -> str:
    if options.ignore_whitespace:
        text = "".join(char for char in text if not char.isspace())
    return text.casefold() if options.ignore_case else text


def _normalize_with_map(text: str, options: DiffOptions):
    characters = []
    positions = []
    for index, char in enumerate(text):
        if options.ignore_whitespace and char.isspace():
            continue
        normalized = char.casefold() if options.ignore_case else char
        characters.append(normalized)
        positions.extend([index] * len(normalized))
    return "".join(characters), positions


def _common_edges(left, right):
    prefix = 0
    limit = min(len(left), len(right))
    while prefix < limit and left[prefix] == right[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < limit - prefix and
           left[len(left) - 1 - suffix] == right[len(right) - 1 - suffix]):
        suffix += 1
    return prefix, suffix


def _opcodes(left, right, pair_limit: int, item_limit: int):
    prefix, suffix = _common_edges(left, right)
    left_end, right_end = len(left) - suffix, len(right) - suffix
    if prefix:
        yield "equal", 0, prefix, 0, prefix
    left_size, right_size = left_end - prefix, right_end - prefix
    if left_size or right_size:
        if not left_size:
            yield "insert", prefix, prefix, prefix, right_end
        elif not right_size:
            yield "delete", prefix, left_end, prefix, prefix
        elif (left_size * right_size > pair_limit or
              max(left_size, right_size) > item_limit):
            yield "replace", prefix, left_end, prefix, right_end
        else:
            matcher = SequenceMatcher(
                None, left[prefix:left_end], right[prefix:right_end], autojunk=False)
            for tag, a, b, c, d in matcher.get_opcodes():
                yield tag, a + prefix, b + prefix, c + prefix, d + prefix
    if suffix:
        yield "equal", left_end, len(left), right_end, len(right)


def _mapped_span(mapping, start, end):
    if start == end:
        return None
    return Span(mapping[start], mapping[end - 1] + 1)


def _merge_spans(spans):
    result = []
    for span in spans:
        if span is None:
            continue
        if result and span.start <= result[-1].end:
            result[-1] = Span(result[-1].start, max(result[-1].end, span.end))
        else:
            result.append(span)
    return tuple(result)


def _intraline(left: str, right: str, options: DiffOptions):
    a, a_map = _normalize_with_map(left, options)
    b, b_map = _normalize_with_map(right, options)
    left_spans, right_spans = [], []
    for tag, i, j, k, m in _opcodes(a, b, 1_000_000, 10_000):
        if tag != "equal":
            left_spans.append(_mapped_span(a_map, i, j))
            right_spans.append(_mapped_span(b_map, k, m))
    return _merge_spans(left_spans), _merge_spans(right_spans)


def _whole_line_span(line: str):
    return (Span(0, len(line)),) if line else ()


def compare_texts(left: str, right: str,
                  options: DiffOptions = DiffOptions()) -> DiffResult:
    started = perf_counter()
    left_lines, right_lines = split_lines(left), split_lines(right)
    left_keys = tuple(_normalize(line, options) for line in left_lines)
    right_keys = tuple(_normalize(line, options) for line in right_lines)
    rows, changes = [], []
    added = deleted = modified = 0
    for tag, a, b, c, d in _opcodes(left_keys, right_keys, 4_000_000, 20_000):
        start_row = len(rows)
        if tag == "equal":
            rows.extend(DiffRow(i, j, "equal")
                        for i, j in zip(range(a, b), range(c, d)))
            continue
        paired = min(b - a, d - c) if tag == "replace" else 0
        for offset in range(paired):
            i, j = a + offset, c + offset
            left_spans, right_spans = _intraline(left_lines[i], right_lines[j], options)
            rows.append(DiffRow(i, j, "replace", left_spans, right_spans))
        for i in range(a + paired, b):
            rows.append(DiffRow(i, None, "delete", _whole_line_span(left_lines[i])))
        for j in range(c + paired, d):
            rows.append(DiffRow(None, j, "insert", (), _whole_line_span(right_lines[j])))
        modified += paired
        deleted += b - a - paired
        added += d - c - paired
        changes.append(DiffChange(start_row, len(rows), tag, a, b, c, d))
    return DiffResult(left_lines, right_lines, tuple(rows), tuple(changes),
                      added, deleted, modified, (perf_counter() - started) * 1000)


def apply_change(result: DiffResult, change_index: int, target: str) -> str:
    """Copy a hunk into target ('left' or 'right'), preserving its raw lines."""
    if target not in ("left", "right"):
        raise ValueError("target must be 'left' or 'right'")
    if change_index < 0 or change_index >= len(result.changes):
        raise IndexError("change index out of range")
    change = result.changes[change_index]
    if target == "left":
        lines = list(result.left_lines)
        lines[change.left_start:change.left_end] = result.right_lines[
            change.right_start:change.right_end]
    else:
        lines = list(result.right_lines)
        lines[change.right_start:change.right_end] = result.left_lines[
            change.left_start:change.left_end]
    return "\n".join(lines)


def _patch_lines(text: str):
    parts = split_lines(text)
    if not parts:
        return []
    # A terminal empty source line represents the preceding newline; it is not
    # an additional physical line in a unified patch.
    return [line + "\n" for line in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def export_unified(left: str, right: str, left_name: str = "原始文本",
                   right_name: str = "修改文本", context: int = 3) -> str:
    """Export actual text differences, independent of ignore-view options."""
    if context < 0:
        raise ValueError("context must be non-negative")
    output = []
    for line in unified_diff(_patch_lines(left), _patch_lines(right),
                             fromfile=left_name, tofile=right_name,
                             n=context, lineterm="\n"):
        output.append(line)
        if not line.endswith("\n"):
            output.append("\n\\ No newline at end of file\n")
    return "".join(output)
