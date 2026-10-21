"""Lightweight, foreground-only code highlighting for the comparison editors.

This is a tolerant lexical highlighter, not a compiler or a JSON validator.
Token positions are converted from Python codepoints to Qt UTF-16 positions.
"""

from __future__ import annotations

import keyword
from pathlib import PurePosixPath
import re

from PyQt5.QtGui import QColor, QSyntaxHighlighter, QTextBlockUserData, QTextCharFormat


LANGUAGES = ("plain", "verilog", "cpp", "python", "json")
LANGUAGE_LABELS = {
    "plain": "纯文本", "verilog": "Verilog / SystemVerilog",
    "cpp": "C / C++", "python": "Python", "json": "JSON",
}
_ALIASES = {
    "text": "plain", "plaintext": "plain", "plain text": "plain", "txt": "plain",
    "c": "cpp", "c++": "cpp", "c/c++": "cpp", "cc": "cpp", "cxx": "cpp",
    "systemverilog": "verilog", "system verilog": "verilog", "sv": "verilog",
    "v": "verilog", "verilog/systemverilog": "verilog", "py": "python",
}
_EXTENSIONS = {
    ".v": "verilog", ".vh": "verilog", ".sv": "verilog", ".svh": "verilog",
    ".c": "cpp", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".c++": "cpp",
    ".h": "cpp", ".hh": "cpp", ".hpp": "cpp", ".hxx": "cpp", ".ino": "cpp",
    ".py": "python", ".pyw": "python", ".pyi": "python", ".json": "json",
}


def canonical_language(value: str | None) -> str | None:
    """Resolve manual language labels; return None for a filename or Auto."""
    value = str(value or "").strip().lower()
    if value in LANGUAGES:
        return value
    return _ALIASES.get(value, _ALIASES.get(value.replace(" ", "")))


def detect_language(path: str = "", text: str = "") -> str:
    """Prefer a known filename extension, then cautiously inspect pasted code.

    Unknown explicit extensions remain plain text. Content heuristics are used
    for paste input, extensionless files and .txt snippets, and never execute it.
    """
    path = str(path or "").strip()
    manual = canonical_language(path)
    if manual is not None:
        return manual
    suffix = PurePosixPath(path.replace("\\", "/")).suffix.lower()
    if suffix in _EXTENSIONS:
        return _EXTENSIONS[suffix]
    if suffix and suffix != ".txt":
        return "plain"
    sample = text[:8192].lstrip("\ufeff \t\r\n")
    if not sample:
        return "plain"
    if re.search(r"(?m)^\s*(?:module\s+[\w$]+\s*(?:#\s*\(|\(|;)|endmodule\b|"
                 r"always_(?:ff|comb|latch)\b|always\s*@|assign\s+[\w$]+(?:\[[^\]]+\])?\s*=)", sample):
        return "verilog"
    if re.search(r"(?m)^\s*(?:#\s*(?:include|define|pragma)\b|"
                 r"(?:int|void|float|double|uint\d+_t)\s+\w+\s*\([^;\n]*\)\s*\{)", sample):
        return "cpp"
    if (re.match(r"#![^\n]*\bpython", sample) or
            re.search(r"(?m)^\s*(?:(?:async\s+)?def\s+\w+\s*\(|class\s+\w+\s*[:(]|"
                      r"from\s+[\w.]+\s+import\b|import\s+[\w.]|print\s*\()", sample)):
        return "python"
    if (sample.startswith(("{", "[")) and
            re.search(r'"(?:[^"\\]|\\.)*"\s*:|\b(?:true|false|null)\b|^\[\s*(?:\d|["\[{])', sample)):
        return "json"
    return "plain"


_CPP_KEYWORDS = set("""
alignas alignof and and_eq asm auto bitand bitor break case catch class co_await
co_return co_yield compl concept const consteval constexpr constinit const_cast
continue decltype default delete do dynamic_cast else enum explicit export extern
false for friend goto if inline mutable namespace new noexcept not not_eq nullptr
operator or or_eq private protected public register reinterpret_cast requires
return sizeof static static_assert static_cast struct switch template this
thread_local throw true try typedef typeid typename union using virtual volatile
while xor xor_eq override final restrict
""".split())
_CPP_TYPES = set("""
bool char char8_t char16_t char32_t double float int long short signed unsigned void
wchar_t size_t ssize_t uint8_t uint16_t uint32_t uint64_t int8_t int16_t int32_t
int64_t ap_uint ap_int ap_fixed ap_ufixed string vector array stream
""".split())
_VERILOG_KEYWORDS = set("""
accept_on alias always always_comb always_ff always_latch and assert assign assume
automatic before begin bind bins binsof break buf bufif0 bufif1 case casex casez
cell chandle checker class clocking config const constraint context continue cover
covergroup coverpoint cross deassign default defparam design disable dist do edge
else end endcase endchecker endclass endclocking endconfig endfunction endgenerate
endgroup endinterface endmodule endpackage endprimitive endprogram endproperty
endsequence endspecify endtable endtask enum event eventually expect export extends
extern final first_match for force foreach forever fork forkjoin function generate
genvar global highz0 highz1 if iff ifnone ignore_bins illegal_bins implements implies
import incdir include initial inout input inside instance int integer interconnect
interface intersect join join_any join_none large let liblist library local
localparam macromodule matches medium modport module nand negedge nettype new nexttime
nmos nor noshowcancelled not notif0 notif1 null or output package packed parameter
pmos posedge primitive priority program property protected pull0 pull1 pulldown
pullup pulsestyle_ondetect pulsestyle_onevent pure rand randc randcase randsequence
rcmos ref reject_on release repeat restrict return rnmos rpmos rtran rtranif0
rtranif1 s_always s_eventually s_nexttime s_until s_until_with scalared sequence
showcancelled signed small soft solve specify specparam static strong strong0
strong1 struct super supply0 supply1 sync_accept_on sync_reject_on table tagged
task this throughout timeprecision timeunit tran tranif0 tranif1 tri tri0 tri1 triand
trior trireg type typedef union unique unique0 unsigned use uwire var vectored
virtual wait wait_order wand weak weak0 weak1 while wildcard wire with within wor
xnor xor
""".split())
_VERILOG_TYPES = set("""
bit byte shortint int longint integer logic reg wire real realtime shortreal
string time void
""".split())
_PYTHON_KEYWORDS = set(keyword.kwlist) | set(getattr(keyword, "softkwlist", ()))
_PYTHON_BUILTINS = set("""
abs all any ascii bin bool bytearray bytes callable chr classmethod complex dict
dir divmod enumerate eval filter float format frozenset getattr globals hasattr
hash help hex id input int isinstance issubclass iter len list locals map max
memoryview min next object oct open ord pow print property range repr reversed
round set setattr slice sorted staticmethod str sum super tuple type vars zip
Exception ValueError TypeError RuntimeError KeyError IndexError StopIteration
NotImplementedError self cls
""".split())

_WORDS = re.compile(r"(?<![\w$])(?:\$[A-Za-z_]\w*|[^\W\d]\w*)", re.UNICODE)
_NUMBERS = re.compile(
    r"(?<![\w$])(?:0[xX][\da-fA-F](?:[\da-fA-F_']*)|0[bB][01](?:[01_']*)|"
    r"0[oO][0-7](?:[0-7_']*)|(?:\d[\d_']*(?:\.[\d_']*)?|\.\d[\d_']*)"
    r"(?:[eE][+-]?\d[\d_]*)?)[uUlLfFjJ]*"
)
_VERILOG_NUMBERS = re.compile(r"(?<![\w$])(?:(?:\d[\d_]*\s*)?'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|'[01xXzZ])")
_RAW_OPEN = re.compile(r'R"([^\s()\\]{0,16})\(')
_CALL = re.compile(r"\s*\(")

LIGHT_SYNTAX = {
    "keyword": "#7851A4", "type": "#23718C", "string": "#437C3E",
    "comment": "#7D9085", "number": "#A46929", "builtin": "#247C83",
    "function": "#346BA0", "preprocessor": "#926B36", "key": "#247C83",
}
DARK_SYNTAX = {
    "keyword": "#C4A0E8", "type": "#83C5D4", "string": "#B0CB9A",
    "comment": "#849C90", "number": "#E3B186", "builtin": "#87C9CC",
    "function": "#90BDF0", "preprocessor": "#DCC18F", "key": "#89CCD5",
}


class _RawStringData(QTextBlockUserData):
    def __init__(self, closer):
        super().__init__()
        self.closer = closer


class SyntaxHighlighter(QSyntaxHighlighter):
    """Highlight lexical tokens without setting background, weight or font."""

    BLOCK_COMMENT = 1
    PY_SINGLE_TRIPLE = 2
    PY_DOUBLE_TRIPLE = 3
    CONTINUED_DOUBLE = 4
    CONTINUED_SINGLE = 5
    CPP_RAW_STRING = 6

    def __init__(self, document, language="plain", colors=None):
        super().__init__(document)
        self.language = canonical_language(language) or detect_language(language)
        self.formats = {}
        self.set_colors(colors or {})

    def set_language(self, language):
        resolved = canonical_language(language) or detect_language(language)
        if resolved != self.language:
            self.language = resolved
            self.rehighlight()

    def set_colors(self, colors):
        background = QColor(colors.get("bg", colors.get("background", "#FFFFFF")))
        defaults = DARK_SYNTAX if background.lightness() < 128 else LIGHT_SYNTAX
        self.formats = {}
        for name, fallback in defaults.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colors.get("syntax_" + name, fallback)))
            self.formats[name] = fmt
        self.rehighlight()

    @staticmethod
    def _closing(text, delimiter, start):
        """Find a delimiter that is not preceded by an odd escape sequence."""
        index = text.find(delimiter, start)
        while index >= 0:
            slash = index - 1
            while slash >= 0 and text[slash] == "\\":
                slash -= 1
            if (index - slash - 1) % 2 == 0:
                return index
            index = text.find(delimiter, index + 1)
        return -1

    @staticmethod
    def _continued(text):
        return (len(text) - len(text.rstrip("\\"))) % 2 == 1

    def highlightBlock(self, text):
        self.setCurrentBlockState(0)
        if self.language == "plain":
            return
        offsets = None
        if any(ord(char) > 0xFFFF for char in text):
            offsets = [0]
            for char in text:
                offsets.append(offsets[-1] + (2 if ord(char) > 0xFFFF else 1))

        def paint(start, end, role):
            if end <= start:
                return
            lo, hi = (offsets[start], offsets[end]) if offsets else (start, end)
            self.setFormat(lo, hi - lo, self.formats[role])

        for match in _NUMBERS.finditer(text):
            paint(match.start(), match.end(), "number")
        if self.language == "verilog":
            for match in _VERILOG_NUMBERS.finditer(text):
                paint(match.start(), match.end(), "number")
        for match in _WORDS.finditer(text):
            word = match.group()
            role = None
            if self.language == "cpp":
                if word in _CPP_KEYWORDS:
                    role = "keyword"
                elif word in _CPP_TYPES or word.endswith("_t"):
                    role = "type"
                elif _CALL.match(text, match.end()):
                    role = "function"
            elif self.language == "verilog":
                if word in _VERILOG_TYPES:
                    role = "type"
                elif word in _VERILOG_KEYWORDS:
                    role = "keyword"
                elif word.startswith("$"):
                    role = "builtin"
            elif self.language == "python":
                if word in _PYTHON_KEYWORDS:
                    role = "keyword"
                elif word in _PYTHON_BUILTINS:
                    role = "builtin"
                elif _CALL.match(text, match.end()):
                    role = "function"
            elif self.language == "json" and word in {"true", "false", "null"}:
                role = "keyword"
            if role:
                paint(match.start(), match.end(), role)
        if self.language == "cpp":
            directive = re.match(r"\s*#\s*\w+", text)
            if directive:
                paint(directive.start(), directive.end(), "preprocessor")
        elif self.language == "verilog":
            for directive in re.finditer(r"`[A-Za-z_]\w*", text):
                paint(directive.start(), directive.end(), "preprocessor")
        elif self.language == "python":
            for decorator in re.finditer(r"@[\w.]+", text):
                paint(decorator.start(), decorator.end(), "preprocessor")

        state = self.previousBlockState()
        index = 0
        if state == self.BLOCK_COMMENT and self.language in ("cpp", "verilog"):
            end = text.find("*/")
            paint(0, len(text) if end < 0 else end + 2, "comment")
            if end < 0:
                self.setCurrentBlockState(self.BLOCK_COMMENT)
                return
            index = end + 2
        elif state in (self.PY_SINGLE_TRIPLE, self.PY_DOUBLE_TRIPLE) and self.language == "python":
            delimiter = "'''" if state == self.PY_SINGLE_TRIPLE else '"""'
            end = self._closing(text, delimiter, 0)
            paint(0, len(text) if end < 0 else end + 3, "string")
            if end < 0:
                self.setCurrentBlockState(state)
                return
            index = end + 3
        elif state == self.CPP_RAW_STRING and self.language == "cpp":
            data = self.currentBlock().previous().userData()
            closer = data.closer if isinstance(data, _RawStringData) else ')"'
            end = text.find(closer)
            paint(0, len(text) if end < 0 else end + len(closer), "string")
            if end < 0:
                self.currentBlock().setUserData(_RawStringData(closer))
                self.setCurrentBlockState(state)
                return
            index = end + len(closer)
        elif state in (self.CONTINUED_DOUBLE, self.CONTINUED_SINGLE) and self.language != "json":
            delimiter = '"' if state == self.CONTINUED_DOUBLE else "'"
            end = self._closing(text, delimiter, 0)
            paint(0, len(text) if end < 0 else end + 1, "string")
            if end < 0:
                if self._continued(text):
                    self.setCurrentBlockState(state)
                return
            index = end + 1

        while index < len(text):
            if self.language in ("cpp", "verilog") and text.startswith("//", index):
                paint(index, len(text), "comment")
                break
            if self.language in ("cpp", "verilog") and text.startswith("/*", index):
                end = text.find("*/", index + 2)
                paint(index, len(text) if end < 0 else end + 2, "comment")
                if end < 0:
                    self.setCurrentBlockState(self.BLOCK_COMMENT)
                    break
                index = end + 2
                continue
            if self.language == "python" and text[index] == "#":
                paint(index, len(text), "comment")
                break
            if self.language == "cpp":
                raw = _RAW_OPEN.match(text, index)
                if raw:
                    closer = ")" + raw.group(1) + '"'
                    end = text.find(closer, raw.end())
                    paint(index, len(text) if end < 0 else end + len(closer), "string")
                    if end < 0:
                        self.currentBlock().setUserData(_RawStringData(closer))
                        self.setCurrentBlockState(self.CPP_RAW_STRING)
                        break
                    index = end + len(closer)
                    continue
            if self.language == "python" and text[index:index + 3] in ("'''", '"""'):
                delimiter = text[index:index + 3]
                end = self._closing(text, delimiter, index + 3)
                paint(index, len(text) if end < 0 else end + 3, "string")
                if end < 0:
                    self.setCurrentBlockState(self.PY_SINGLE_TRIPLE if delimiter == "'''" else self.PY_DOUBLE_TRIPLE)
                    break
                index = end + 3
                continue
            quotes = '"' if self.language in ("verilog", "json") else "\"'"
            if text[index] in quotes:
                delimiter = text[index]
                end = self._closing(text, delimiter, index + 1)
                role = "key" if self.language == "json" and end >= 0 and text[end + 1:].lstrip().startswith(":") else "string"
                paint(index, len(text) if end < 0 else end + 1, role)
                if end < 0:
                    if self.language != "json" and self._continued(text):
                        self.setCurrentBlockState(self.CONTINUED_DOUBLE if delimiter == '"' else self.CONTINUED_SINGLE)
                    break
                index = end + 1
                continue
            index += 1


CodeHighlighter = SyntaxHighlighter
