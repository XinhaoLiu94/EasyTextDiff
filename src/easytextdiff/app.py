"""EasyTextDiff application entry point and dependency assembly."""
import argparse
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from .branding import APP_NAME, DISPLAY_NAME, VERSION
from .icons import app_icon
from .main_window import MainWindow


def create_application(argv=None):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    application = QApplication(argv or sys.argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(f'{APP_NAME} · {DISPLAY_NAME}')
    application.setApplicationVersion(VERSION)
    application.setOrganizationName(APP_NAME)
    application.setStyle('Fusion')
    application.setFont(QFont('Microsoft YaHei UI', 10))
    application.setWindowIcon(app_icon())
    return application


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='*', help='Optional left and right text files')
    parser.add_argument('--demo', action='store_true', help='Open the built-in example')
    args = parser.parse_args()
    application = create_application()
    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.setFocus)
    for side, path in zip(('left', 'right'), args.files[:2]):
        window.active_presenter.import_file(side, path)
    if args.demo:
        QTimer.singleShot(150, window.load_demo)
    return application.exec_()


if __name__ == '__main__':
    sys.exit(main())
