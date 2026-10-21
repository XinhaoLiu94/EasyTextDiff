"""Presentation widgets for one comparison; no file I/O or comparison jobs."""
from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QTextCursor, QTextDocument
from PyQt5.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from icons import icon
from overview import DiffOverview
from widgets import TextPane, tool_button


class SessionView(QWidget):
    """Passive comparison view. Signals express intent, setters render state."""

    textEdited = pyqtSignal(str, str)
    compareRequested = pyqtSignal()
    navigateRequested = pyqtSignal(int)
    mergeRequested = pyqtSignal(str)
    importRequested = pyqtSignal(str, str)
    saveRequested = pyqtSignal(str)
    sampleRequested = pyqtSignal()
    swapRequested = pyqtSignal()
    newRequested = pyqtSignal()
    optionsChanged = pyqtSignal()
    automaticChanged = pyqtSignal(bool)
    languageChanged = pyqtSignal(str, str)
    rowRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = None
        self.active_side = 'left'
        self._scroll_lock = False
        self._wrapping = False
        self._rendering = False
        self._colors = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 12, 26, 12)
        outer.setSpacing(14)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.sample_button = QPushButton('  载入示例')
        self.swap_button = QPushButton('  交换左右')
        self.new_button = QPushButton('  新建比较')
        for button, signal in ((self.sample_button, self.sampleRequested),
                               (self.swap_button, self.swapRequested),
                               (self.new_button, self.newRequested)):
            button.clicked.connect(signal.emit)
            controls.addWidget(button)
        self.sample_button.setObjectName('quiet')
        self.swap_button.setObjectName('quiet')

        self.summary_label = QLabel()
        self.summary_label.setObjectName('subtitle')
        controls.addStretch()
        self.automatic = QCheckBox('自动比较')
        self.automatic.setChecked(True)
        self.automatic.setToolTip('停止输入约半秒后更新结果，不打断输入焦点')
        self.automatic.toggled.connect(self.automaticChanged)
        self.ignore_whitespace = QCheckBox('忽略空白')
        self.ignore_whitespace.setToolTip('忽略行内空白，保留原文和换行')
        self.ignore_case = QCheckBox('忽略大小写')
        controls.addWidget(self.automatic)
        for checkbox in (self.ignore_whitespace, self.ignore_case):
            checkbox.toggled.connect(self.optionsChanged)
            controls.addWidget(checkbox)
        self.sync_button = tool_button('link', '同步两侧滚动')
        self.sync_button.setCheckable(True)
        self.sync_button.setChecked(True)
        controls.addWidget(self.sync_button)
        self.compare_button = QPushButton('  开始对比')
        self.compare_button.setObjectName('primary')
        self.compare_button.setToolTip('开始对比  Ctrl+Enter / F5')
        self.compare_button.clicked.connect(self.compareRequested)
        controls.addWidget(self.compare_button)
        outer.addLayout(controls)

        self.search_box = QFrame()
        self.search_box.setObjectName('searchBox')
        search = QHBoxLayout(self.search_box)
        search.setContentsMargins(8, 0, 4, 0)
        search.addWidget(QLabel('查找当前栏'))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('输入文字，按 Enter 跳转')
        self.search_input.returnPressed.connect(self.find_next)
        search.addWidget(self.search_input, 1)
        self.find_previous_button = tool_button('up', '查找上一处', lambda: self.find_next(True))
        self.find_next_button = tool_button('down', '查找下一处', self.find_next)
        self.find_close_button = tool_button('close', '关闭查找', self.search_box.hide)
        for button in (self.find_previous_button, self.find_next_button, self.find_close_button):
            search.addWidget(button)
        self.search_box.hide()
        outer.addWidget(self.search_box)

        panels = QHBoxLayout()
        panels.setSpacing(0)
        self.left, self.right = TextPane('left'), TextPane('right')
        panels.addWidget(self.left, 1)
        center = QWidget()
        center.setFixedWidth(42)
        actions = QVBoxLayout(center)
        actions.setContentsMargins(6, 0, 6, 0)
        actions.setSpacing(10)
        actions.addStretch()
        self.merge_left_button = tool_button('left', '将当前差异应用到左侧', lambda: self.mergeRequested.emit('left'))
        self.merge_right_button = tool_button('right', '将当前差异应用到右侧', lambda: self.mergeRequested.emit('right'))
        for button in (self.merge_left_button, self.merge_right_button):
            button.setObjectName('mergeButton')
            button.setFixedSize(30, 34)
            actions.addWidget(button)
        actions.addStretch()
        panels.addWidget(center)
        panels.addWidget(self.right, 1)
        self.overview = DiffOverview()
        self.overview.setToolTip('差异概览：点击跳到对应行')
        self.overview.activated.connect(self.rowRequested)
        panels.addSpacing(8)
        panels.addWidget(self.overview)
        outer.addLayout(panels, 1)

        bottom = QHBoxLayout()
        self.legend_delete = QLabel('●  删除')
        self.legend_add = QLabel('●  新增')
        self.legend_change = QLabel('较深底色表示行内修改')
        self.legend_change.setObjectName('subtitle')
        for label in (self.legend_delete, self.legend_add, self.legend_change):
            bottom.addWidget(label)
            bottom.addSpacing(9)
        bottom.addWidget(self.summary_label)
        bottom.addStretch()
        self.change_position = QLabel()
        self.change_position.setObjectName('subtitle')
        self.previous_button = tool_button('up', '上一处差异  F7', lambda: self.navigateRequested.emit(-1))
        self.next_button = tool_button('down', '下一处差异  F8', lambda: self.navigateRequested.emit(1))
        for widget in (self.change_position, self.previous_button, self.next_button):
            bottom.addWidget(widget)
        outer.addLayout(bottom)
        self.status_label = QLabel('就绪 · 粘贴文字即可开始')
        self.status_label.setObjectName('subtitle')
        self.status_label.setTextFormat(Qt.PlainText)
        outer.addWidget(self.status_label)
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self._status = self.status_label.text()
        self.notice_timer.timeout.connect(lambda: self.status_label.setText(self._status))

        for side in ('left', 'right'):
            pane = self.pane(side)
            pane.textChanged.connect(lambda s=side: self._text_changed(s))
            pane.notice.connect(self.notice)
            pane.importRequested.connect(lambda s=side: self.importRequested.emit(s, ''))
            pane.fileDropped.connect(lambda path, s=side: self.importRequested.emit(s, path))
            pane.saveRequested.connect(lambda s=side: self.saveRequested.emit(s))
            pane.languageChanged.connect(lambda language, s=side: self.languageChanged.emit(s, language))
            pane.editor.installEventFilter(self)
        self._connect_scrolls(self.left.editor, self.right.editor)
        self.set_navigation(None, -1)

    def pane(self, side):
        return self.left if side == 'left' else self.right

    @property
    def wrapping(self):
        return self._wrapping

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            if obj is self.left.editor:
                self.active_side = 'left'
            elif obj is self.right.editor:
                self.active_side = 'right'
        return super().eventFilter(obj, event)

    def _text_changed(self, side):
        if not self._rendering:
            self.textEdited.emit(side, self.pane(side).text())

    def set_document(self, side, text, path='', format_label='UTF-8 · LF', modified=False):
        self._rendering = True
        try:
            self.pane(side).set_text(text, str(path) if path else '', format_label)
            self.pane(side).set_metadata(path, format_label, modified)
        finally:
            self._rendering = False

    def update_metadata(self, side, path, format_label, modified):
        self.pane(side).set_metadata(path, format_label, modified)

    def invalidate_result(self):
        self._result = None
        self.summary_label.setText('文字已更新')
        self.overview.set_result(None)
        for pane in (self.left, self.right):
            pane.editor.clear_diff()
        self.set_navigation(None, -1)

    def render_result(self, result, current):
        self._result = result
        for pane in (self.left, self.right):
            pane.render_diff(result)
        self.overview.set_result(result)
        self.summary_label.setText('两侧文本一致' if result.identical else
            f'{len(result.changes)} 处差异 · +{result.added_lines} −{result.deleted_lines}  ~{result.modified_lines}')
        self.set_navigation(result, current)

    def set_navigation(self, result, current, scroll=False):
        enabled = bool(result and result.changes)
        for button in (self.previous_button, self.next_button, self.merge_left_button, self.merge_right_button):
            button.setEnabled(enabled)
        self.change_position.setText(f'{current+1} / {len(result.changes)} 处' if enabled else '')
        self.overview.set_current_change(current if result else -1)
        if enabled:
            change = result.changes[current]
            for pane in (self.left, self.right):
                pane.editor.set_current_change(change.start_row, change.end_row)
                if scroll:
                    pane.editor.scroll_to_row(change.start_row)

    def set_busy(self, busy):
        self.compare_button.setText('  正在对比…' if busy else '  开始对比')
        # A fresh manual request may supersede a running automatic request.
        self.compare_button.setEnabled(True)

    def set_status(self, text):
        self._status = text
        if not self.notice_timer.isActive():
            self.status_label.setText(text)

    def notice(self, text):
        self.status_label.setText(text)
        self.notice_timer.start(5500)

    def show_find(self):
        self.search_box.show()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def find_next(self, backwards=False):
        query = self.search_input.text()
        if not query:
            return
        pane = self.pane(self.active_side)
        editor = pane.editor
        flags = QTextDocument.FindBackward if backwards else QTextDocument.FindFlags()
        if not editor.find(query, flags):
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.End if backwards else QTextCursor.Start)
            editor.setTextCursor(cursor)
            if not editor.find(query, flags):
                self.notice('当前栏没有找到这段文字')

    def set_wrap(self, enabled):
        self._wrapping = enabled
        for pane in (self.left, self.right):
            pane.editor.set_wrap(enabled)

    def _connect_scrolls(self, left, right):
        for source, target in ((left, right), (right, left)):
            source.verticalScrollBar().valueChanged.connect(lambda value, s=source, t=target: self._sync_scroll(s, t, value))
            source.horizontalScrollBar().valueChanged.connect(lambda value, t=target: self._sync_horizontal(t, value))

    def _sync_scroll(self, source, target, value):
        if self._scroll_lock:
            return
        self._scroll_lock = True
        try:
            if self.sync_button.isChecked():
                if self._result is not None:
                    source_block = source.firstVisibleBlock()
                    aligned_row = source.aligned_row_for_source(source_block.blockNumber())
                    target_row = target.source_row_for_aligned(aligned_row)
                    target_block = target.document().findBlockByNumber(target_row)
                    if target_block.isValid():
                        offset = max(0, value - source_block.firstLineNumber())
                        target.verticalScrollBar().setValue(target_block.firstLineNumber() +
                            min(offset, max(0, target_block.lineCount()-1)))
                else:
                    maximum = source.verticalScrollBar().maximum()
                    ratio = value / maximum if maximum else 0
                    target.verticalScrollBar().setValue(round(ratio * target.verticalScrollBar().maximum()))
            if self._result is not None:
                first = source.firstVisibleBlock().blockNumber()
                count = max(1, source.viewport().height() // max(1, source.fontMetrics().height()))
                self.overview.set_visible_rows(source.aligned_row_for_source(first),
                    source.aligned_row_for_source(min(source.blockCount()-1, first+count)) + 1)
        finally:
            self._scroll_lock = False

    def _sync_horizontal(self, target, value):
        if self._scroll_lock or not self.sync_button.isChecked():
            return
        self._scroll_lock = True
        try:
            target.horizontalScrollBar().setValue(value)
        finally:
            self._scroll_lock = False

    def set_colors(self, colors):
        self._colors = colors
        for pane in (self.left, self.right):
            pane.set_colors(colors)
        self.overview.set_colors(colors)
        self.legend_delete.setStyleSheet(f'color:{colors["red"]};font-size:11px;')
        self.legend_add.setStyleSheet(f'color:{colors["green"]};font-size:11px;')
        self.summary_label.setStyleSheet(f'color:{colors["accent"]};font-size:11px;')
        for button, name in ((self.sample_button,'sample'), (self.swap_button,'swap'),
                             (self.new_button,'plus'), (self.sync_button,'link'),
                             (self.previous_button,'up'), (self.next_button,'down'),
                             (self.merge_left_button,'left'), (self.merge_right_button,'right'),
                             (self.find_previous_button,'up'), (self.find_next_button,'down'),
                             (self.find_close_button,'close')):
            button.setIcon(icon(name, colors['secondary'], 18))
        self.compare_button.setIcon(icon('compare', colors['bg'], 18))
