import codecs
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from file_service import (BinaryFileError, ExternalModificationError,
                          FileServiceError, FileTooLargeError,
                          UnsupportedEncodingError, read_document, save_document)
from models import ComparisonModel, DocumentModel, Newline


class DocumentModelTests(unittest.TestCase):
    def test_text_is_canonical_and_undo_restores_unmodified_state(self):
        document = DocumentModel("one\r\ntwo\rthree\n")
        self.assertEqual(document.text, "one\ntwo\nthree\n")
        self.assertFalse(document.modified)
        document.text += "four\r\n"
        self.assertTrue(document.modified)
        self.assertTrue(document.text.endswith("four\n"))
        document.text = "one\r\ntwo\rthree\n"
        self.assertFalse(document.modified)

    def test_format_changes_are_modified_even_without_text_changes(self):
        document = DocumentModel("same")
        document.newline = Newline.CRLF
        self.assertTrue(document.modified)
        document.newline = Newline.LF
        self.assertFalse(document.modified)
        document.bom = codecs.BOM_UTF8
        self.assertTrue(document.modified)
        document.mark_saved()
        self.assertFalse(document.modified)
        self.assertEqual(document.format_label, "UTF-8 BOM · LF")
        document.encoding = "gb18030"
        self.assertTrue(document.modified)

    def test_comparison_defaults_are_independent_and_title_uses_paths(self):
        comparison = ComparisonModel()
        comparison.left.text = "only left"
        self.assertEqual(comparison.right.text, "")
        comparison.left.path = Path("left.txt")
        comparison.right.path = Path("right.txt")
        self.assertEqual(comparison.display_title, "left.txt ↔ right.txt")


class DocumentFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, payload):
        path = self.root / name
        path.write_bytes(payload)
        return path

    def test_lossless_format_roundtrips(self):
        cases = [
            ("utf8", "hello\n中文\n", "utf-8", b"", Newline.LF),
            ("utf8bom", "hello\r\n中文\r\n", "utf-8", codecs.BOM_UTF8, Newline.CRLF),
            ("utf16le", "hello\r\n中文\r\n", "utf-16-le", codecs.BOM_UTF16_LE, Newline.CRLF),
            ("utf16be", "hello\r中文\r", "utf-16-be", codecs.BOM_UTF16_BE, Newline.CR),
            ("gb18030", "中文𠀀\r\n下一行\r\n", "gb18030", b"", Newline.CRLF),
        ]
        for name, text, encoding, bom, newline in cases:
            with self.subTest(name=name):
                payload = bom + text.encode(encoding)
                path = self.write(name + ".txt", payload)
                document = read_document(path)
                self.assertEqual(document.encoding, encoding)
                self.assertEqual(document.bom, bom)
                self.assertEqual(document.newline, newline)
                self.assertNotIn("\r", document.text)
                self.assertFalse(document.modified)
                self.assertIs(save_document(document), document)
                self.assertEqual(path.read_bytes(), payload)
                self.assertFalse(document.modified)

    def test_empty_bom_only_file_roundtrip(self):
        for encoding, bom in (("utf-8", codecs.BOM_UTF8),
                              ("utf-16-le", codecs.BOM_UTF16_LE),
                              ("utf-16-be", codecs.BOM_UTF16_BE)):
            with self.subTest(encoding=encoding):
                path = self.write("empty.txt", bom)
                document = read_document(path)
                self.assertEqual(document.text, "")
                save_document(document)
                self.assertEqual(path.read_bytes(), bom)

    def test_mixed_endings_preserve_bytes_until_edit(self):
        original = b"one\r\ntwo\nthree\rfour\r\n"
        path = self.write("mixed.txt", original)
        document = read_document(path)
        self.assertTrue(document.mixed_newlines)
        self.assertEqual(document.newline, Newline.CRLF)
        self.assertEqual(document.newline_counts, {"\n": 1, "\r\n": 2, "\r": 1})
        copy_path = self.root / "copy.txt"
        save_document(document, copy_path)
        self.assertEqual(copy_path.read_bytes(), original)
        self.assertTrue(document.mixed_newlines)
        document.text += "five\n"
        save_document(document)
        self.assertEqual(copy_path.read_bytes(), b"one\r\ntwo\r\nthree\r\nfour\r\nfive\r\n")
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(document.mixed_newlines)
        self.assertFalse(document.modified)

    def test_mixed_ending_ties_use_first_seen_and_undo_keeps_original(self):
        original = b"one\rtwo\nthree\r\n"
        path = self.write("tie.txt", original)
        document = read_document(path)
        self.assertEqual(document.newline, Newline.CR)
        saved_text = document.text
        document.text += "edit"
        document.text = saved_text
        self.assertFalse(document.modified)
        save_document(document)
        self.assertEqual(path.read_bytes(), original)

    def test_edit_preserves_utf16be_bom_and_eol(self):
        path = self.write("big-endian.txt", codecs.BOM_UTF16_BE + "甲\r\n乙".encode("utf-16-be"))
        document = read_document(path)
        document.text = "甲\n乙\n丙"
        save_document(document)
        self.assertEqual(path.read_bytes(), codecs.BOM_UTF16_BE + "甲\r\n乙\r\n丙".encode("utf-16-be"))
        self.assertFalse(document.modified)

    def test_explicit_encoding_and_newline_conversion_commits_after_save(self):
        document = DocumentModel("中文\nnext\n")
        path = self.root / "converted.txt"
        save_document(document, path, encoding="utf-8-sig", newline=Newline.CRLF)
        self.assertEqual(path.read_bytes(), codecs.BOM_UTF8 + "中文\r\nnext\r\n".encode("utf-8"))
        self.assertEqual(document.encoding, "utf-8")
        self.assertEqual(document.bom, codecs.BOM_UTF8)
        self.assertEqual(document.newline, Newline.CRLF)
        self.assertEqual(document.path, path.resolve())
        self.assertFalse(document.modified)
        save_document(document, encoding="utf-8")
        self.assertEqual(path.read_bytes(), "中文\r\nnext\r\n".encode("utf-8"))
        self.assertEqual(document.bom, b"")

    def test_explicit_utf16_encoding_emits_matching_bom(self):
        for encoding, bom in (("utf-16-le", codecs.BOM_UTF16_LE),
                              ("utf-16-be", codecs.BOM_UTF16_BE)):
            with self.subTest(encoding=encoding):
                document = DocumentModel("中文\n")
                path = self.root / (encoding + ".txt")
                save_document(document, path, encoding=encoding)
                self.assertEqual(path.read_bytes(), bom + "中文\n".encode(encoding))

    def test_atomic_replace_failure_preserves_both_files_and_model(self):
        source = self.write("source.txt", b"baseline\r\n")
        target = self.write("target.txt", b"existing destination")
        document = read_document(source)
        document.text = "edited\n"
        before = (document.path, document.encoding, document.newline, document.bom,
                  document._saved_text, document._saved_format, document._original_bytes)
        with patch("file_service.os.replace", side_effect=OSError("destination locked")):
            with self.assertRaises(FileServiceError):
                save_document(document, target, encoding="utf-8-sig", newline=Newline.LF)
        self.assertEqual(source.read_bytes(), b"baseline\r\n")
        self.assertEqual(target.read_bytes(), b"existing destination")
        self.assertEqual(before, (document.path, document.encoding, document.newline,
                                 document.bom, document._saved_text,
                                 document._saved_format, document._original_bytes))
        self.assertTrue(document.modified)
        self.assertEqual({path.name for path in self.root.iterdir()}, {"source.txt", "target.txt"})

    def test_unencodable_text_is_not_replaced_or_written(self):
        path = self.write("safe.txt", b"original")
        document = read_document(path)
        document.text = "bad surrogate: \ud800"
        with self.assertRaises(UnsupportedEncodingError):
            save_document(document)
        self.assertEqual(path.read_bytes(), b"original")
        self.assertTrue(document.modified)
        self.assertEqual(document._saved_text, "original")

    def test_external_edit_is_not_overwritten_and_baseline_is_unchanged(self):
        path = self.write("external.txt", b"loaded\r\n")
        document = read_document(path)
        document.text = "my changes\n"
        path.write_bytes(b"external changes\r\n")
        with self.assertRaises(ExternalModificationError):
            save_document(document)
        self.assertEqual(path.read_bytes(), b"external changes\r\n")
        self.assertEqual(document.text, "my changes\n")
        self.assertEqual(document._saved_text, "loaded\n")
        self.assertEqual(document._original_bytes, b"loaded\r\n")
        self.assertTrue(document.modified)
        self.assertEqual([entry.name for entry in self.root.iterdir()], ["external.txt"])

    def test_explicit_external_overwrite_updates_disk_and_baseline(self):
        path = self.write("external.txt", b"loaded\n")
        document = read_document(path)
        document.text = "my changes\n"
        path.write_bytes(b"external changes\n")
        save_document(document, overwrite_external=True)
        self.assertEqual(path.read_bytes(), b"my changes\n")
        self.assertEqual(document._original_bytes, b"my changes\n")
        self.assertFalse(document.modified)
        document.text = "next local save\n"
        save_document(document)
        self.assertEqual(path.read_bytes(), b"next local save\n")

    def test_external_deletion_requires_confirmation(self):
        path = self.write("deleted.txt", b"loaded")
        document = read_document(path)
        document.text = "edited"
        path.unlink()
        with self.assertRaises(ExternalModificationError):
            save_document(document)
        self.assertFalse(path.exists())
        self.assertTrue(document.modified)
        self.assertEqual(document._saved_text, "loaded")
        save_document(document, overwrite_external=True)
        self.assertEqual(path.read_bytes(), b"edited")
        self.assertFalse(document.modified)

    def test_missing_parent_save_does_not_commit_model(self):
        document = DocumentModel()
        document.text = "new content"
        with self.assertRaises(FileServiceError):
            save_document(document, self.root / "missing" / "new.txt")
        self.assertIsNone(document.path)
        self.assertTrue(document.modified)

    def test_binary_files_are_rejected(self):
        for raw in (b"text\x00binary", b"\x01\x02\x03data", b"\x89PNG\r\n\x1a\n\x00data"):
            with self.subTest(raw=raw):
                with self.assertRaises(BinaryFileError):
                    read_document(self.write("binary.bin", raw))

    def test_size_limit_counts_bytes_and_allows_exact_limit(self):
        path = self.write("size.txt", "中文".encode("utf-8"))
        with self.assertRaises(FileTooLargeError):
            read_document(path, max_bytes=5)
        self.assertEqual(read_document(path, max_bytes=6).text, "中文")

    def test_malformed_bom_and_unsupported_encoding_are_rejected(self):
        with self.assertRaises(UnsupportedEncodingError):
            read_document(self.write("truncated.txt", codecs.BOM_UTF16_LE + b"x"))
        with self.assertRaises(UnsupportedEncodingError):
            read_document(self.write("utf32.txt", codecs.BOM_UTF32_LE + "a".encode("utf-32-le")))
        with self.assertRaises(UnsupportedEncodingError):
            save_document(DocumentModel("text"), self.root / "unsupported.txt", encoding="ascii")
        self.assertFalse((self.root / "unsupported.txt").exists())


if __name__ == "__main__":
    unittest.main()
