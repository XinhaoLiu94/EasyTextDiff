import unittest


from easytextdiff.diff_engine import (DiffOptions, Span, apply_change, compare_texts,
                         export_unified, split_lines)


class DiffEngineTests(unittest.TestCase):
    def test_empty_and_newline_normalization(self):
        self.assertEqual(split_lines(""), ())
        self.assertEqual(split_lines("a\r\nb\rc\n"), ("a", "b", "c", ""))
        self.assertTrue(compare_texts("a\r\nb\r", "a\nb\n").identical)
        self.assertTrue(compare_texts("", "").identical)

    def test_terminal_newline_is_a_real_change(self):
        result = compare_texts("a", "a\n")
        self.assertFalse(result.identical)
        self.assertEqual(result.added_lines, 1)
        self.assertEqual(apply_change(result, 0, "left"), "a\n")
        self.assertEqual(apply_change(result, 0, "right"), "a")
        blank = compare_texts("", "\n")
        self.assertEqual(apply_change(blank, 0, "left"), "\n")
        self.assertEqual(apply_change(blank, 0, "right"), "")

    def test_replacement_counts_and_positions(self):
        result = compare_texts("head\nold\nend", "head\nnew\nextra\nend")
        self.assertEqual((result.modified_lines, result.added_lines, result.deleted_lines),
                         (1, 1, 0))
        self.assertEqual([row.kind for row in result.rows],
                         ["equal", "replace", "insert", "equal"])
        change = result.changes[0]
        self.assertEqual((change.start_row, change.end_row), (1, 3))
        self.assertEqual((change.left_start, change.left_end,
                          change.right_start, change.right_end), (1, 2, 1, 3))
        self.assertEqual(result.rows[2].left_index, None)
        self.assertEqual(result.rows[2].right_index, 2)

    def test_insert_delete_and_merge_both_directions(self):
        pairs = [("", "one\ntwo"), ("one\ntwo", ""),
                 ("a\nb\nc", "a\nx\nc"),
                 ("a\nb", "a\ninsert\nb"),
                 ("a\nremove\nb", "a\nb"),
                 ("\n", ""), ("", "\n"), ("a\n\n", "a\n")]
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                result = compare_texts(left, right)
                self.assertEqual(result.total_changes, 1)
                self.assertEqual(apply_change(result, 0, "left"), right)
                self.assertEqual(apply_change(result, 0, "right"), left)

    def test_reordered_lines_keep_each_source_index_once(self):
        result = compare_texts("a\nb\nc\nd", "c\na\nb\nd")
        self.assertFalse(result.identical)
        self.assertEqual([row.left_index for row in result.rows if row.left_index is not None],
                         list(range(4)))
        self.assertEqual([row.right_index for row in result.rows if row.right_index is not None],
                         list(range(4)))
        self.assertEqual((result.added_lines, result.deleted_lines, result.modified_lines),
                         (1, 1, 0))

    def test_unicode_spans_are_codepoint_offsets(self):
        result = compare_texts("前😀旧后", "前😀新后")
        row = result.rows[0]
        self.assertEqual(row.left_spans, (Span(2, 3),))
        self.assertEqual(row.right_spans, (Span(2, 3),))
        self.assertEqual("前😀旧后"[row.left_spans[0].start:row.left_spans[0].end], "旧")

    def test_character_insert_does_not_mark_unchanged_source(self):
        row = compare_texts("甲乙", "甲😀乙").rows[0]
        self.assertEqual(row.left_spans, ())
        self.assertEqual(row.right_spans, (Span(1, 2),))

    def test_ignore_options_preserve_raw_text(self):
        options = DiffOptions(ignore_whitespace=True, ignore_case=True)
        result = compare_texts("Straße\t A", "STRASSE a", options)
        self.assertTrue(result.identical)
        self.assertEqual(result.left_lines, ("Straße\t A",))
        self.assertEqual(result.right_lines, ("STRASSE a",))
        changed = compare_texts("Straße\t X", "STRASSE y", options)
        self.assertEqual(changed.rows[0].left_spans, (Span(8, 9),))
        self.assertEqual(changed.rows[0].right_spans, (Span(8, 9),))
        self.assertEqual(apply_change(changed, 0, "left"), "STRASSE y")

    def test_ignored_characters_alone_have_no_spans(self):
        self.assertTrue(compare_texts("A B", "ab", DiffOptions(True, True)).identical)
        self.assertTrue(compare_texts("x\u3000y", "xy", DiffOptions(True)).identical)
        row = compare_texts("ß", "st", DiffOptions(ignore_case=True)).rows[0]
        self.assertEqual(row.left_spans, (Span(0, 1),))
        self.assertEqual(row.right_spans, (Span(1, 2),))

    def test_multiple_hunks_merge_only_selected_original_range(self):
        result = compare_texts("a\nold\nkeep\nlast", "a\nnew\nkeep\nLAST")
        self.assertEqual(result.total_changes, 2)
        self.assertEqual(apply_change(result, 1, "left"), "a\nold\nkeep\nLAST")
        self.assertEqual(apply_change(result, 0, "right"), "a\nold\nkeep\nLAST")

    def test_patch_missing_newline_never_concatenates_changes(self):
        patch = export_unified("old", "new", "left.txt", "right.txt")
        self.assertEqual(patch, "--- left.txt\n+++ right.txt\n@@ -1 +1 @@\n"
                         "-old\n\\ No newline at end of file\n"
                         "+new\n\\ No newline at end of file\n")
        self.assertIn("-a\n\\ No newline at end of file\n+a\n",
                      export_unified("a", "a\n"))
        self.assertEqual(export_unified("a\r\nb\r", "a\nb\n"), "")

    def test_patch_preserves_blank_lines(self):
        patch = export_unified("a\n\nb\n", "a\n\nB\n")
        self.assertIn(" a\n \n-b\n+B\n", patch)
        self.assertIn("+\n", export_unified("", "\n"))
        self.assertNotIn("No newline", export_unified("", "\n"))

    def test_bounded_fallback_keeps_content_and_spans(self):
        left = "a" * 20000 + "中" + "b" * 20000
        right = "a" * 20000 + "文" + "b" * 20000
        row = compare_texts(left, right).rows[0]
        self.assertEqual(row.left_spans, (Span(20000, 20001),))
        a = "\n".join(["a"] * 2500)
        b = "\n".join(["b"] * 2500)
        result = compare_texts(a, b)
        self.assertEqual(result.modified_lines, 2500)
        self.assertEqual(apply_change(result, 0, "left"), b)
        self.assertTrue(compare_texts(a, a).identical)

    def test_bad_merge_arguments(self):
        result = compare_texts("a", "b")
        with self.assertRaises(ValueError):
            apply_change(result, 0, "up")
        for index in (-1, 1):
            with self.assertRaises(IndexError):
                apply_change(result, index, "left")


if __name__ == "__main__":
    unittest.main()
