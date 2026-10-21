"""Document state shared by presenters and file services; no Qt dependency."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Newline(str, Enum):
    LF = "\n"
    CRLF = "\r\n"
    CR = "\r"


def canonical_text(text: str) -> str:
    """Use LF internally, independently of the on-disk newline convention."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


@dataclass
class DocumentModel:
    text: str = ""
    path: Path | None = None
    encoding: str = "utf-8"
    newline: Newline = Newline.LF
    bom: bytes = b""
    mixed_newlines: bool = False
    newline_counts: dict[str, int] = field(default_factory=dict)
    _saved_text: str = field(init=False, repr=False)
    _saved_format: tuple[str, str, bytes] = field(init=False, repr=False)
    _original_bytes: bytes | None = field(default=None, init=False, repr=False)

    def __setattr__(self, name: str, value: object) -> None:
        if name == "text":
            if not isinstance(value, str):
                raise TypeError("Document text must be a string.")
            value = canonical_text(value)
        object.__setattr__(self, name, value)

    def __post_init__(self) -> None:
        if self.path is not None:
            self.path = Path(self.path)
        self.newline = Newline(self.newline)
        self.mark_saved()

    @property
    def modified(self) -> bool:
        return self.text != self._saved_text or self._format != self._saved_format

    @property
    def _format(self) -> tuple[str, str, bytes]:
        return self.encoding, str(self.newline.value if isinstance(self.newline, Newline)
                                  else self.newline), self.bom

    @property
    def display_name(self) -> str:
        return self.path.name if self.path is not None else "未命名"

    @property
    def format_label(self) -> str:
        labels = {"utf-8": "UTF-8", "utf-16-le": "UTF-16 LE",
                  "utf-16-be": "UTF-16 BE", "gb18030": "GB18030"}
        encoding_label = labels.get(self.encoding, self.encoding.upper())
        if self.bom:
            encoding_label += " BOM"
        return f"{encoding_label} · {Newline(self.newline).name}"

    def mark_saved(self, *, original_bytes: bytes | None = None) -> None:
        """Record the successful load/save baseline, including format choices."""
        self._saved_text = self.text
        self._saved_format = self._format
        self._original_bytes = original_bytes


@dataclass
class ComparisonModel:
    left: DocumentModel = field(default_factory=DocumentModel)
    right: DocumentModel = field(default_factory=DocumentModel)

    @property
    def display_title(self) -> str:
        return f"{self.left.display_name} ↔ {self.right.display_name}"
