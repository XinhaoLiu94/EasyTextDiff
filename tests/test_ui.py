"""MVP integration checks; launch with QT_QPA_PLATFORM=offscreen."""
import tempfile
import unittest
from html import escape
from pathlib import Path

from PyQt5.QtCore import QCoreApplication, QEvent, QEventLoop, QSettings, QTimer, Qt
from PyQt5.QtGui import QTextCursor
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication
from easytextdiff.app import create_application
from easytextdiff.main_window import MainWindow
from easytextdiff.reports import html_report


class FakeDialogs:
    def __init__(self):
        self.answer = 'discard'
        self.warnings = []

    def unsaved(self, document, side):
        return self.answer

    def choose_open(self, side):
        return ''

    def choose_save(self, document):
        return None

    def choose_report(self):
        return ''

    def overwrite(self, path):
        return False

    def external_modified(self, document):
        return False

    def mixed_newlines(self, document):
        return False

    def warning(self, title, text):
        self.warnings.append((title, text))


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or create_application(['easytextdiff-ui-tests'])
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='easytextdiff-tests-')
        self.settings = QSettings(str(Path(self.temporary.name) / 'settings.ini'), QSettings.IniFormat)
        self.settings.setValue('theme', 'light')
        self.dialogs = []

        def factory(view):
            dialogs = FakeDialogs()
            self.dialogs.append(dialogs)
            return dialogs

        self.window = MainWindow(settings=self.settings, dialogs_factory=factory)
        self.window.show()
        self.application.processEvents()

    def tearDown(self):
        for dialogs in self.dialogs:
            dialogs.answer = 'discard'
        for presenter in tuple(self.window.presenters.values()):
            presenter.coordinator.dispose()
        self.window.pool.waitForDone(3000)
        self.application.processEvents()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.application.processEvents()
        self.settings.sync()
        self.temporary.cleanup()

    def wait_for(self, predicate, timeout=6000):
        if predicate():
            return
        loop, poll, deadline = QEventLoop(), QTimer(), QTimer()
        poll.setInterval(5)
        deadline.setSingleShot(True)
        poll.timeout.connect(lambda: loop.quit() if predicate() else None)
        deadline.timeout.connect(loop.quit)
        poll.start()
        deadline.start(timeout)
        loop.exec_()
        poll.stop()
        deadline.stop()
        self.assertTrue(predicate(), 'Qt operation did not finish before timeout')

    def wait_result(self, presenter):
        self.wait_for(lambda: presenter.can_export and not presenter.coordinator.busy
                      and not presenter.coordinator.pending)
        return presenter.result

    def compare(self, left, right):
        view, presenter = self.window.active_view, self.window.active_presenter
        view.left.editor.setPlainText(left)
        view.right.editor.setPlainText(right)
        view.compare_button.click()
        self.wait_result(presenter)
        return presenter

    @staticmethod
    def editor_state(editor):
        cursor = editor.textCursor()
        return (editor.toPlainText(), cursor.position(), cursor.anchor(),
                cursor.selectedText(), editor.document().availableUndoSteps())

    def test_manual_comparison_preserves_source_selection_and_real_undo_history(self):
        view, presenter = self.window.active_view, self.window.active_presenter
        view.automatic.setChecked(False)
        left, right = view.left.editor, view.right.editor
        right.setPlainText('prefix😀 NEW suffix')
        left.insertPlainText('prefix😀 OLD suffix')
        cursor = left.textCursor()
        start = len('prefix😀 '.encode('utf-16-le')) // 2
        cursor.setPosition(start)
        cursor.setPosition(start + 3, QTextCursor.KeepAnchor)
        left.setTextCursor(cursor)
        before = (self.editor_state(left), self.editor_state(right))
        edited = QSignalSpy(view.textEdited)
        view.compare_button.click()
        self.wait_result(presenter)
        self.assertIs(view.left.editor, left)
        self.assertIs(view.right.editor, right)
        self.assertEqual((self.editor_state(left), self.editor_state(right)), before)
        self.assertEqual(len(edited), 0)
        self.assertTrue(any(selection.cursor.selectedText() == 'OLD'
                            for selection in left.extraSelections()))
        self.assertFalse(left.isReadOnly())
        left.undo()
        self.assertEqual(left.toPlainText(), '')
        self.assertEqual(presenter.model.left.text, '')

    def test_keyboard_and_overview_navigation_use_the_same_source_editors(self):
        presenter = self.compare('head\nold\nmiddle\nlast\ntail',
                                 'head\nnew\nmiddle\nLAST\ntail')
        view = self.window.active_view
        left, right = view.left.editor, view.right.editor
        before = (left.toPlainText(), right.toPlainText(),
                  left.document().availableUndoSteps(), right.document().availableUndoSteps())
        self.assertEqual(len(presenter.result.changes), 2)
        self.window.activateWindow()
        self.window.setFocus()
        self.application.processEvents()
        QTest.keyClick(self.window, Qt.Key_F8)
        self.wait_for(lambda: presenter.current_change == 1)
        QTest.keyClick(self.window, Qt.Key_F7)
        self.wait_for(lambda: presenter.current_change == 0)
        view.overview.activated.emit(presenter.result.changes[1].start_row)
        self.assertEqual(presenter.current_change, 1)
        self.assertEqual(left.textCursor().blockNumber(), 3)
        self.assertEqual(right.textCursor().blockNumber(), 3)
        self.assertIs(view.left.editor, left)
        self.assertIs(view.right.editor, right)
        self.assertFalse(left.isReadOnly())
        self.assertFalse(right.isReadOnly())
        self.assertEqual((left.toPlainText(), right.toPlainText(),
                          left.document().availableUndoSteps(), right.document().availableUndoSteps()), before)

    def test_scroll_sync_maps_common_source_anchors_after_insertions(self):
        lines = [f'common line {index:03d}' for index in range(320)]
        right_lines = lines[:80] + [f'inserted {index}' for index in range(10)] + lines[80:]
        self.compare('\n'.join(lines), '\n'.join(right_lines))
        view = self.window.active_view
        left, right = view.left.editor, view.right.editor
        self.wait_for(lambda: min(left.verticalScrollBar().maximum(),
                                  right.verticalScrollBar().maximum()) > 200)
        cursors = (left.textCursor().position(), right.textCursor().position())
        right.verticalScrollBar().setValue(180)
        self.application.processEvents()
        self.assertEqual(left.firstVisibleBlock().text(), right.firstVisibleBlock().text())
        self.assertEqual(right.firstVisibleBlock().blockNumber() - left.firstVisibleBlock().blockNumber(), 10)
        left.verticalScrollBar().setValue(140)
        self.application.processEvents()
        self.assertEqual(left.firstVisibleBlock().text(), right.firstVisibleBlock().text())
        self.assertEqual(right.firstVisibleBlock().blockNumber() - left.firstVisibleBlock().blockNumber(), 10)
        self.assertEqual((left.textCursor().position(), right.textCursor().position()), cursors)

    def test_default_has_only_editable_source_panes(self):
        view, presenter = self.window.active_view, self.window.active_presenter
        self.assertIn('EasyTextDiff', self.window.windowTitle())
        self.assertIn('轻松文本对比', self.window.windowTitle())
        self.assertNotIn('QingDiff', self.window.windowTitle())
        self.assertEqual(self.window.workspace.count(), 1)
        self.assertEqual((view.left.text(), view.right.text()), ('', ''))
        self.assertFalse(hasattr(view, 'edit_tab'))
        self.assertFalse(hasattr(view, 'review_tab'))
        self.assertTrue(view.automatic.isChecked())
        self.assertFalse(presenter.can_export)
        self.assertFalse(self.window.export_button.isEnabled())
        for pane in (view.left, view.right):
            self.assertFalse(pane.editor.isReadOnly())
            self.assertFalse(hasattr(pane, 'viewer'))
            self.assertFalse(hasattr(pane, 'stack'))
        view.compare_button.click()
        self.assertFalse(presenter.coordinator.busy)
        self.assertIn('粘贴文字', view.status_label.text())

    def test_clipboard_buttons_show_diffs_in_same_editors(self):
        view, presenter = self.window.active_view, self.window.active_presenter
        editors = (view.left.editor, view.right.editor)
        QApplication.clipboard().setText('第一行\n旧😀\n')
        view.left.paste_button.click()
        QApplication.clipboard().setText('第一行\n新😀\n')
        view.right.empty_button.click()
        self.assertEqual(view.left.text(), '第一行\n旧😀\n')
        self.assertEqual(view.right.text(), '第一行\n新😀\n')
        view.compare_button.click()
        self.assertEqual(self.wait_result(presenter).modified_lines, 1)
        self.assertEqual((view.left.editor, view.right.editor), editors)
        self.assertTrue(all(not editor.isReadOnly() for editor in editors))
        self.assertTrue(any(selection.cursor.hasSelection()
                            for selection in view.left.editor.extraSelections()))
        self.assertTrue(self.window.export_button.isEnabled())

    def test_automatic_comparison_preserves_edit_focus(self):
        view, presenter = self.window.active_view, self.window.active_presenter
        view.right.editor.setPlainText('new value')
        self.window.activateWindow()
        view.left.editor.setFocus()
        view.left.editor.insertPlainText('old value')
        cursor = view.left.editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(3, QTextCursor.KeepAnchor)
        view.left.editor.setTextCursor(cursor)
        before = self.editor_state(view.left.editor)
        edited = QSignalSpy(view.textEdited)
        self.application.processEvents()
        self.assertTrue(presenter.coordinator.pending)
        self.assertTrue(view.left.editor.hasFocus())
        self.wait_result(presenter)
        self.assertTrue(view.left.editor.hasFocus())
        self.assertEqual(self.editor_state(view.left.editor), before)
        self.assertEqual(len(edited), 0)
        self.assertFalse(view.left.editor.isReadOnly())
        self.assertEqual(presenter.result.modified_lines, 1)

    def test_new_tab_preserves_old_session_and_isolates_models(self):
        first_view = self.window.active_view
        first = self.compare('original A', 'original B')
        first_view.new_button.click()
        second_view, second = self.window.active_view, self.window.active_presenter
        self.assertEqual(self.window.workspace.count(), 2)
        self.assertIsNot(first.model, second.model)
        self.assertEqual((second_view.left.text(), second_view.right.text()), ('', ''))
        self.assertFalse(second_view.left.editor.isReadOnly())
        second_view.left.editor.setPlainText('second session')
        self.assertEqual(first.model.left.text, 'original A')
        self.assertEqual(first.model.right.text, 'original B')
        self.window.workspace.setCurrentWidget(first_view)
        self.assertIs(self.window.active_presenter, first)
        self.assertTrue(first.can_export)

    def test_cancel_window_close_keeps_all_tabs_and_text(self):
        first = self.window.active_view
        first.left.editor.setPlainText('unsaved first')
        self.window.new_comparison()
        second = self.window.active_view
        second.right.editor.setPlainText('unsaved second')
        self.dialogs[1].answer = 'cancel'
        self.assertFalse(self.window.close())
        self.assertEqual(self.window.workspace.count(), 2)
        self.assertEqual(len(self.window.presenters), 2)
        self.assertEqual(first.left.text(), 'unsaved first')
        self.assertEqual(second.right.text(), 'unsaved second')
        self.assertTrue(self.window.isVisible())
        self.assertIs(self.window.active_view, second)

    def test_merge_then_undo_updates_model(self):
        presenter = self.compare('head\n旧值\nend', 'head\n新值\nend')
        view = self.window.active_view
        view.merge_left_button.click()
        self.wait_result(presenter)
        self.assertEqual(view.left.text(), 'head\n新值\nend')
        self.assertTrue(presenter.result.identical)
        self.assertTrue(view.left.editor.document().isUndoAvailable())
        view.left.editor.undo()
        self.assertEqual(view.left.text(), 'head\n旧值\nend')
        self.assertEqual(presenter.model.left.text, 'head\n旧值\nend')
        self.assertTrue(presenter.dirty)
        self.assertFalse(view.left.editor.isReadOnly())
        view.compare_button.click()
        self.wait_result(presenter)
        self.assertEqual(presenter.result.modified_lines, 1)

    def test_identical_and_either_empty_side(self):
        for left, right, identical in (('相同\n', '相同\n', True),
                                       ('', '新增\n', False), ('删除\n', '', False)):
            with self.subTest(left=left, right=right):
                presenter = self.compare(left, right)
                view = self.window.active_view
                self.assertEqual(presenter.result.identical, identical)
                self.assertFalse(view.left.editor.isReadOnly())
                self.assertFalse(view.right.editor.isReadOnly())
                self.assertEqual(view.next_button.isEnabled(), not identical)

    def test_asymmetric_long_line_keeps_source_viewports_equal(self):
        lines = [f'line {index:03d}' for index in range(280)]
        right_lines = list(lines)
        right_lines[173] = 'right-only long line: ' + 'abcdefghij' * 300
        self.compare('\n'.join(lines), '\n'.join(right_lines))
        view = self.window.active_view
        left, right = view.left.editor, view.right.editor
        self.wait_for(lambda: right.horizontalScrollBar().maximum() > 0
                      and right.verticalScrollBar().maximum() > 0)
        self.assertEqual(left.horizontalScrollBar().maximum(), 0)
        right.verticalScrollBar().setValue(right.verticalScrollBar().maximum())
        self.application.processEvents()
        self.assertEqual(left.viewport().height(), right.viewport().height())
        self.assertEqual(left.verticalScrollBar().value(), right.verticalScrollBar().value())
        self.assertGreater(right.firstVisibleBlock().blockNumber(), 200)
        self.assertEqual(left.firstVisibleBlock().blockNumber(), right.firstVisibleBlock().blockNumber())

    def test_cursor_footer_counts_codepoints(self):
        view = self.window.active_view
        view.left.editor.insertPlainText('😀')
        self.assertEqual(view.left.position_label.text(), '行 1，列 2')
        view.left.editor.insertPlainText('A')
        self.assertEqual(view.left.position_label.text(), '行 1，列 3')
        self.assertIn('2 字符', view.left.count_label.text())

    def test_html_report_escapes_content_and_filenames(self):
        presenter = self.compare('<script>alert("X")</script>', '<script>alert("Y")</script>')
        left_name, right_name = '<source & "one">', '<target & "two">'
        document = html_report(presenter.result, left_name, right_name)
        self.assertNotIn('<script>', document)
        self.assertIn('&lt;script&gt;', document)
        self.assertIn(escape(left_name), document)
        self.assertIn(escape(right_name), document)
        self.assertIn('<mark>', document)
        self.assertIn('EasyTextDiff', document)
        self.assertNotIn('QingDiff', document)
        self.assertNotIn('轻比', document)


if __name__ == '__main__':
    unittest.main()
