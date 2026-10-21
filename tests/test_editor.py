"""Native source editing must remain intact while diff decorations change."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCursor
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication

from easytextdiff.diff_engine import DiffOptions, compare_texts
from easytextdiff.editor import CodeEditor


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication(["editor-tests"])

    def setUp(self):
        self.editor = CodeEditor()

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        self.application.processEvents()

    def show_diff(self, left, right, side="left"):
        self.editor.setPlainText(left if side == "left" else right)
        result = compare_texts(left, right, DiffOptions())
        lines = result.left_lines if side == "left" else result.right_lines
        self.editor.set_diff_rows(result.rows, side, lines)
        return result

    def select_positions(self, start, end):
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)

    def test_decorations_preserve_text_selection_scroll_focus_and_signals(self):
        left = "a\U0001f600\n" + "\n".join(str(i) for i in range(80))
        self.editor.setPlainText(left)
        self.editor.resize(400, 240)
        self.editor.show()
        self.editor.setFocus()
        self.application.processEvents()
        self.select_positions(1, 3)
        self.editor.verticalScrollBar().setValue(20)
        result = compare_texts(left, "inserted\n" + left, DiffOptions())
        cursor = self.editor.textCursor()
        state = (cursor.position(), cursor.anchor(), self.editor.verticalScrollBar().value(),
                 self.editor.document().availableUndoSteps(), self.editor.document().isModified(),
                 self.editor.hasFocus())
        text_events = QSignalSpy(self.editor.textChanged)
        cursor_events = QSignalSpy(self.editor.cursorPositionChanged)
        self.editor.set_diff_rows(result.rows, "left", result.left_lines)
        self.editor.set_current_change(0, 1)
        self.editor.clear_diff()
        cursor = self.editor.textCursor()
        self.assertEqual(state, (cursor.position(), cursor.anchor(), self.editor.verticalScrollBar().value(),
                                self.editor.document().availableUndoSteps(), self.editor.document().isModified(),
                                self.editor.hasFocus()))
        self.assertEqual(self.editor.toPlainText(), left)
        self.assertEqual(len(text_events), 0)
        self.assertEqual(len(cursor_events), 0)
        self.assertFalse(self.editor.isReadOnly())

    def test_decorating_does_not_pollute_native_undo(self):
        self.editor.setPlainText("first\nsecond")
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText("!")
        self.editor.setTextCursor(cursor)
        left = self.editor.toPlainText()
        result = compare_texts(left, "first\ninserted\nsecond!", DiffOptions())
        steps = self.editor.document().availableUndoSteps()
        self.editor.set_diff_rows(result.rows, "left", result.left_lines)
        self.editor.clear_diff()
        self.assertEqual(self.editor.document().availableUndoSteps(), steps)
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), "first\nsecond")

    def test_native_copy_cut_paste_preserves_blank_lines_and_emoji(self):
        source = "a\U0001f600\n\nend\n"
        self.show_diff(source, "prefix\n" + source)
        self.editor.selectAll()
        QTest.keyClick(self.editor, Qt.Key_C, Qt.ControlModifier)
        self.assertEqual(QApplication.clipboard().text(), source)
        self.editor.cut()
        self.assertEqual(self.editor.toPlainText(), "")
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), source)
        self.editor.selectAll()
        QApplication.clipboard().setText("new\n\n\U0001f600")
        self.editor.paste()
        self.assertEqual(self.editor.toPlainText(), "new\n\n\U0001f600")

    def test_emoji_inline_spans_use_qt_utf16_positions(self):
        self.show_diff("a\U0001f600x", "a\U0001f603x")
        inline = [item.cursor for item in self.editor.extraSelections() if item.cursor.hasSelection()]
        self.assertEqual(len(inline), 1)
        self.assertEqual(inline[0].selectedText(), "\U0001f600")
        self.assertEqual((inline[0].selectionStart(), inline[0].selectionEnd()), (1, 3))

    def test_bidirectional_alignment_maps_missing_rows_to_nearest_source(self):
        self.show_diff("A\nB\nC", "A\nnew1\nnew2\nB\nC")
        self.assertEqual([self.editor.aligned_row_for_source(i) for i in range(3)], [0, 3, 4])
        self.assertEqual([self.editor.source_row_for_aligned(i) for i in range(5)], [0, 0, 1, 1, 2])
        self.assertEqual(self.editor.source_row_for_aligned(-100), 0)
        self.assertEqual(self.editor.source_row_for_aligned(100), 2)
        self.editor.scroll_to_row(3)
        self.assertEqual(self.editor.textCursor().blockNumber(), 1)

    def test_insertions_mark_middle_prefix_and_suffix_boundaries(self):
        cases = [
            ("A\nB", "prefix\nA\nB", 0),
            ("A\nB", "A\ninserted\nB", 1),
            ("A\nB", "A\nB\nsuffix", 2),
        ]
        for left, right, boundary in cases:
            result = self.show_diff(left, right)
            change = result.changes[0]
            self.editor.set_current_change(change.start_row, change.end_row)
            self.assertEqual(self.editor._source_change_marker(), ("boundary", boundary, None))

    def test_deletions_mark_original_source_range(self):
        result = self.show_diff("A\ndeleted\nB", "A\nB")
        change = result.changes[0]
        self.editor.set_current_change(change.start_row, change.end_row)
        self.assertEqual(self.editor._source_change_marker(), ("range", 1, 2))
        self.assertEqual(self.editor.toPlainText(), "A\ndeleted\nB")

    def test_empty_source_has_legal_anchor_without_placeholder_text(self):
        result = self.show_diff("", "one\ntwo")
        self.assertTrue(self.editor.has_diff)
        self.assertEqual(self.editor.toPlainText(), "")
        self.assertEqual(self.editor.blockCount(), 1)
        self.assertEqual(self.editor.source_row_for_aligned(1), 0)
        self.editor.set_current_change(0, len(result.rows))
        self.assertEqual(self.editor._source_change_marker(), ("boundary", 0, None))
        self.editor.clear_diff()
        self.assertFalse(self.editor.has_diff)

    def test_cursor_signal_reports_source_line_and_unicode_column(self):
        self.show_diff("abc\na\U0001f600x", "abc\ninserted\na\U0001f600x")
        spy = QSignalSpy(self.editor.cursorPositionReported)
        block = self.editor.document().findBlockByNumber(1)
        self.select_positions(block.position() + 3, block.position() + 3)
        self.assertEqual(list(spy[-1]), [2, 3])

    def test_theme_aliases_and_dynamic_source_gutter_geometry(self):
        self.editor.set_palette_colors({"bg": "#151A23", "text": "#E8EEF8", "gutter_bg": "#191F2A"})
        self.assertEqual(self.editor.palette().base().color().name(), "#151a23")
        self.editor.setPlainText("\n".join(str(i) for i in range(1000)))
        self.assertEqual(self.editor._line_number_area.width(), self.editor.line_number_area_width())


if __name__ == "__main__":
    unittest.main()
