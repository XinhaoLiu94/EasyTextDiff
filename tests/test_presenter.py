"""Save/import/close integration without native dialogs or user preferences."""

import codecs
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtCore import QEvent, QSettings
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QApplication

from dialogs import SaveChoice
from file_service import FileServiceError
from main_window import MainWindow
from models import Newline


class FakeDialogs:
    def __init__(self):
        self.unsaved_choice = "cancel"
        self.save_choice = None
        self.open_path = ""
        self.allow_external = False
        self.allow_mixed = False
        self.allow_overwrite = False
        self.calls = []
        self.warnings = []

    def unsaved(self, document, side):
        self.calls.append(("unsaved", side))
        return self.unsaved_choice

    def choose_save(self, document):
        self.calls.append(("choose_save", document.path))
        return self.save_choice

    def choose_open(self, side):
        self.calls.append(("choose_open", side))
        return self.open_path

    def external_modified(self, document):
        self.calls.append(("external_modified", document.path))
        return self.allow_external

    def mixed_newlines(self, document):
        self.calls.append(("mixed_newlines", document.path))
        return self.allow_mixed

    def overwrite(self, path):
        self.calls.append(("overwrite", path))
        return self.allow_overwrite

    def warning(self, title, text):
        self.warnings.append((title, text))

    def choose_report(self):
        self.calls.append(("choose_report",))
        return ""


class PresenterFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication(["easytextdiff-presenter-tests"])
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="easytextdiff-presenter-")
        self.root = Path(self.temporary.name)
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.IniFormat)
        self.settings.setValue("theme", "light")
        self.settings.setValue("automatic", False)
        self.dialogs = FakeDialogs()
        self.window = MainWindow(settings=self.settings, dialogs_factory=lambda view: self.dialogs)
        self.presenter = self.window.active_presenter
        self.view = self.window.active_view

    def tearDown(self):
        self.dialogs.unsaved_choice = "discard"
        self.window.close()
        self.window.pool.waitForDone(1500)
        self.window.deleteLater()
        self.application.sendPostedEvents(None, QEvent.DeferredDelete)
        self.application.processEvents()
        self.settings.sync()
        self.temporary.cleanup()

    def write(self, name, payload):
        path = self.root / name
        path.write_bytes(payload)
        return path

    def import_left(self, path):
        self.assertTrue(self.presenter.import_file("left", str(path)))
        return self.presenter.document("left")

    def edit_left(self, text):
        self.view.left.editor.setPlainText(text)
        self.assertEqual(self.presenter.document("left").text, text)

    def assert_dirty_indicators(self, expected):
        self.assertEqual(self.presenter.modified, expected)
        self.assertEqual(self.view.left.file_label.text().startswith("● "), expected)
        self.assertEqual(self.window.workspace.tabText(0).startswith("● "), expected)

    def test_cancelled_save_prevents_closing_dirty_tab(self):
        self.edit_left("unsaved input")
        original_view = self.window.active_view
        self.dialogs.unsaved_choice = "save"
        self.dialogs.save_choice = None
        self.assertFalse(self.window.close_comparison(0))
        self.assertEqual(self.window.workspace.count(), 1)
        self.assertIs(self.window.active_view, original_view)
        self.assertEqual(self.presenter.document("left").text, "unsaved input")
        self.assert_dirty_indicators(True)
        self.assertEqual([call[0] for call in self.dialogs.calls], ["unsaved", "choose_save"])

    def test_cancelled_save_prevents_replacing_input_during_import(self):
        self.edit_left("keep my input")
        original_document = self.presenter.document("left")
        imported = self.write("incoming.txt", b"replacement\r\n")
        self.dialogs.unsaved_choice = "save"
        self.dialogs.save_choice = None
        self.assertFalse(self.presenter.import_file("left", str(imported)))
        self.assertIs(self.presenter.document("left"), original_document)
        self.assertEqual(self.view.left.text(), "keep my input")
        self.assertIsNone(original_document.path)
        self.assertEqual(imported.read_bytes(), b"replacement\r\n")
        self.assert_dirty_indicators(True)

    def test_import_same_path_after_saving_reloads_latest_bytes(self):
        path = self.write("same-file.txt", b"old disk content\r\n")
        self.import_left(path)
        self.edit_left("saved new content\n")
        self.dialogs.unsaved_choice = "save"
        self.assertTrue(self.presenter.import_file("left", str(path)))
        self.assertEqual(path.read_bytes(), b"saved new content\r\n")
        self.assertEqual(self.presenter.document("left").text, "saved new content\n")
        self.assertEqual(self.view.left.text(), "saved new content\n")
        self.assert_dirty_indicators(False)

    def test_successful_same_path_save_preserves_format_and_clears_dirty(self):
        path = self.write("source.txt", codecs.BOM_UTF16_BE + "甲\r\n乙".encode("utf-16-be"))
        document = self.import_left(path)
        self.edit_left("甲\n修改后\n")
        self.assertTrue(self.presenter.save("left"))
        self.assertEqual(path.read_bytes(), codecs.BOM_UTF16_BE + "甲\r\n修改后\r\n".encode("utf-16-be"))
        self.assertIs(self.presenter.document("left"), document)
        self.assertEqual(document.path, path)
        self.assertEqual(document.encoding, "utf-16-be")
        self.assertEqual(document.newline, Newline.CRLF)
        self.assertEqual(document.bom, codecs.BOM_UTF16_BE)
        self.assertEqual(document._saved_text, "甲\n修改后\n")
        self.assertIn("UTF-16 BE BOM", self.view.left.position_label.toolTip())
        self.assertIn("CRLF", self.view.left.position_label.toolTip())
        self.assert_dirty_indicators(False)
        self.assertEqual(self.dialogs.warnings, [])

    def test_failed_save_retains_dirty_model_and_reports_error(self):
        path = self.write("source.txt", b"baseline\n")
        document = self.import_left(path)
        self.edit_left("pending edit\n")
        with patch("presenter.save_document", side_effect=FileServiceError("disk unavailable")):
            self.assertFalse(self.presenter.save("left"))
        self.assertEqual(path.read_bytes(), b"baseline\n")
        self.assertEqual(document._saved_text, "baseline\n")
        self.assertEqual(document.text, "pending edit\n")
        self.assertEqual(len(self.dialogs.warnings), 1)
        self.assertIn("disk unavailable", self.dialogs.warnings[0][1])
        self.assert_dirty_indicators(True)

    def test_external_change_cancellation_preserves_disk_and_local_edit(self):
        path = self.write("external.txt", b"loaded\n")
        document = self.import_left(path)
        self.edit_left("local edit\n")
        path.write_bytes(b"external edit\n")
        self.dialogs.allow_external = False
        self.assertFalse(self.presenter.save("left"))
        self.assertEqual(path.read_bytes(), b"external edit\n")
        self.assertEqual(document._saved_text, "loaded\n")
        self.assertEqual(document.text, "local edit\n")
        self.assertEqual(sum(call[0] == "external_modified" for call in self.dialogs.calls), 1)
        self.assert_dirty_indicators(True)
        self.assertEqual(self.dialogs.warnings, [])

    def test_confirmed_external_overwrite_commits_local_edit(self):
        path = self.write("external.txt", codecs.BOM_UTF8 + b"loaded\r\n")
        document = self.import_left(path)
        self.edit_left("local edit\n")
        path.write_bytes(b"external edit\n")
        self.dialogs.allow_external = True
        self.assertTrue(self.presenter.save("left"))
        self.assertEqual(path.read_bytes(), codecs.BOM_UTF8 + b"local edit\r\n")
        self.assertEqual(document._saved_text, "local edit\n")
        self.assertEqual(sum(call[0] == "external_modified" for call in self.dialogs.calls), 1)
        self.assert_dirty_indicators(False)
        self.assertEqual(self.dialogs.warnings, [])

    def test_mixed_newline_cancellation_prevents_normalizing_original(self):
        original = b"one\r\ntwo\nthree\r\n"
        path = self.write("mixed.txt", original)
        document = self.import_left(path)
        self.edit_left("one\ntwo\nthree\nfour\n")
        self.dialogs.allow_mixed = False
        self.assertFalse(self.presenter.save("left"))
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(document.mixed_newlines)
        self.assertEqual(document._saved_text, "one\ntwo\nthree\n")
        self.assertEqual(sum(call[0] == "mixed_newlines" for call in self.dialogs.calls), 1)
        self.assert_dirty_indicators(True)

    def test_confirmed_mixed_newline_save_uses_predominant_format(self):
        path = self.write("mixed.txt", b"one\r\ntwo\nthree\r\n")
        document = self.import_left(path)
        self.edit_left("one\ntwo\nthree\nfour\n")
        self.dialogs.allow_mixed = True
        self.assertTrue(self.presenter.save("left"))
        self.assertEqual(path.read_bytes(), b"one\r\ntwo\r\nthree\r\nfour\r\n")
        self.assertFalse(document.mixed_newlines)
        self.assert_dirty_indicators(False)

    def test_undo_to_loaded_baseline_clears_both_modified_indicators(self):
        path = self.write("undo.txt", b"baseline\n")
        document = self.import_left(path)
        self.assert_dirty_indicators(False)
        editor = self.view.left.editor
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        editor.setTextCursor(cursor)
        editor.insertPlainText("extra")
        self.assertEqual(document.text, "baseline\nextra")
        self.assert_dirty_indicators(True)
        self.assertTrue(editor.document().isUndoAvailable())
        editor.undo()
        self.assertEqual(document.text, "baseline\n")
        self.assert_dirty_indicators(False)
        self.assertEqual(path.read_bytes(), b"baseline\n")
        self.assertFalse(any(call[0] == "choose_save" for call in self.dialogs.calls))

    def test_save_as_overwrite_cancellation_keeps_destination_and_model(self):
        source = self.write("source.txt", b"source\n")
        target = self.write("target.txt", b"existing destination")
        document = self.import_left(source)
        self.edit_left("local changes\n")
        self.dialogs.save_choice = SaveChoice(str(target), "utf-8-sig", "\r\n")
        self.dialogs.allow_overwrite = False
        self.assertFalse(self.presenter.save("left", save_as=True))
        self.assertEqual(document.path, source)
        self.assertEqual(document.bom, b"")
        self.assertEqual(document.newline, Newline.LF)
        self.assertEqual(source.read_bytes(), b"source\n")
        self.assertEqual(target.read_bytes(), b"existing destination")
        self.assert_dirty_indicators(True)


if __name__ == "__main__":
    unittest.main()
