"""Actual QTextLayout format checks, independent of offscreen font rendering."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextDocument, QTextFormat
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication

from easytextdiff.diff_engine import compare_texts, DiffOptions
from easytextdiff.editor import CodeEditor
from easytextdiff.highlighting import SyntaxHighlighter, canonical_language, detect_language


class HighlightingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication(["highlighting-tests"])

    def make(self, language, text):
        self.document = QTextDocument(text)
        self.highlighter = SyntaxHighlighter(self.document, language)
        self.highlighter.rehighlight()
        return self.highlighter

    def color_at(self, block_number, codepoint):
        block = self.document.findBlockByNumber(block_number)
        position = len(block.text()[:codepoint].encode("utf-16-le")) // 2
        color = None
        for span in block.layout().formats():
            if span.start <= position < span.start + span.length:
                color = span.format.foreground().color().name()
        return color

    def role(self, name):
        return self.highlighter.formats[name].foreground().color().name()

    def test_extensions_and_manual_labels(self):
        cases = {r"C:\rtl\core.SVH": "verilog", "a.v": "verilog", "a.cpp": "cpp",
                 "a.H": "cpp", "main.py": "python", "data.JSON": "json", "readme.md": "plain"}
        for path, language in cases.items():
            with self.subTest(path=path):
                self.assertEqual(detect_language(path), language)
        self.assertEqual(canonical_language("C / C++"), "cpp")
        self.assertEqual(canonical_language("Verilog / SystemVerilog"), "verilog")

    def test_explicit_extension_wins_over_pasted_content(self):
        self.assertEqual(detect_language("design.sv", "def example():\n    pass"), "verilog")
        self.assertEqual(detect_language("note.md", "module example; endmodule"), "plain")

    def test_paste_heuristics_and_plain_fallback(self):
        for text, expected in [
            ("module top(input logic clk);\nendmodule", "verilog"),
            ("#include <stdint.h>\nint x = 0;", "cpp"),
            ("def hello():\n    print('hello')", "python"),
            ('{"threshold": 1.5, "valid": true}', "json"),
            ("A paragraph about ordinary text.", "plain"),
        ]:
            self.assertEqual(detect_language(text=text), expected)

    def test_cpp_keyword_type_number_and_string(self):
        self.make("cpp", 'const int value = 42; const char* s = "// not a comment";')
        self.assertEqual(self.color_at(0, 0), self.role("keyword"))
        self.assertEqual(self.color_at(0, 6), self.role("type"))
        self.assertEqual(self.color_at(0, 18), self.role("number"))
        self.assertEqual(self.color_at(0, 39), self.role("string"))

    def test_systemverilog_types_numbers_and_block_comment(self):
        self.make("verilog", "module top;\nlogic [7:0] value = 8'hFF; /* always\nstill comment */ assign done = 1'b1;\nendmodule")
        self.assertEqual(self.color_at(0, 0), self.role("keyword"))
        self.assertEqual(self.color_at(1, 0), self.role("type"))
        self.assertEqual(self.color_at(1, 20), self.role("number"))
        self.assertEqual(self.color_at(2, 0), self.role("comment"))
        self.assertEqual(self.color_at(2, 17), self.role("keyword"))

    def test_cpp_block_comments_end_before_following_code(self):
        self.make("cpp", "/* int start\nend */ int count = 1;")
        self.assertEqual(self.color_at(0, 3), self.role("comment"))
        self.assertEqual(self.color_at(1, 0), self.role("comment"))
        self.assertEqual(self.color_at(1, 7), self.role("type"))
        self.assertEqual(self.document.firstBlock().userState(), SyntaxHighlighter.BLOCK_COMMENT)
        self.assertEqual(self.document.lastBlock().userState(), 0)

    def test_python_triple_string_does_not_treat_hash_as_comment(self):
        self.make("python", "def example():\n    text = '''start\n# still string\nend'''\n    return 1 # comment")
        self.assertEqual(self.color_at(0, 0), self.role("keyword"))
        self.assertEqual(self.color_at(2, 0), self.role("string"))
        self.assertEqual(self.color_at(4, 4), self.role("keyword"))
        self.assertEqual(self.color_at(4, 13), self.role("comment"))

    def test_cpp_raw_string_preserves_custom_multiline_delimiter(self):
        self.make("cpp", 'auto s = R"tag(begin\n// not comment "quote"\nend)tag"; int x;')
        self.assertEqual(self.color_at(1, 0), self.role("string"))
        self.assertEqual(self.color_at(1, 16), self.role("string"))
        self.assertEqual(self.color_at(2, 10), self.role("type"))

    def test_json_unicode_key_and_keyword_use_utf16_ranges(self):
        self.make("json", '{"\U0001f600": true, "value": 42}')
        self.assertEqual(self.color_at(0, 2), self.role("key"))
        self.assertEqual(self.color_at(0, 6), self.role("keyword"))
        self.assertEqual(self.color_at(0, 21), self.role("number"))
        keyword_ranges = [span for span in self.document.firstBlock().layout().formats()
                          if span.format.foreground().color().name() == self.role("keyword")]
        self.assertTrue(any(span.start == 7 and span.length == 4 for span in keyword_ranges))

    def test_formats_only_set_foreground_and_plain_clears(self):
        self.make("python", "return 42 # comment")
        for span in self.document.firstBlock().layout().formats():
            self.assertTrue(span.format.hasProperty(QTextFormat.ForegroundBrush))
            self.assertFalse(span.format.hasProperty(QTextFormat.BackgroundBrush))
            self.assertFalse(span.format.hasProperty(QTextFormat.FontWeight))
            self.assertEqual(span.format.background().style(), Qt.NoBrush)
        self.highlighter.set_language("plain")
        self.assertEqual(list(self.document.firstBlock().layout().formats()), [])

    def test_theme_change_recolors_existing_tokens(self):
        self.make("cpp", "return 1;")
        light = self.color_at(0, 0)
        self.highlighter.set_colors({"bg": "#151B18"})
        self.assertNotEqual(self.color_at(0, 0), light)

    def test_editor_keeps_diff_backgrounds_and_source_copy(self):
        editor = CodeEditor()
        try:
            result = compare_texts("int a = 1;\n", "int a = 2;\n", DiffOptions())
            editor.setPlainText("int a = 1;\n")
            editor.set_diff_rows(result.rows, "left", result.left_lines)
            colors = [selection.format.background().color().name() for selection in editor.extraSelections()]
            editor.set_language("cpp")
            editor._syntax_highlighter.rehighlight()
            self.assertEqual(colors, [selection.format.background().color().name() for selection in editor.extraSelections()])
            editor.selectAll()
            self.assertEqual(editor.createMimeDataFromSelection().text(), "int a = 1;\n")
            self.assertEqual(editor.language, "cpp")
        finally:
            editor.close()

    def test_editor_auto_updates_on_paste_and_filename_wins(self):
        editor = CodeEditor()
        try:
            editor.set_language("auto")
            editor.setPlainText("module top;\nendmodule")
            QTest.qWait(220)
            self.assertEqual(editor.language, "verilog")
            editor.set_language("auto", "configuration.json")
            self.assertEqual(editor.language, "json")
            editor.set_language("plain")
            self.assertEqual(editor.language, "plain")
        finally:
            editor.close()

    def test_language_and_theme_do_not_emit_source_text_changes(self):
        editor = CodeEditor()
        try:
            editor.setPlainText("int value = 1;")
            self.application.processEvents()
            spy = QSignalSpy(editor.textChanged)
            editor.set_language("cpp")
            editor.set_palette_colors({"bg": "#151B18"})
            self.application.processEvents()
            self.assertEqual(len(spy), 0)
            self.assertFalse(editor.document().isModified())
            editor.insertPlainText("new")
            self.assertGreater(len(spy), 0)
        finally:
            editor.close()


if __name__ == "__main__":
    unittest.main()
