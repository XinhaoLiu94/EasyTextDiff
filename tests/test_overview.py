"""Diff overview paints engine changes and reports aligned navigation rows."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication

from easytextdiff.diff_engine import compare_texts, DiffOptions
from easytextdiff.overview import DiffOverview


class OverviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication(["overview-tests"])

    def setUp(self):
        self.overview = DiffOverview()
        self.overview.resize(18, 210)
        self.overview.show()
        self.application.processEvents()

    def tearDown(self):
        self.overview.close()
        self.overview.deleteLater()
        self.application.processEvents()

    def result(self, left="a\nb\nc", right="a\nX\nc"):
        result = compare_texts(left, right, DiffOptions())
        self.overview.set_result(result)
        return result

    def test_empty_overview_does_not_emit_navigation(self):
        spy = QSignalSpy(self.overview.activated)
        QTest.mouseClick(self.overview, Qt.LeftButton, pos=QPoint(9, 100))
        self.assertEqual(len(spy), 0)

    def test_click_maps_to_aligned_row_not_change_index(self):
        result = self.result("\n".join(map(str, range(100))), "\n".join(map(str, range(99))))
        spy = QSignalSpy(self.overview.activated)
        QTest.mouseClick(self.overview, Qt.LeftButton, pos=QPoint(9, 105))
        self.assertEqual(list(spy[-1]), [50])
        self.assertEqual(len(result.changes), 1)

    def test_track_edges_clamp_to_first_and_last_row(self):
        self.result()
        spy = QSignalSpy(self.overview.activated)
        QTest.mouseClick(self.overview, Qt.LeftButton, pos=QPoint(9, 0))
        QTest.mouseClick(self.overview, Qt.LeftButton, pos=QPoint(9, 209))
        self.assertEqual([list(event) for event in spy], [[0], [2]])

    def test_keyboard_navigation_uses_aligned_rows(self):
        self.result()
        spy = QSignalSpy(self.overview.activated)
        QTest.keyClick(self.overview, Qt.Key_End)
        QTest.keyClick(self.overview, Qt.Key_Up)
        QTest.keyClick(self.overview, Qt.Key_Home)
        self.assertEqual([list(event) for event in spy], [[2], [1], [0]])

    def test_current_hunk_and_viewport_ranges_are_safely_clamped(self):
        self.result()
        self.overview.set_current_change(0)
        self.assertEqual(self.overview._current_change, 0)
        self.overview.set_current_change(100)
        self.assertEqual(self.overview._current_change, -1)
        self.overview.set_visible_rows(-100, 100)
        self.assertEqual(self.overview._visible_rows, (0, 3))
        self.overview.set_result(None)
        self.assertIsNone(self.overview._visible_rows)

    def test_replacement_marker_paints_both_delete_and_add_colors(self):
        self.result()
        self.overview.set_colors({"bg": "#FFFFFF", "red": "#DD3322", "green": "#22AA55"})
        self.application.processEvents()
        image = self.overview.grab().toImage()
        self.assertEqual(image.pixelColor(5, 105).name(), "#dd3322")
        self.assertEqual(image.pixelColor(12, 105).name(), "#22aa55")


if __name__ == "__main__":
    unittest.main()
