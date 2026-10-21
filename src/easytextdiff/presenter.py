"""Per-tab application logic, independent of the main-window shell."""
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

from .dialogs import QtDialogs
from .diff_engine import DiffOptions, apply_change, export_unified
from .file_service import ExternalModificationError, FileServiceError, read_document, save_document
from .highlighting import detect_language
from .models import ComparisonModel, DocumentModel
from .reports import html_report
from .tasks import CompareCoordinator


class SessionPresenter(QObject):
    """Coordinate one model and view; all file writes use file_service."""

    stateChanged = pyqtSignal()

    def __init__(self, view, model=None, dialogs=None, pool=None, compute=None):
        super().__init__(view)
        self.view = view
        self.model = model or ComparisonModel()
        self.dialogs = dialogs or QtDialogs(view)
        kwargs = {'pool': pool}
        if compute is not None:
            kwargs['compute'] = compute
        self.coordinator = CompareCoordinator(parent=self, **kwargs)
        self.result = None
        self.current_change = -1
        self.dirty = True
        self._disposed = False
        self._languages = {'left': 'auto', 'right': 'auto'}
        view.textEdited.connect(self.edit_text)
        view.compareRequested.connect(self.compare)
        view.navigateRequested.connect(self.navigate)
        view.mergeRequested.connect(self.merge)
        view.importRequested.connect(self.import_file)
        view.saveRequested.connect(self.save)
        view.optionsChanged.connect(self.options_changed)
        view.automaticChanged.connect(self.automatic_changed)
        view.swapRequested.connect(self.swap)
        view.languageChanged.connect(self.set_language)
        view.rowRequested.connect(self.go_to_row)
        self.coordinator.resultReady.connect(self._compared)
        self.coordinator.failed.connect(self._failed)
        self.coordinator.busyChanged.connect(self._busy_changed)
        for side in ('left', 'right'):
            self._render_document(side)
        self.view.set_navigation(None, -1)

    @property
    def title(self):
        title = self.model.display_title
        return ('● ' if self.modified else '') + title

    @property
    def modified(self):
        return self.model.left.modified or self.model.right.modified

    @property
    def can_export(self):
        return self.result is not None and not self.dirty

    def document(self, side):
        return self.model.left if side == 'left' else self.model.right

    def options(self):
        return DiffOptions(self.view.ignore_whitespace.isChecked(), self.view.ignore_case.isChecked())

    def _metadata(self, side):
        doc = self.document(side)
        self.view.update_metadata(side, doc.path, doc.format_label, doc.modified)

    def _render_document(self, side):
        doc = self.document(side)
        self.view.set_document(side, doc.text, doc.path, doc.format_label, doc.modified)
        self._highlight(side)

    def _highlight(self, side):
        doc = self.document(side)
        language = self._languages[side]
        if language == 'auto':
            language = detect_language(str(doc.path or ''), doc.text)
        pane = self.view.pane(side)
        pane.editor.set_language(language)

    def set_language(self, side, language):
        self._languages[side] = language
        self._highlight(side)

    def edit_text(self, side, text):
        self.document(side).text = text
        self._metadata(side)
        self._highlight(side)
        self._invalidate()
        if self.view.automatic.isChecked():
            self._request(delay_ms=500)

    def _invalidate(self):
        self.coordinator.invalidate()
        self.dirty = True
        self.view.invalidate_result()
        self.view.set_status('文字已更新 · 自动比较已开启' if self.view.automatic.isChecked() else
                             '文字已更新 · 按 Ctrl+Enter 重新比较')
        self.stateChanged.emit()

    def _request(self, delay_ms=0, show_empty_notice=False):
        if not self.model.left.text and not self.model.right.text:
            self.view.summary_label.clear()
            if show_empty_notice:
                self.view.notice('先在任一侧粘贴文字，再开始对比')
            return
        self.coordinator.request(self.model.left.text, self.model.right.text, self.options(), delay_ms=delay_ms)

    def compare(self):
        self._request(show_empty_notice=True)

    def options_changed(self):
        self._invalidate()
        self._request()

    def automatic_changed(self, enabled):
        if enabled and self.dirty:
            self._request(delay_ms=500)
        elif not enabled and self.coordinator.pending:
            self.coordinator.invalidate()

    def _busy_changed(self, busy):
        self.view.set_busy(busy)
        if busy:
            self.view.set_status('正在整理逐行差异…')

    def _compared(self, result):
        if self._disposed:
            return
        self.result = result
        self.dirty = False
        self.current_change = 0 if result.changes else -1
        self.view.render_result(result, self.current_change)
        self.view.set_status(f'对比完成 · {result.elapsed_ms:.0f} ms · 内容仅在本机处理')
        self.stateChanged.emit()

    def _failed(self, error):
        self.view.notice('未能完成对比：' + error)
        self.stateChanged.emit()

    def navigate(self, direction):
        if not self.can_export or not self.result.changes:
            return
        self.current_change = (self.current_change + direction) % len(self.result.changes)
        self.view.set_navigation(self.result, self.current_change, scroll=True)

    def go_to_row(self, row):
        if not self.can_export:
            return
        for pane in (self.view.left, self.view.right):
            pane.editor.scroll_to_row(row)
        for index, change in enumerate(self.result.changes):
            if change.start_row <= row < change.end_row:
                self.current_change = index
                self.view.set_navigation(self.result, index)
                break

    def merge(self, target):
        if not self.can_export or self.current_change < 0:
            return
        text = apply_change(self.result, self.current_change, target)
        self.view.pane(target).replace_text(text)
        self.compare()

    def confirm_replace(self, side):
        doc = self.document(side)
        if not doc.modified:
            return True
        choice = self.dialogs.unsaved(doc, side)
        if choice == 'save':
            return self.save(side)
        return choice == 'discard'

    def can_close(self):
        return all(self.confirm_replace(side) for side in ('left', 'right'))

    def import_file(self, side, path=''):
        path = path or self.dialogs.choose_open(side)
        if not path:
            return False
        try:
            document = read_document(path)
        except (OSError, ValueError, FileServiceError) as error:
            self.dialogs.warning('无法导入文本', str(error))
            return False
        if not self.confirm_replace(side):
            return False
        # Saving during the confirmation may update the very path being
        # imported. Do not install the pre-save snapshot as a clean document.
        try:
            document = read_document(path)
        except (OSError, ValueError, FileServiceError) as error:
            self.dialogs.warning('无法导入文本', str(error))
            return False
        setattr(self.model, side, document)
        self._languages[side] = 'auto'
        self.view.pane(side).language_combo.setCurrentIndex(0)
        self._render_document(side)
        self._invalidate()
        if self.view.automatic.isChecked():
            self._request(delay_ms=500)
        self.view.notice(f'已导入 {document.display_name}')
        return True

    def save(self, side=None, *, save_as=False):
        side = side or self.view.active_side
        doc = self.document(side)
        path, encoding, newline = doc.path, None, None
        if save_as or path is None:
            choice = self.dialogs.choose_save(doc)
            if choice is None:
                return False
            path, encoding, newline = Path(choice.path).expanduser().resolve(), choice.encoding, choice.newline
            if path.exists() and (doc.path is None or path.resolve() != Path(doc.path).resolve()):
                if not self.dialogs.overwrite(path):
                    return False
        original_encoding = 'utf-8-sig' if doc.encoding == 'utf-8' and doc.bom else doc.encoding
        normalizes = doc.modified or (newline is not None and newline != doc.newline.value) or (
            encoding is not None and encoding != original_encoding)
        if doc.mixed_newlines and normalizes and not self.dialogs.mixed_newlines(doc):
            return False
        try:
            save_document(doc, path, encoding=encoding, newline=newline)
        except ExternalModificationError:
            if not self.dialogs.external_modified(doc):
                return False
            try:
                save_document(doc, path, encoding=encoding, newline=newline, overwrite_external=True)
            except (OSError, ValueError, FileServiceError) as error:
                self.dialogs.warning('无法保存文本', str(error))
                return False
        except (OSError, ValueError, FileServiceError) as error:
            self.dialogs.warning('无法保存文本', str(error))
            return False
        self._metadata(side)
        self._highlight(side)
        self.view.notice(f'已保存 {doc.display_name} · {doc.format_label}')
        self.stateChanged.emit()
        return True

    def swap(self):
        self.model.left, self.model.right = self.model.right, self.model.left
        self._languages['left'], self._languages['right'] = self._languages['right'], self._languages['left']
        for side in ('left', 'right'):
            combo = self.view.pane(side).language_combo
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(self._languages[side])))
            combo.blockSignals(False)
            self._render_document(side)
        self._invalidate()
        self.compare()

    def load_example(self, left, right):
        self.model.left, self.model.right = DocumentModel(left), DocumentModel(right)
        for side in ('left', 'right'):
            self._languages[side] = 'cpp'
            combo = self.view.pane(side).language_combo
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData('cpp'))
            combo.blockSignals(False)
            self._render_document(side)
        self._invalidate()
        self.compare()

    def export_report(self):
        if not self.can_export:
            return False
        path = self.dialogs.choose_report()
        if not path:
            return False
        path = Path(path)
        if not path.suffix:
            path = path.with_suffix('.html')
        text = html_report(self.result, str(self.model.left.path or '原始文本'),
                           str(self.model.right.path or '修改文本'), self.options())
        try:
            path.write_text(text, encoding='utf-8')
        except OSError as error:
            self.dialogs.warning('无法保存报告', str(error))
            return False
        self.view.notice('报告已保存，可用浏览器直接打开')
        return True

    def copy_patch(self):
        text = export_unified(self.model.left.text, self.model.right.text,
            str(self.model.left.path or 'original.txt'), str(self.model.right.path or 'modified.txt'))
        QApplication.clipboard().setText(text)
        self.view.notice('已复制原文的统一差异补丁')

    def dispose(self):
        self._disposed = True
        self.coordinator.dispose()
