"""Deterministic coordinator checks using gated workers and a local pool."""

import os
from threading import Event
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, QEventLoop, QThreadPool, QTimer
from PyQt5.QtWidgets import QApplication

from easytextdiff.diff_engine import DiffOptions
from easytextdiff.tasks import CompareCoordinator


class CompareCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication(["easytextdiff-task-tests"])
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(2)
        self.coordinators = []
        self.gates = []

    def tearDown(self):
        for gate in self.gates:
            gate.set()
        for coordinator in self.coordinators:
            coordinator.dispose()
        self.assertTrue(self.pool.waitForDone(3000), "Test worker did not finish")
        self.application.processEvents()
        for coordinator in self.coordinators:
            coordinator.deleteLater()
        self.pool.deleteLater()
        self.application.sendPostedEvents(None, QEvent.DeferredDelete)
        self.application.processEvents()

    def coordinator(self, compute):
        coordinator = CompareCoordinator(pool=self.pool, compute=compute)
        self.coordinators.append(coordinator)
        return coordinator

    def wait_for(self, predicate, timeout=2000):
        if predicate():
            return
        loop = QEventLoop()
        poll, deadline = QTimer(), QTimer()
        poll.setInterval(2)
        deadline.setSingleShot(True)
        poll.timeout.connect(lambda: loop.quit() if predicate() else None)
        deadline.timeout.connect(loop.quit)
        poll.start()
        deadline.start(timeout)
        loop.exec_()
        poll.stop()
        deadline.stop()
        self.assertTrue(predicate(), "Coordinator operation timed out")

    def test_debounce_runs_only_latest_snapshot(self):
        calls, results = [], []

        def compute(left, right, options):
            calls.append((left, right, options))
            return (left, right)

        coordinator = self.coordinator(compute)
        coordinator.resultReady.connect(results.append)
        options = DiffOptions(ignore_case=True)
        first = coordinator.request("old left", "old right", DiffOptions(), delay_ms=200)
        latest = coordinator.request("latest left", "latest right", options, delay_ms=20)
        self.assertGreater(latest, first)
        self.assertTrue(coordinator.pending)
        self.assertFalse(coordinator.busy)
        self.assertEqual(calls, [])
        self.wait_for(lambda: len(results) == 1)
        self.assertEqual(calls, [("latest left", "latest right", options)])
        self.assertEqual(results, [("latest left", "latest right")])
        self.assertFalse(coordinator.pending)
        self.assertFalse(coordinator.busy)

    def test_running_stale_result_cannot_replace_newer_result(self):
        started, release = Event(), Event()
        self.gates.append(release)
        results, errors = [], []

        def compute(left, right, options):
            if left == "old":
                started.set()
                if not release.wait(2):
                    raise RuntimeError("Test gate timed out")
            return left

        coordinator = self.coordinator(compute)
        coordinator.resultReady.connect(results.append)
        coordinator.failed.connect(errors.append)
        coordinator.request("old", "", DiffOptions())
        self.wait_for(started.is_set)
        coordinator.request("new", "", DiffOptions())
        self.wait_for(lambda: results == ["new"])
        # The old worker is still running when the current result is published.
        self.assertFalse(release.is_set())
        self.assertFalse(coordinator.busy)
        release.set()
        self.assertTrue(self.pool.waitForDone(2000))
        self.application.processEvents()
        self.assertEqual(results, ["new"])
        self.assertEqual(errors, [])
        self.assertFalse(coordinator.busy)

    def test_dispose_returns_while_worker_runs_and_ignores_its_result(self):
        started, release, finished = Event(), Event(), Event()
        self.gates.append(release)
        results, errors = [], []

        def compute(left, right, options):
            started.set()
            if not release.wait(2):
                raise RuntimeError("Test gate timed out")
            finished.set()
            return "obsolete result"

        coordinator = self.coordinator(compute)
        coordinator.resultReady.connect(results.append)
        coordinator.failed.connect(errors.append)
        coordinator.request("old", "", DiffOptions())
        self.wait_for(started.is_set)
        coordinator.dispose()
        self.assertFalse(finished.is_set(), "Dispose waited for an unfinished worker")
        self.assertFalse(coordinator.busy)
        self.assertFalse(coordinator.pending)
        with self.assertRaises(RuntimeError):
            coordinator.request("new", "", DiffOptions())
        release.set()
        self.assertTrue(self.pool.waitForDone(2000))
        self.application.processEvents()
        self.assertTrue(finished.is_set())
        self.assertEqual(results, [])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
