from pathlib import Path

from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)

from .editor import CodeEditor
from .icons import icon


def tool_button(name, tooltip, callback=None, parent=None):
    button = QToolButton(parent)
    button.setProperty('icon_name', name)
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setFixedSize(30, 30)
    if callback:
        button.clicked.connect(callback)
    return button


class TextPane(QFrame):
    importRequested = pyqtSignal()
    textChanged = pyqtSignal()
    notice = pyqtSignal(str)
    fileDropped = pyqtSignal(str)
    languageChanged = pyqtSignal(str)
    saveRequested = pyqtSignal()

    def __init__(self, side, parent=None):
        super().__init__(parent)
        self.setObjectName('card')
        self.side = side
        self.title = '原始文本' if side == 'left' else '修改文本'
        self.filename = ''
        self.encoding = '纯文本'
        self._colors = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName('paneHeader')
        header.setFixedHeight(58)
        row = QHBoxLayout(header)
        row.setContentsMargins(17, 0, 11, 0)
        row.setSpacing(10)
        self.badge = QLabel('A' if side == 'left' else 'B')
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedSize(27, 27)
        row.addWidget(self.badge)
        title_column = QVBoxLayout()
        title_column.setSpacing(1)
        self.title_label = QLabel(self.title)
        self.title_label.setFont(QFont('Microsoft YaHei UI', 10, QFont.DemiBold))
        self.file_label = QLabel('粘贴输入')
        self.file_label.setTextFormat(Qt.PlainText)
        self.file_label.setObjectName('subtitle')
        self.file_label.setMaximumWidth(210)
        self.file_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        title_column.addWidget(self.title_label)
        title_column.addWidget(self.file_label)
        row.addLayout(title_column, 1)
        self.paste_button = tool_button('paste', '粘贴剪贴板文字', self.paste_text)
        self.import_button = tool_button('file', '导入文本文件', self.importRequested.emit)
        self.copy_button = tool_button('copy', '复制完整文本', self.copy_text)
        self.save_button = tool_button('download', '保存这一侧  Ctrl+S', self.saveRequested.emit)
        self.clear_button = tool_button('clear', '清空这一侧', self.clear_text)
        self.buttons = [self.paste_button, self.import_button, self.save_button, self.copy_button, self.clear_button]
        for button in self.buttons:
            row.addWidget(button)
        layout.addWidget(header)

        self.editor = CodeEditor()
        self.editor.setAccessibleName(f'{self.title}输入框')
        self.editor.set_font_size(12)
        self.editor.document().setDocumentMargin(16)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(' ') * 4)
        # Equal viewport heights keep corresponding regions level when only one
        # document contains a line wide enough to require horizontal scrolling.
        self.editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        layout.addWidget(self.editor, 1)

        self.empty = QFrame(self.editor.viewport())
        self.empty.setObjectName('emptyPrompt')
        self.empty.setFixedSize(310, 212)
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(10)
        self.empty_icon = QLabel()
        self.empty_icon.setFixedSize(56, 56)
        self.empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_icon, 0, Qt.AlignHCenter)
        self.empty_title = QLabel(f'粘贴{self.title}')
        self.empty_title.setFont(QFont('Microsoft YaHei UI', 13, QFont.DemiBold))
        self.empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        help_label = QLabel('点击空白处输入，或拖入一个文本文件')
        help_label.setObjectName('subtitle')
        help_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(help_label)
        self.empty_button = QPushButton('  从剪贴板粘贴')
        self.empty_button.setCursor(Qt.PointingHandCursor)
        self.empty_button.clicked.connect(self.paste_text)
        self.empty_button.setFixedWidth(176)
        empty_layout.addWidget(self.empty_button, 0, Qt.AlignHCenter)
        keyboard = QLabel('Ctrl + V')
        keyboard.setObjectName('subtitle')
        keyboard.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(keyboard)
        for label in (self.empty_icon, self.empty_title, help_label, keyboard):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.empty.installEventFilter(self)
        self.editor.installEventFilter(self)
        self.editor.viewport().installEventFilter(self)

        footer = QFrame()
        footer.setObjectName('paneFooter')
        footer.setFixedHeight(34)
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(16, 0, 16, 0)
        self.count_label = QLabel('0 行 · 0 字符')
        self.count_label.setObjectName('subtitle')
        self.position_label = QLabel('纯文本')
        self.position_label.setObjectName('subtitle')
        self.language_combo = QComboBox()
        self.language_combo.setAccessibleName(f'{self.title}代码语言')
        self.language_combo.setToolTip('代码语法高亮语言；自动模式根据文件名或内容判断')
        for name, value in [('自动', 'auto'), ('纯文本', 'plain'), ('Verilog / SV', 'verilog'),
                            ('C / C++', 'cpp'), ('Python', 'python'), ('JSON', 'json')]:
            self.language_combo.addItem(name, value)
        self.language_combo.setFixedWidth(104)
        self.language_combo.currentIndexChanged.connect(
            lambda: self.languageChanged.emit(self.language_combo.currentData()))
        foot.addWidget(self.count_label)
        foot.addStretch()
        foot.addWidget(self.position_label)
        foot.addSpacing(8)
        foot.addWidget(self.language_combo)
        layout.addWidget(footer)

        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.cursorPositionReported.connect(self._cursor_changed)
        self.editor.fileDropped.connect(self.fileDropped)
        self.update_empty()

    def eventFilter(self, obj, event):
        if obj is self.editor.viewport() and event.type() == QEvent.Resize:
            self._position_empty()
        if obj is self.editor and event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            QTimer.singleShot(0, self.update_empty)
        if obj is self.empty and event.type() == QEvent.MouseButtonPress:
            self.editor.setFocus()
            self.update_empty()
            return True
        return super().eventFilter(obj, event)

    def _position_empty(self):
        viewport = self.editor.viewport()
        self.empty.move(max(0, (viewport.width()-self.empty.width())//2),
                        max(20, (viewport.height()-self.empty.height())//2-12))

    def update_empty(self):
        self._position_empty()
        self.empty.setVisible(not self.editor.toPlainText() and not self.editor.hasFocus())

    def _on_text_changed(self):
        text = self.text()
        count = len(text.split('\n')) if text else 0
        self.count_label.setText(f'{count:,} 行 · {len(text):,} 字符')
        self.copy_button.setEnabled(bool(text))
        self.clear_button.setEnabled(bool(text))
        self.update_empty()
        self.textChanged.emit()

    def _cursor_changed(self, line, column):
        self.position_label.setText(f'行 {line}，列 {column}')

    def text(self):
        return self.editor.toPlainText()

    def set_text(self, text, filename='', encoding='纯文本'):
        self.filename = filename
        self.encoding = encoding
        self.file_label.setText(Path(filename).name if filename else '粘贴输入')
        self.file_label.setToolTip(filename)
        self.editor.setPlainText(text)
        self.position_label.setText(encoding)
        self.update_empty()

    def set_metadata(self, filename, format_label, modified=False):
        self.filename = str(filename) if filename else ''
        self.encoding = format_label
        name = Path(self.filename).name if self.filename else '粘贴输入'
        self.file_label.setText(('● ' if modified else '') + name)
        self.file_label.setToolTip(self.filename or name)
        # Updating dirty state must not overwrite a Unicode cursor report.
        self.position_label.setToolTip(format_label)
        self.file_label.setToolTip((self.filename + '\n' if self.filename else '') + format_label)
        self.save_button.setToolTip('保存这一侧  Ctrl+S' + (' · 有未保存修改' if modified else ''))

    def render_diff(self, result):
        lines = result.left_lines if self.side == 'left' else result.right_lines
        self.editor.set_diff_rows(result.rows, self.side, lines)

    def replace_text(self, text):
        # Keep merging undoable; source files are never saved implicitly.
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.select(cursor.Document)
        cursor.insertText(text)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)

    def paste_text(self):
        text = QApplication.clipboard().text()
        if not text:
            self.notice.emit('剪贴板中没有可粘贴的文字')
            self.editor.setFocus()
            return
        self.editor.setFocus()
        cursor = self.editor.textCursor()
        cursor.select(cursor.Document)
        cursor.insertText(text)
        self.editor.setTextCursor(cursor)

    def clear_text(self):
        self.replace_text('')
        self.editor.setFocus()

    def copy_text(self):
        QApplication.clipboard().setText(self.text())
        self.notice.emit(f'已复制{self.title}')

    def set_colors(self, colors):
        self._colors = colors
        self.badge.setStyleSheet(f'background:{colors["accent_soft"]};color:{colors["accent"]};border-radius:6px;font-weight:700;font-size:12px;')
        self.empty_icon.setPixmap(icon('paste', colors['accent'], 27).pixmap(27, 27))
        self.empty_icon.setStyleSheet(f'background:{colors["placeholder_bg"]};border-radius:16px;')
        self.empty_button.setIcon(icon('paste', colors['accent'], 16))
        for button in self.buttons:
            button.setIcon(icon(button.property('icon_name'), colors['secondary'], 18))
        self.editor.set_palette_colors(colors)
