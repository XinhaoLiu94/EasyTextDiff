"""Qt dialogs used by presenters; replaceable in integration tests."""
from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)


@dataclass(frozen=True)
class SaveChoice:
    path: str
    encoding: str
    newline: str


class SaveDialog(QDialog):
    def __init__(self, parent, document):
        super().__init__(parent)
        self.setWindowTitle('保存文本')
        self.resize(590, 230)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        form = QFormLayout()
        row = QHBoxLayout()
        self.path_input = QLineEdit(str(document.path) if document.path else '')
        self.path_input.setPlaceholderText('选择保存位置')
        browse = QPushButton('浏览…')
        browse.clicked.connect(self._browse)
        row.addWidget(self.path_input, 1)
        row.addWidget(browse)
        form.addRow('文件', row)
        self.encoding_combo = QComboBox()
        for label, value in [('UTF-8', 'utf-8'), ('UTF-8 BOM', 'utf-8-sig'),
                             ('UTF-16 LE BOM', 'utf-16-le'), ('UTF-16 BE BOM', 'utf-16-be'),
                             ('GB18030', 'gb18030')]:
            self.encoding_combo.addItem(label, value)
        encoding = 'utf-8-sig' if document.encoding == 'utf-8' and document.bom else document.encoding
        index = self.encoding_combo.findData(encoding)
        self.encoding_combo.setCurrentIndex(max(0, index))
        form.addRow('编码', self.encoding_combo)
        self.newline_combo = QComboBox()
        for label, value in [('LF（Unix）', '\n'), ('CRLF（Windows）', '\r\n'), ('CR（经典 Mac）', '\r')]:
            self.newline_combo.addItem(label, value)
        self.newline_combo.setCurrentIndex(max(0, self.newline_combo.findData(document.newline.value)))
        form.addRow('换行', self.newline_combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('保存')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(self, '选择保存位置', self.path_input.text() or '文本.txt',
                                             '文本和代码文件 (*);;文本文件 (*.txt)',
                                             options=QFileDialog.DontConfirmOverwrite)
        if path:
            self.path_input.setText(path)

    def _accept(self):
        if not self.path_input.text().strip():
            self.path_input.setFocus()
            return
        self.accept()

    def choice(self):
        return SaveChoice(self.path_input.text().strip(), self.encoding_combo.currentData(),
                          self.newline_combo.currentData())


class QtDialogs:
    def __init__(self, parent):
        self.parent = parent

    def _message(self, title, text, buttons, default, icon=QMessageBox.Question):
        box = QMessageBox(icon, title, text, buttons, self.parent)
        box.setTextFormat(Qt.PlainText)
        box.setDefaultButton(default)
        for role, label in ((QMessageBox.Save, '保存'), (QMessageBox.Discard, '放弃修改'),
                            (QMessageBox.Cancel, '取消'), (QMessageBox.Yes, '继续'), (QMessageBox.No, '取消')):
            button = box.button(role)
            if button is not None:
                button.setText(label)
        return box.exec_()

    def unsaved(self, document, side):
        label = '左侧' if side == 'left' else '右侧'
        choice = self._message('有未保存的修改',
            f'{label}“{document.display_name}”的修改尚未保存。是否保存后继续？',
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        return {QMessageBox.Save: 'save', QMessageBox.Discard: 'discard'}.get(choice, 'cancel')

    def mixed_newlines(self, document):
        return self._message('统一混合换行',
            '原文件含有多种换行格式。编辑后的保存会使用所选的统一换行格式，是否继续？',
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Yes

    def overwrite(self, path):
        return self._message('覆盖文件', f'“{path}”已存在，是否覆盖？',
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Yes

    def external_modified(self, document):
        return self._message('文件已在外部修改',
            f'“{document.path}”在导入后已被其他程序修改或移除。是否用当前内容覆盖？',
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Yes

    def choose_open(self, side):
        path, _ = QFileDialog.getOpenFileName(self.parent, '导入左侧文本' if side == 'left' else '导入右侧文本', '',
            '文本和代码 (*.txt *.md *.v *.sv *.vh *.c *.cpp *.h *.hpp *.py *.json *.yaml *.yml *.tcl *.log *.csv);;所有文件 (*)')
        return path

    def choose_save(self, document):
        dialog = SaveDialog(self.parent, document)
        return dialog.choice() if dialog.exec_() == QDialog.Accepted else None

    def warning(self, title, text):
        self._message(title, text, QMessageBox.Ok, QMessageBox.Ok, QMessageBox.Warning)

    def choose_report(self):
        path, _ = QFileDialog.getSaveFileName(self.parent, '导出差异报告', '文本差异报告.html', 'HTML 报告 (*.html)')
        return path
