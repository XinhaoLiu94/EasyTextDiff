"""A compact navigation strip for already-computed aligned diff rows."""

from __future__ import annotations

from PyQt5.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QSizePolicy, QWidget


class DiffOverview(QWidget):
    """Paint changes and emit the aligned row clicked by the user.

    The result and its change list come from the diff engine; no text matching
    or hunk selection is performed in this view. Row ranges are end-exclusive.
    """

    activated = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = None
        self._row_count = 0
        self._current_change = -1
        self._visible_rows = None
        self._navigation_row = 0
        self._colors = {
            "bg": "#FFFFFF", "gutter_bg": "#F4F7F5", "border": "#DFE7E3",
            "accent": "#176F64", "green": "#66AE84", "red": "#DB9B8E",
        }
        self.setFixedWidth(18)
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("差异概览")
        self.setToolTip("点击跳转到对应行")
        self.setMouseTracking(True)

    def sizeHint(self):
        return QSize(18, 220)

    def set_result(self, result):
        self._result = result
        self._row_count = len(result.rows) if result is not None else 0
        self._current_change = -1
        self._visible_rows = None
        self._navigation_row = 0
        self.update()

    def set_current_change(self, index):
        count = len(self._result.changes) if self._result is not None else 0
        self._current_change = int(index) if index is not None and 0 <= index < count else -1
        self.update()

    def set_visible_rows(self, start, end):
        if start is None or end is None or end <= start or not self._row_count:
            self._visible_rows = None
        else:
            self._visible_rows = (max(0, min(int(start), self._row_count)),
                                  max(0, min(int(end), self._row_count)))
        self.update()

    def set_colors(self, colors):
        self._colors.update({key: value for key, value in colors.items() if key in self._colors})
        self.update()

    def _track(self):
        return QRectF(3, 5, max(1, self.width() - 6), max(1, self.height() - 10))

    def _row_at(self, y):
        track = self._track()
        fraction = max(0.0, min(1.0, (y - track.top()) / track.height()))
        return min(max(0, self._row_count - 1), int(fraction * self._row_count))

    def _range_rect(self, start, end, minimum_height=2):
        track = self._track()
        scale = track.height() / max(1, self._row_count)
        top = track.top() + start * scale
        height = max(minimum_height, (end - start) * scale)
        if top + height > track.bottom():
            top = max(track.top(), track.bottom() - height)
        return QRectF(track.left(), top, track.width(), min(height, track.height()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(self._colors["bg"]))
        track = self._track()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._colors["gutter_bg"]))
        painter.drawRoundedRect(track, 3, 3)
        if not self._result or not self._row_count:
            return
        if self._visible_rows:
            viewport = self._range_rect(*self._visible_rows, minimum_height=6)
            color = QColor(self._colors["accent"])
            color.setAlpha(25)
            painter.setBrush(color)
            painter.drawRoundedRect(viewport, 2, 2)
        for change in self._result.changes:
            rect = self._range_rect(change.start_row, change.end_row, minimum_height=3)
            if change.tag == "replace":
                painter.fillRect(QRectF(rect.left(), rect.top(), rect.width() / 2, rect.height()), QColor(self._colors["red"]))
                painter.fillRect(QRectF(rect.center().x(), rect.top(), rect.width() / 2, rect.height()), QColor(self._colors["green"]))
            else:
                painter.fillRect(rect, QColor(self._colors["green" if change.tag == "insert" else "red"]))
        if 0 <= self._current_change < len(self._result.changes):
            change = self._result.changes[self._current_change]
            rect = self._range_rect(change.start_row, change.end_row, minimum_height=5)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(self._colors["accent"]), 1.5))
            painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 2, 2)
        if self.hasFocus():
            painter.setPen(QPen(QColor(self._colors["accent"]), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(track.adjusted(-1, -1, 1, 1), 3, 3)

    def _activate_y(self, y):
        if self._row_count:
            self._navigation_row = self._row_at(y)
            self.activated.emit(self._navigation_row)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self._activate_y(event.pos().y())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._activate_y(event.pos().y())
            event.accept()
        else:
            if self._row_count:
                self.setToolTip(f"第 {self._row_at(event.pos().y()) + 1:,} 行 · 点击跳转")
            super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if not self._row_count:
            return super().keyPressEvent(event)
        step = (self._visible_rows[1] - self._visible_rows[0]) if self._visible_rows else 10
        targets = {
            Qt.Key_Up: self._navigation_row - 1,
            Qt.Key_Down: self._navigation_row + 1,
            Qt.Key_PageUp: self._navigation_row - max(1, step),
            Qt.Key_PageDown: self._navigation_row + max(1, step),
            Qt.Key_Home: 0, Qt.Key_End: self._row_count - 1,
        }
        if event.key() in targets:
            self._navigation_row = max(0, min(targets[event.key()], self._row_count - 1))
            self.activated.emit(self._navigation_row)
            event.accept()
        else:
            super().keyPressEvent(event)


Overview = DiffOverview
