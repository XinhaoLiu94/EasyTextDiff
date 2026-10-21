"""Debounced, versioned comparison jobs. Workers never access Qt widgets."""
from threading import Event

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal

from .diff_engine import compare_texts


class _JobSignals(QObject):
    finished = pyqtSignal(int, object, str)


class _CompareJob(QRunnable):
    def __init__(self, revision, snapshot, compute):
        super().__init__()
        self.revision, self.snapshot, self.compute = revision, snapshot, compute
        self.signals = _JobSignals()
        self.cancelled = Event()

    def run(self):
        result, error = None, ''
        try:
            if not self.cancelled.is_set():
                result = self.compute(*self.snapshot)
        except Exception as exception:
            error = str(exception)
        self.signals.finished.emit(self.revision, result, error)


class CompareCoordinator(QObject):
    """Publish only the latest snapshot; pending denotes the debounce timer.

    busy denotes a running current job, not superseded jobs still completing.
    dispose never clears a shared pool or blocks the GUI waiting for old work.
    """

    resultReady = pyqtSignal(object)
    failed = pyqtSignal(str)
    busyChanged = pyqtSignal(bool)

    def __init__(self, parent=None, pool=None, compute=None):
        super().__init__(parent)
        self.pool = pool if pool is not None else QThreadPool.globalInstance()
        self.compute = compute if compute is not None else compare_texts
        self._revision = 0
        self._busy = False
        self._disposed = False
        self._snapshot = None
        self._jobs = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start)

    @property
    def revision(self):
        return self._revision

    @property
    def busy(self):
        return self._busy

    @property
    def pending(self):
        return self._timer.isActive()

    def _set_busy(self, busy):
        if self._busy != busy:
            self._busy = busy
            self.busyChanged.emit(busy)

    def invalidate(self):
        self._revision += 1
        self._timer.stop()
        self._snapshot = None
        for job in self._jobs.values():
            job.cancelled.set()
        self._set_busy(False)

    def request(self, left, right, options, delay_ms=0):
        if self._disposed:
            raise RuntimeError('Cannot request work after disposing a comparison.')
        self.invalidate()
        self._snapshot = (left, right, options)
        if delay_ms > 0:
            self._timer.start(int(delay_ms))
        else:
            self._start()
        return self._revision

    def _start(self):
        if self._disposed or self._snapshot is None:
            return
        snapshot, self._snapshot = self._snapshot, None
        job = _CompareJob(self._revision, snapshot, self.compute)
        self._jobs[self._revision] = job
        job.signals.finished.connect(self._finished)
        self._set_busy(True)
        self.pool.start(job)

    def _finished(self, revision, result, error):
        self._jobs.pop(revision, None)
        if self._disposed or revision != self._revision:
            return
        self._set_busy(False)
        if error:
            self.failed.emit(error)
        elif result is not None:
            self.resultReady.emit(result)

    def dispose(self):
        self._disposed = True
        self.invalidate()
