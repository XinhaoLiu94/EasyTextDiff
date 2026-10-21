"""Application shell: tabs, global actions, settings and theme only."""
import sys

from PyQt5.QtCore import QSettings, Qt, QThreadPool, QTimer
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QAction, QActionGroup, QApplication, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMenu, QMessageBox, QPushButton, QShortcut, QTabBar, QTabWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from .branding import APP_NAME, DISPLAY_NAME, VERSION
from .examples import DEMO_LEFT, DEMO_RIGHT
from .icons import app_icon, icon
from .preferences import load_settings
from .presenter import SessionPresenter
from .session_view import SessionView
from .styles import DARK, LIGHT, qt_palette, stylesheet
from .widgets import tool_button

class MainWindow(QMainWindow):
    """A shell around independent comparison sessions, not a document editor."""

    def __init__(self, settings=None, dialogs_factory=None, compute=None):
        super().__init__()
        self.settings = settings if settings is not None else load_settings()
        self.dialogs_factory, self.compute = dialogs_factory, compute
        self.presenters = {}
        self._close_buttons = {}
        self._session_number = 0
        self._closing = False
        self._theme_mode = str(self.settings.value('theme', 'system'))
        if self._theme_mode not in ('system', 'light', 'dark'):
            self._theme_mode = 'system'
        self._dark = None
        self.setWindowTitle(f'{APP_NAME} · {DISPLAY_NAME}')
        self.setWindowIcon(app_icon())
        self.resize(1420, 930)
        self.setMinimumSize(1120, 720)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._build_shell()
        self._build_menus()
        self._shortcuts()
        self.apply_theme()
        self.new_comparison()
        self.system_theme_timer = QTimer(self)
        self.system_theme_timer.timeout.connect(self._poll_theme)
        self.system_theme_timer.start(4000)
        self.setFocusPolicy(Qt.StrongFocus)
        geometry = self.settings.value('geometry')
        if geometry is not None:
            self.restoreGeometry(geometry)

    @property
    def active_presenter(self):
        return self.presenters.get(self.workspace.currentWidget())

    @property
    def active_view(self):
        return self.workspace.currentWidget()

    def _build_shell(self):
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        appbar = QFrame()
        appbar.setObjectName('appbar')
        appbar.setFixedHeight(70)
        row = QHBoxLayout(appbar)
        row.setContentsMargins(26, 0, 26, 0)
        row.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(36, 36))
        row.addWidget(logo)
        title = QLabel(APP_NAME)
        title.setFont(QFont('Microsoft YaHei UI', 17, QFont.DemiBold))
        row.addWidget(title)
        english = QLabel(DISPLAY_NAME)
        english.setObjectName('subtitle')
        english.setStyleSheet('font-size:11px;')
        row.addWidget(english)
        row.addStretch()
        self.local_badge = QLabel('●  本地处理')
        row.addWidget(self.local_badge)
        row.addSpacing(12)
        self.export_button = QPushButton('  导出报告')
        self.export_button.clicked.connect(lambda: self.active_presenter.export_report())
        row.addWidget(self.export_button)
        self.theme_button = tool_button('sun', '外观：跟随系统')
        self.theme_button.setFixedSize(34, 34)
        self.theme_button.setPopupMode(QToolButton.InstantPopup)
        row.addWidget(self.theme_button)
        self.more_button = tool_button('more', '更多选项')
        self.more_button.setFixedSize(34, 34)
        self.more_button.setPopupMode(QToolButton.InstantPopup)
        row.addWidget(self.more_button)
        outer.addWidget(appbar)
        self.workspace = QTabWidget()
        self.workspace.setObjectName('workspace')
        self.workspace.setDocumentMode(True)
        self.workspace.setTabsClosable(True)
        self.workspace.setMovable(True)
        self.workspace.tabBar().setDrawBase(False)
        self.workspace.setElideMode(Qt.ElideMiddle)
        self.workspace.tabCloseRequested.connect(self.close_comparison)
        self.workspace.currentChanged.connect(self._active_changed)
        self.add_tab_button = tool_button('plus', '新建比较  Ctrl+N', self.new_comparison)
        self.workspace.setCornerWidget(self.add_tab_button, Qt.TopRightCorner)
        outer.addWidget(self.workspace, 1)

    def _build_menus(self):
        self.theme_menu = QMenu(self)
        group = QActionGroup(self)
        group.setExclusive(True)
        self.theme_actions = {}
        for mode, label in [('system', '跟随系统'), ('light', '浅色'), ('dark', '深色')]:
            action = QAction(label, self, checkable=True)
            action.triggered.connect(lambda checked, value=mode: self.set_theme(value))
            group.addAction(action)
            self.theme_menu.addAction(action)
            self.theme_actions[mode] = action
        self.theme_button.setMenu(self.theme_menu)
        menu = QMenu(self)
        menu.addAction('新建比较    Ctrl+N', self.new_comparison)
        menu.addAction('关闭当前比较    Ctrl+W', lambda: self.close_comparison(self.workspace.currentIndex()))
        menu.addSeparator()
        menu.addAction('保存当前侧    Ctrl+S', lambda: self.active_presenter.save())
        menu.addAction('当前侧另存为…    Ctrl+Shift+S', lambda: self.active_presenter.save(save_as=True))
        menu.addAction('保存左侧', lambda: self.active_presenter.save('left'))
        menu.addAction('保存右侧', lambda: self.active_presenter.save('right'))
        menu.addSeparator()
        menu.addAction('查找文字    Ctrl+F', lambda: self.active_view.show_find())
        self.wrap_action = menu.addAction('自动换行')
        self.wrap_action.setCheckable(True)
        self.wrap_action.toggled.connect(lambda enabled: self.active_view.set_wrap(enabled))
        menu.addAction('复制统一差异补丁', lambda: self.active_presenter.copy_patch())
        menu.addSeparator()
        menu.addAction(f'关于 {APP_NAME}', self.about)
        self.more_button.setMenu(menu)

    def _shortcuts(self):
        bindings = [
            ('Ctrl+Return', lambda: self.active_presenter.compare()),
            ('Ctrl+Enter', lambda: self.active_presenter.compare()),
            ('F5', lambda: self.active_presenter.compare()),
            ('F7', lambda: self.active_presenter.navigate(-1)),
            ('F8', lambda: self.active_presenter.navigate(1)),
            ('Ctrl+N', self.new_comparison),
            ('Ctrl+W', lambda: self.close_comparison(self.workspace.currentIndex())),
            ('Ctrl+S', lambda: self.active_presenter.save()),
            ('Ctrl+Shift+S', lambda: self.active_presenter.save(save_as=True)),
            ('Ctrl+O', lambda: self.active_presenter.import_file(self.active_view.active_side)),
            ('Ctrl+F', lambda: self.active_view.show_find()),
            ('Escape', lambda: self.active_view.search_box.hide()),
        ]
        self._shortcut_objects = []
        for key, callback in bindings:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self._shortcut_objects.append(shortcut)

    def new_comparison(self):
        self._session_number += 1
        view = SessionView()
        view.setProperty('session_number', self._session_number)
        view.automatic.setChecked(self.settings.value('automatic', True, type=bool))
        view.set_colors(self.colors)
        dialogs = self.dialogs_factory(view) if self.dialogs_factory else None
        presenter = SessionPresenter(view, dialogs=dialogs, pool=self.pool, compute=self.compute)
        self.presenters[view] = presenter
        presenter.stateChanged.connect(lambda p=presenter: self._session_changed(p))
        view.newRequested.connect(self.new_comparison)
        view.sampleRequested.connect(lambda p=presenter: self.load_demo(p))
        view.automaticChanged.connect(lambda enabled: self.settings.setValue('automatic', enabled))
        index = self.workspace.addTab(view, self._tab_title(presenter))
        close_button = tool_button('close', '关闭此比较',
            lambda: self.close_comparison(self.workspace.indexOf(view)))
        close_button.setFixedSize(22, 22)
        close_button.setIcon(icon('close', self.colors['secondary'], 14))
        old_button = self.workspace.tabBar().tabButton(index, QTabBar.RightSide)
        self.workspace.tabBar().setTabButton(index, QTabBar.RightSide, close_button)
        if old_button is not None:
            old_button.deleteLater()
        self._close_buttons[view] = close_button
        self.workspace.setCurrentIndex(index)
        self._active_changed(index)
        self.setFocus()
        return presenter

    def _tab_title(self, presenter):
        if presenter.model.left.path is None and presenter.model.right.path is None:
            return ('● ' if presenter.modified else '') + f'比较 {presenter.view.property("session_number")}'
        return presenter.title

    def _session_changed(self, presenter):
        index = self.workspace.indexOf(presenter.view)
        if index >= 0:
            self.workspace.setTabText(index, self._tab_title(presenter))
            self.workspace.setTabToolTip(index, presenter.title)
        if presenter is self.active_presenter:
            self.export_button.setEnabled(presenter.can_export)

    def _active_changed(self, index):
        presenter = self.active_presenter
        self.export_button.setEnabled(bool(presenter and presenter.can_export))
        if presenter:
            self.wrap_action.blockSignals(True)
            self.wrap_action.setChecked(presenter.view.wrapping)
            self.wrap_action.blockSignals(False)

    def close_comparison(self, index):
        view = self.workspace.widget(index)
        presenter = self.presenters.get(view)
        if presenter is None or not presenter.can_close():
            return False
        presenter.dispose()
        del self.presenters[view]
        self._close_buttons.pop(view, None)
        self.workspace.removeTab(index)
        view.deleteLater()
        if not self.presenters and not self._closing:
            self.new_comparison()
        return True

    def load_demo(self, presenter=None):
        presenter = presenter if isinstance(presenter, SessionPresenter) else self.active_presenter
        if presenter.model.left.text or presenter.model.right.text:
            presenter = self.new_comparison()
        presenter.load_example(DEMO_LEFT, DEMO_RIGHT)
        return presenter

    def _system_dark(self):
        if sys.platform == 'win32':
            try:
                settings = QSettings(r'HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize', QSettings.NativeFormat)
                return int(settings.value('AppsUseLightTheme', 1)) == 0
            except (TypeError, ValueError):
                pass
        return self.style().standardPalette().window().color().lightness() < 128

    def _poll_theme(self):
        if self._theme_mode == 'system' and self._system_dark() != self._dark:
            self.apply_theme()

    def set_theme(self, mode):
        self._theme_mode = mode
        self.settings.setValue('theme', mode)
        self.apply_theme()

    def apply_theme(self):
        self._dark = self._system_dark() if self._theme_mode == 'system' else self._theme_mode == 'dark'
        self.colors = DARK if self._dark else LIGHT
        application = QApplication.instance()
        application.setPalette(qt_palette(self.colors))
        application.setStyleSheet(stylesheet(self.colors))
        for view in self.presenters:
            view.set_colors(self.colors)
            if view in self._close_buttons:
                self._close_buttons[view].setIcon(icon('close', self.colors['secondary'], 14))
        self.local_badge.setStyleSheet(f'color:{self.colors["accent"]};font-size:11px;')
        for button, name in ((self.export_button, 'download'), (self.more_button, 'more'), (self.add_tab_button, 'plus')):
            button.setIcon(icon(name, self.colors['secondary'], 18))
        self.theme_button.setIcon(icon('moon' if self._dark else 'sun', self.colors['secondary'], 19))
        self.theme_button.setToolTip('外观：' + {'system':'跟随系统','light':'浅色','dark':'深色'}[self._theme_mode])
        self.theme_actions[self._theme_mode].setChecked(True)
        if sys.platform == 'win32':
            try:
                import ctypes
                value = ctypes.c_int(int(self._dark))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 20, ctypes.byref(value), ctypes.sizeof(value))
            except (AttributeError, OSError):
                pass

    def about(self):
        QMessageBox.about(self, f'关于 {APP_NAME}',
            f'{APP_NAME} {VERSION}\n{DISPLAY_NAME}\n\n默认粘贴输入的本地文本对比工具。\n'
            '支持多标签、语法高亮、差异概览和原格式保存。\n\n'
            '独立的 PyQt5 实现，未包含 WinMerge 源码。\nGPL-3.0-or-later。')

    def closeEvent(self, event):
        # Confirm every tab before removing any of them.
        for view, presenter in tuple(self.presenters.items()):
            if not presenter.can_close():
                self.workspace.setCurrentWidget(view)
                event.ignore()
                return
        self._closing = True
        self.settings.setValue('geometry', self.saveGeometry())
        self.system_theme_timer.stop()
        for presenter in self.presenters.values():
            presenter.dispose()
        self.pool.clear()
        self.pool.waitForDone(1500)
        event.accept()
