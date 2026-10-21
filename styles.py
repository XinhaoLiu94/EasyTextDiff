from PyQt5.QtGui import QColor, QPalette

LIGHT = dict(
    canvas='#F3F6F5', bg='#FFFFFF', text='#1D302E', muted='#7B8986',
    secondary='#546863', gutter_bg='#FAFCFB', gutter_text='#9CA9A5', border='#DFE7E3',
    accent='#176F64', accent_hover='#105D53', accent_soft='#E8F3EE', selection='#CFE7DE',
    placeholder_bg='#F2F7F4', toolbar='#E9EFEC', added_bg='#EAF6EE', deleted_bg='#FFF0ED',
    added_inline='#AFDEBF', deleted_inline='#F3BDB3', green='#278554', red='#BC6253',
    warning='#A87C35', active='#E2F0E9',
)
DARK = dict(
    canvas='#141B1A', bg='#1C2523', text='#DFEAE5', muted='#8C9D96',
    secondary='#ADC0B6', gutter_bg='#19221F', gutter_text='#63796D', border='#34433B',
    accent='#76D3AE', accent_hover='#95E4C4', accent_soft='#233E31', selection='#355647',
    placeholder_bg='#24332B', toolbar='#222F28', added_bg='#213D2C', deleted_bg='#422D28',
    added_inline='#356448', deleted_inline='#7C4539', green='#8CD4A3', red='#E5A091',
    warning='#D7B579', active='#2C4839',
)


def qt_palette(c):
    palette = QPalette()
    for role, value in (
        (QPalette.Window, c['canvas']), (QPalette.WindowText, c['text']),
        (QPalette.Base, c['bg']), (QPalette.AlternateBase, c['gutter_bg']),
        (QPalette.Text, c['text']), (QPalette.Button, c['bg']),
        (QPalette.ButtonText, c['text']), (QPalette.Highlight, c['selection']),
        (QPalette.HighlightedText, c['text']), (QPalette.ToolTipBase, c['bg']),
        (QPalette.ToolTipText, c['text']),
        (QPalette.Light, c['border']), (QPalette.Midlight, c['border']),
        (QPalette.Dark, c['muted']), (QPalette.Mid, c['border']),
        (QPalette.Shadow, c['secondary']),
    ):
        palette.setColor(role, QColor(value))
    return palette


def stylesheet(c):
    return f'''
    QWidget {{ color:{c['text']}; }}
    QMainWindow, QWidget#root {{ background:{c['canvas']}; }}
    QLabel {{ background:transparent; border:0; }}
    QLabel#muted, QLabel#subtitle {{ color:{c['muted']}; }}
    QLabel#subtitle {{ font-size:12px; }}
    QFrame#appbar {{ background:{c['bg']}; border:0; border-bottom:1px solid {c['border']}; }}
    QFrame#card {{ background:{c['bg']}; border:1px solid {c['border']}; border-radius:13px; }}
    QFrame#paneHeader {{ background:transparent; border:0; border-bottom:1px solid {c['border']}; }}
    QFrame#paneFooter {{ background:transparent; border:0; border-top:1px solid {c['border']}; }}
    QFrame#segmented {{ background:{c['toolbar']}; border:1px solid {c['border']}; border-radius:9px; }}
    QFrame#searchBox {{ background:{c['bg']}; border:1px solid {c['border']}; border-radius:9px; }}
    QPushButton {{ background:{c['bg']}; border:1px solid {c['border']}; border-radius:7px; padding:8px 14px; font-size:12px; font-weight:500; }}
    QPushButton:hover {{ background:{c['gutter_bg']}; border-color:{c['muted']}; }}
    QPushButton:pressed {{ background:{c['toolbar']}; }}
    QPushButton:disabled {{ color:{c['gutter_text']}; border-color:{c['border']}; }}
    QPushButton#primary {{ background:{c['accent']}; border:1px solid {c['accent']}; color:{c['bg']}; padding:9px 19px; font-weight:600; }}
    QPushButton#primary:hover {{ background:{c['accent_hover']}; border-color:{c['accent_hover']}; }}
    QPushButton#primary:disabled {{ background:{c['toolbar']}; color:{c['muted']}; border-color:{c['border']}; }}
    QPushButton#quiet {{ background:transparent; border:0; color:{c['secondary']}; padding:7px 10px; }}
    QPushButton#quiet:hover {{ background:{c['toolbar']}; }}
    QPushButton#segment {{ background:transparent; border:0; color:{c['secondary']}; border-radius:6px; padding:6px 16px; }}
    QPushButton#segment:checked {{ background:{c['bg']}; color:{c['accent']}; font-weight:600; }}
    QPushButton#segment:disabled {{ color:{c['gutter_text']}; }}
    QToolButton {{ background:transparent; border:0; border-radius:6px; padding:6px; color:{c['secondary']}; }}
    QToolButton:hover {{ background:{c['toolbar']}; }}
    QToolButton:pressed, QToolButton:checked {{ background:{c['accent_soft']}; color:{c['accent']}; }}
    QToolButton:disabled {{ color:{c['gutter_text']}; }}
    QToolButton#mergeButton {{ background:{c['bg']}; border:1px solid {c['border']}; border-radius:8px; padding:5px; }}
    QToolButton#mergeButton:hover {{ border-color:{c['accent']}; background:{c['accent_soft']}; }}
    QCheckBox {{ spacing:6px; font-size:12px; color:{c['secondary']}; }}
    QCheckBox::indicator {{ width:15px; height:15px; }}
    QComboBox {{ background:{c['bg']}; color:{c['secondary']}; border:1px solid {c['border']}; border-radius:5px; padding:3px 6px; font-size:11px; }}
    QComboBox:hover {{ border-color:{c['muted']}; }}
    QComboBox::drop-down {{ border:0; width:14px; }}
    QComboBox QAbstractItemView {{ background:{c['bg']}; color:{c['text']}; selection-background-color:{c['accent_soft']}; border:1px solid {c['border']}; }}
    QTabWidget#workspace::pane {{ border:0; background:{c['canvas']}; }}
    QTabWidget#workspace QTabBar {{ background:{c['canvas']}; }}
    QTabBar::tab {{ background:transparent; color:{c['secondary']}; padding:10px 16px; min-width:105px; max-width:260px; border:0; border-bottom:2px solid transparent; font-size:12px; }}
    QTabBar::tab:selected {{ color:{c['accent']}; background:{c['bg']}; border-bottom:2px solid {c['accent']}; }}
    QTabBar::tab:hover {{ background:{c['toolbar']}; }}
    QPlainTextEdit {{ background:{c['bg']}; color:{c['text']}; border:0; selection-background-color:{c['selection']}; selection-color:{c['text']}; }}
    QLineEdit {{ background:transparent; color:{c['text']}; border:0; padding:7px 8px; font-size:12px; selection-background-color:{c['selection']}; }}
    QScrollBar:vertical {{ background:transparent; width:9px; margin:3px 1px; }}
    QScrollBar::handle:vertical {{ background:{c['border']}; min-height:32px; border-radius:3px; }}
    QScrollBar::handle:vertical:hover {{ background:{c['muted']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
    QScrollBar:horizontal {{ background:transparent; height:9px; margin:1px 3px; }}
    QScrollBar::handle:horizontal {{ background:{c['border']}; min-width:32px; border-radius:3px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background:transparent; }}
    QMenu {{ background:{c['bg']}; color:{c['text']}; border:1px solid {c['border']}; border-radius:8px; padding:6px; }}
    QMenu::item {{ padding:8px 28px 8px 12px; border-radius:5px; }}
    QMenu::item:selected {{ background:{c['accent_soft']}; }}
    QMenu::separator {{ height:1px; background:{c['border']}; margin:5px; }}
    QToolTip {{ background:{c['bg']}; color:{c['text']}; border:1px solid {c['border']}; padding:5px; }}
    QMessageBox {{ background:{c['bg']}; }}
    '''
