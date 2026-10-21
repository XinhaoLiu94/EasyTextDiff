"""Small vector icons drawn locally with Qt; no external asset dependencies."""
from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtGui import QPainter

PATHS = {
    'paste': '<rect x="6" y="5" width="12" height="16" rx="2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 11h6m-6 4h6"/>',
    'file': '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 14h8m-8 3h5"/>',
    'copy': '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3"/>',
    'clear': '<path d="M4 6h16M9 6V4h6v2M6 6l1 14h10l1-14M10 10v6m4-6v6"/>',
    'swap': '<path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"/>',
    'compare': '<path d="M4 7h15m-4-4 4 4-4 4M20 17H5m4-4-4 4 4 4"/>',
    'left': '<path d="m14 6-6 6 6 6M8 12h12"/>',
    'right': '<path d="m10 6 6 6-6 6M4 12h12"/>',
    'up': '<path d="m6 14 6-6 6 6"/>',
    'down': '<path d="m6 10 6 6 6-6"/>',
    'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    'moon': '<path d="M20.5 13A8.5 8.5 0 0 1 11 3.5 8.5 8.5 0 1 0 20.5 13Z"/>',
    'more': '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    'download': '<path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4"/>',
    'search': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    'close': '<path d="m6 6 12 12M6 18 18 6"/>',
    'link': '<path d="m10 13 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m0 2 1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" transform="translate(2 0)"/>',
    'sample': '<path d="m8 5-6 7 6 7m8-14 6 7-6 7M14 3l-4 18"/>',
    'plus': '<path d="M12 4v16M4 12h16"/>',
    'check': '<path d="m5 12 4 4L19 6"/>',
}


def icon(name, color='#637572', size=20):
    body = PATHS.get(name, PATHS['file'])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
           f'fill="none" stroke="{color}" stroke-width="1.65" stroke-linecap="round" '
           f'stroke-linejoin="round">{body}</svg>')
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def app_icon(size=64):
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
    <rect width="64" height="64" rx="17" fill="#176F64"/>
    <path d="M26 17H17v30h9M38 17h9v30h-9" fill="none" stroke="#E9FFF8" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
    <rect x="27" y="25" width="16" height="4" rx="2" fill="#A4DFCA"/>
    <rect x="21" y="35" width="16" height="4" rx="2" fill="#E9FFF8"/>
    </svg>'''
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    return QIcon(pixmap)
