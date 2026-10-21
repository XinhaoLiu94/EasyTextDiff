"""Native source editor with non-destructive diff decorations and row mapping."""

from __future__ import annotations

from collections.abc import Mapping
from bisect import bisect_left

from PyQt5.QtCore import QRect, QRectF, Qt, QTimer, QSignalBlocker, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QPalette,
    QPen,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
    QTextOption,
)
from PyQt5.QtWidgets import QFrame, QPlainTextEdit, QTextEdit, QWidget

from .highlighting import SyntaxHighlighter, canonical_language, detect_language


DEFAULT_COLORS = {
    "background": "#FFFFFF",
    "foreground": "#273248",
    "gutter_background": "#F8F9FC",
    "gutter_text": "#A0A8B8",
    "gutter_border": "#E8ECF3",
    "selection": "#D8E6FF",
    "selection_text": "#183B73",
    "current_line": "#F7F9FD",
    "delete_bg": "#FFF0ED",
    "insert_bg": "#EDF9F1",
    "delete_inline": "#FBC8BF",
    "insert_inline": "#BDEACB",
    "ghost_bg": "#F5F7FA",
    "accent": "#4979E8",
}


def _field(obj, name, default=None):
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


class _LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def sizeHint(self):
        from PyQt5.QtCore import QSize

        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor._paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    """Editable source whose diff decorations never change its document.

    Aligned rows belong to the comparison model. The document contains only
    original source lines, with native editing, selections, clipboard and undo.
    Cursor signals report one-based source line and Unicode column numbers.
    """

    fileDropped = pyqtSignal(str)
    cursorPositionReported = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors = dict(DEFAULT_COLORS)
        self._diff_mode = False
        self._side = "left"
        self._row_map = None
        self._source_to_aligned = {}
        self._legal_aligned_rows = ()
        self._row_kinds = ()
        self._row_spans = ()
        self._current_change = None
        self._font_size = 11
        self._line_number_area = _LineNumberArea(self)
        self._language_mode = "plain"
        self._language_path = ""
        self._syntax_highlighter = SyntaxHighlighter(self.document(), "plain", self._colors)
        self._language_timer = QTimer(self)
        self._language_timer.setSingleShot(True)
        self._language_timer.setInterval(180)
        self._language_timer.timeout.connect(self._refresh_language)

        self.setFrameShape(QFrame.NoFrame)
        self.setAcceptDrops(True)
        self.setCenterOnScroll(False)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.document().setDocumentMargin(16)

        families = set(QFontDatabase().families())
        family = next(
            (name for name in ("JetBrains Mono", "Consolas", "Cascadia Code", "DejaVu Sans Mono")
             if name in families),
            "Courier New",
        )
        self._font_family = family
        self.set_font_size(self._font_size)
        self.set_palette_colors({})

        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._cursor_changed)
        self.textChanged.connect(self._schedule_language)
        self._update_gutter_width()
        self._refresh_highlights()

    @property
    def is_diff_view(self):
        return self._diff_mode

    @property
    def has_diff(self):
        return self._diff_mode

    @property
    def language(self):
        return self._syntax_highlighter.language

    def set_language(self, language="auto", filename=None):
        """Use a manual language, a filename, or Auto with optional filename."""
        value = str(language or "auto").strip()
        manual = canonical_language(value)
        self._language_mode = manual if manual is not None else "auto"
        self._language_path = str(filename or "") if value.lower() == "auto" else ""
        if manual is None and value.lower() != "auto":
            self._language_path = value
        self._language_timer.stop()
        self._refresh_language()

    def _schedule_language(self):
        if self._language_mode == "auto":
            self._language_timer.start()

    def _refresh_language(self):
        language = self._language_mode
        if language == "auto":
            # Inspect at most 8 Ki UTF-16 units instead of copying a large document.
            cursor = QTextCursor(self.document())
            cursor.setPosition(0)
            cursor.setPosition(min(8192, self.document().characterCount() - 1), QTextCursor.KeepAnchor)
            language = detect_language(self._language_path, cursor.selectedText().replace("\u2029", "\n"))
        # Qt emits textChanged for a rehighlight although source text is unchanged.
        blocker = QSignalBlocker(self)
        try:
            self._syntax_highlighter.set_language(language)
        finally:
            del blocker

    def line_number_area_width(self):
        highest_line = self.blockCount()
        digits = len(str(max(1, highest_line)))
        return max(44, 24 + self.fontMetrics().horizontalAdvance("9") * digits)

    def _update_gutter_width(self, *_):
        width = self.line_number_area_width()
        self.setViewportMargins(width, 0, 0, 0)
        rect = self.contentsRect()
        self._line_number_area.setGeometry(rect.left(), rect.top(), width, rect.height())

    def _update_gutter(self, rect, dy):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(rect.left(), rect.top(), self.line_number_area_width(), rect.height())
        )

    def _paint_line_numbers(self, event):
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(self._colors["gutter_background"]))
        painter.setPen(QColor(self._colors["gutter_border"]))
        painter.drawLine(self._line_number_area.width() - 1, event.rect().top(),
                         self._line_number_area.width() - 1, event.rect().bottom())
        painter.setFont(self.font())
        block = self.firstVisibleBlock()
        row = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        active_row = self.textCursor().blockNumber()
        marker = self._source_change_marker()
        while block.isValid() and top <= event.rect().bottom():
            height = self.blockBoundingRect(block).height()
            if block.isVisible() and top + height >= event.rect().top():
                if marker and marker[0] == "range" and marker[1] <= row < marker[2]:
                    painter.fillRect(QRectF(0, top, 3, height), QColor(self._colors["accent"]))
                number = row + 1
                if number is not None:
                    color = self._colors["foreground"] if row == active_row else self._colors["gutter_text"]
                    painter.setPen(QColor(color))
                    # Wrapped text has only one line number, alongside its first visual line.
                    painter.drawText(QRectF(4, top, self._line_number_area.width() - 16,
                                             self.fontMetrics().height()),
                                     Qt.AlignRight | Qt.AlignVCenter, str(number))
            top += height
            block = block.next()
            row += 1
        if marker and marker[0] == "boundary":
            y = self._boundary_y(marker[1])
            painter.setPen(QPen(QColor(self._colors["accent"]), 2))
            painter.drawLine(1, round(y), self._line_number_area.width() - 2, round(y))

    def _cursor_changed(self):
        cursor = self.textCursor()
        row = cursor.blockNumber()
        prefix = cursor.block().text().encode("utf-16-le")[:cursor.positionInBlock() * 2]
        column = len(prefix.decode("utf-16-le", errors="ignore")) + 1
        self.cursorPositionReported.emit(row + 1, column)
        self._line_number_area.update()
        # Keep static diff selections installed while navigating large sources.
        if not self._diff_mode:
            self._refresh_highlights()

    def set_diff_rows(self, rows, side: str, source_lines=None):
        """Decorate existing source; source_lines is accepted for compatibility.

        No placeholder lines, source replacement, undo reset or cursor movement
        occurs. The caller guarantees the result describes the current source.
        """
        if side not in ("left", "right"):
            raise ValueError("side must be 'left' or 'right'")
        rows = tuple(rows)
        mapping = tuple(_field(row, side + "_index") for row in rows)
        self._diff_mode = True
        self._side = side
        self._row_map = mapping
        self._source_to_aligned = {source: row for row, source in enumerate(mapping) if source is not None}
        self._legal_aligned_rows = tuple(row for row, source in enumerate(mapping) if source is not None)
        self._row_kinds = tuple(_field(row, "kind", "equal") for row in rows)
        self._row_spans = tuple(_field(row, side + "_spans", ()) for row in rows)
        self._current_change = None
        self.setReadOnly(False)
        self._refresh_highlights()
        self.viewport().update()

    def clear_diff(self):
        """Remove diff decorations without touching source or editor state."""
        self._diff_mode = False
        self._row_map = None
        self._source_to_aligned = {}
        self._legal_aligned_rows = ()
        self._row_kinds = ()
        self._row_spans = ()
        self._current_change = None
        self._refresh_highlights()
        self.viewport().update()

    def aligned_row_for_source(self, source_row: int):
        source_row = max(0, min(int(source_row), self.blockCount() - 1))
        return self._source_to_aligned.get(source_row, source_row)

    def source_row_for_aligned(self, aligned_row: int):
        """Map missing rows to the nearest real source line; ties choose next."""
        if not self._row_map:
            return max(0, min(int(aligned_row), self.blockCount() - 1))
        aligned_row = max(0, min(int(aligned_row), len(self._row_map) - 1))
        source = self._row_map[aligned_row]
        if source is None:
            if not self._legal_aligned_rows:
                return 0
            insertion = bisect_left(self._legal_aligned_rows, aligned_row)
            candidates = self._legal_aligned_rows[max(0, insertion - 1):insertion + 1]
            closest = min(candidates, key=lambda row: (abs(row - aligned_row), -row))
            source = self._row_map[closest]
        return max(0, min(int(source), self.blockCount() - 1))

    def _source_change_marker(self):
        if self._current_change is None or not self._row_map:
            return None
        start, end = self._current_change
        start, end = max(0, start), min(len(self._row_map), end)
        sources = [source for source in self._row_map[start:end] if source is not None]
        if sources:
            return ("range", max(0, min(sources)), min(self.blockCount(), max(sources) + 1))
        # An insertion into this side has no source block: mark its boundary.
        following = next((source for source in self._row_map[end:] if source is not None), None)
        if following is not None:
            return ("boundary", min(following, self.blockCount()), None)
        previous = next((source for source in reversed(self._row_map[:start]) if source is not None), None)
        boundary = previous + 1 if previous is not None else 0
        return ("boundary", min(boundary, self.blockCount()), None)

    def _boundary_y(self, source_boundary):
        if source_boundary < self.blockCount():
            block = self.document().findBlockByNumber(max(0, source_boundary))
            return self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        block = self.document().lastBlock()
        rect = self.blockBoundingGeometry(block).translated(self.contentOffset())
        return rect.top() + self.blockBoundingRect(block).height()

    def _selection(self, block, color, start=None, end=None):
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(block)
        selection.format = QTextCharFormat()
        selection.format.setBackground(QColor(color))
        if start is None:
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor.clearSelection()
        else:
            text = block.text()
            start = max(0, min(int(start), len(text)))
            end = max(start, min(int(end), len(text)))
            selection.cursor.setPosition(block.position() + _utf16_length(text[:start]))
            selection.cursor.setPosition(block.position() + _utf16_length(text[:end]), QTextCursor.KeepAnchor)
        return selection

    def _refresh_highlights(self):
        selections = []
        if not self.isReadOnly() and not self._diff_mode:
            selections.append(self._selection(self.textCursor().block(), self._colors["current_line"]))
        if self._diff_mode:
            for row, kind in enumerate(self._row_kinds):
                source = self._row_map[row]
                if source is None:
                    continue
                block = self.document().findBlockByNumber(source)
                if not block.isValid():
                    continue
                color = None
                if (self._side == "left" and kind in ("delete", "replace")):
                    color = self._colors["delete_bg"]
                elif (self._side == "right" and kind in ("insert", "replace")):
                    color = self._colors["insert_bg"]
                if color:
                    selections.append(self._selection(block, color))
                inline_color = self._colors["delete_inline" if self._side == "left" else "insert_inline"]
                for span in self._row_spans[row]:
                    if hasattr(span, "start"):
                        start, end = span.start, span.end
                    else:
                        start, end = span
                    if end > start:
                        selections.append(self._selection(block, inline_color, start, end))
        self.setExtraSelections(selections)
        self._line_number_area.update()

    def set_current_change(self, start_row: int, end_row: int):
        """Mark a hunk; end_row is exclusive. Negative/empty ranges clear it."""
        if start_row is None or end_row is None or start_row < 0 or end_row <= start_row:
            self._current_change = None
        else:
            self._current_change = (int(start_row), int(end_row))
        self.viewport().update()
        self._line_number_area.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._current_change:
            return
        marker = self._source_change_marker()
        if marker is None:
            return
        if marker[0] == "boundary":
            painter = QPainter(self.viewport())
            color = QColor(self._colors["accent"])
            color.setAlpha(170)
            painter.setPen(QPen(color, 1.5))
            y = self._boundary_y(marker[1])
            painter.drawLine(3, round(y), self.viewport().width() - 3, round(y))
            return
        _, start, end = marker
        first = self.document().findBlockByNumber(start)
        last = self.document().findBlockByNumber(min(end - 1, self.blockCount() - 1))
        if not first.isValid() or not last.isValid():
            return
        top = self.blockBoundingGeometry(first).translated(self.contentOffset()).top()
        bottom = (self.blockBoundingGeometry(last).translated(self.contentOffset()).top()
                  + self.blockBoundingRect(last).height())
        if bottom < 0 or top > self.viewport().height():
            return
        painter = QPainter(self.viewport())
        color = QColor(self._colors["accent"])
        color.setAlpha(130)
        painter.setPen(QPen(color, 1))
        painter.setBrush(Qt.NoBrush)
        painter.setRenderHint(QPainter.Antialiasing)
        top = max(0.5, top + 0.5)
        bottom = min(self.viewport().height() - 0.5, bottom - 0.5)
        painter.drawRoundedRect(QRectF(2.5, top, max(0, self.viewport().width() - 5),
                                      max(0, bottom - top)), 3, 3)

    def scroll_to_row(self, row: int, center: bool = True):
        row = self.source_row_for_aligned(row)
        block = self.document().findBlockByNumber(row)
        if block.isValid():
            self.setTextCursor(QTextCursor(block))
            if center:
                self.centerCursor()
            else:
                self.ensureCursorVisible()

    def set_wrap(self, enabled: bool):
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth if enabled else QPlainTextEdit.NoWrap)

    def set_font_size(self, size: int):
        """Set the monospaced font size in points."""
        self._font_size = max(8, min(28, int(size)))
        font = QFont(getattr(self, "_font_family", "Consolas"))
        font.setPointSize(self._font_size)
        font.setStyleHint(QFont.Monospace)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        if hasattr(self, "_line_number_area"):
            self._update_gutter_width()
            self._line_number_area.update()

    def set_palette_colors(self, colors: dict):
        aliases = {
            "bg": "background", "text": "foreground", "muted": "gutter_text",
            "gutter_bg": "gutter_background", "border": "gutter_border",
            "added_bg": "insert_bg", "deleted_bg": "delete_bg",
            "added_inline": "insert_inline", "deleted_inline": "delete_inline",
            "placeholder_bg": "ghost_bg",
        }
        for key, value in colors.items():
            target = aliases.get(key, key)
            if target in DEFAULT_COLORS:
                self._colors[target] = value
        background = QColor(self._colors["background"])
        if "current_line" not in colors:
            self._colors["current_line"] = (
                background.lighter(115) if background.lightness() < 128 else background.darker(102)
            ).name()
        if "selection_text" not in colors:
            self._colors["selection_text"] = self._colors["foreground"]
        palette = self.palette()
        palette.setColor(QPalette.Base, QColor(self._colors["background"]))
        palette.setColor(QPalette.Text, QColor(self._colors["foreground"]))
        palette.setColor(QPalette.Highlight, QColor(self._colors["selection"]))
        palette.setColor(QPalette.HighlightedText, QColor(self._colors["selection_text"]))
        self.setPalette(palette)
        blocker = QSignalBlocker(self)
        try:
            self._syntax_highlighter.set_colors({**self._colors, **colors})
        finally:
            del blocker
        self._refresh_highlights()
        self.viewport().update()

    @staticmethod
    def _dropped_file(event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    return url.toLocalFile()
        return None

    def dragEnterEvent(self, event):
        if self._dropped_file(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._dropped_file(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        path = self._dropped_file(event)
        if path:
            self.fileDropped.emit(path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
