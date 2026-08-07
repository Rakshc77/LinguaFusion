"""Small original line-icon system for the LinguaFusion desktop UI.

Icons are painted with Qt at 2x resolution, so they stay crisp without font,
emoji, theme, or external SVG dependencies.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _paint_icon(name: str, color: str, size: int) -> QPixmap:
    dpr = 2
    canvas = max(16, int(size)) * dpr
    pixmap = QPixmap(canvas, canvas)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpr)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    # QPainter already works in device-independent pixels after DPR is set.
    # Scale from the requested logical size, not the physical 2x canvas; using
    # the latter clips every icon to its upper-left quadrant on high-DPI output.
    painter.scale(max(16, int(size)) / 24.0, max(16, int(size)) / 24.0)
    pen = QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    def line(x1, y1, x2, y2):
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def rect(x, y, width, height, radius=0.0):
        painter.drawRoundedRect(QRectF(x, y, width, height), radius, radius)

    def ellipse(x, y, width, height):
        painter.drawEllipse(QRectF(x, y, width, height))

    if name == "translate":
        rect(3, 4, 8, 11, 1.2)
        rect(9, 9, 12, 11, 1.2)
        line(5, 7, 9, 7)
        line(7, 5, 7, 9)
        line(13, 13, 18, 13)
        line(15.5, 11, 15.5, 15)
        line(12.5, 17, 18.5, 17)
    elif name == "reader":
        path = QPainterPath(QPointF(4, 4))
        path.lineTo(10, 4)
        path.quadTo(12, 4, 12, 6)
        path.quadTo(12, 4, 14, 4)
        path.lineTo(20, 4)
        path.lineTo(20, 19)
        path.lineTo(14, 19)
        path.quadTo(12, 19, 12, 21)
        path.quadTo(12, 19, 10, 19)
        path.lineTo(4, 19)
        path.closeSubpath()
        painter.drawPath(path)
        line(12, 6, 12, 19)
    elif name == "microphone":
        rect(8, 3, 8, 12, 4)
        path = QPainterPath(QPointF(5, 11))
        path.cubicTo(5, 16, 8, 19, 12, 19)
        path.cubicTo(16, 19, 19, 16, 19, 11)
        painter.drawPath(path)
        line(12, 19, 12, 22)
        line(9, 22, 15, 22)
    elif name == "scan":
        line(4, 9, 4, 5); line(4, 5, 8, 5)
        line(16, 5, 20, 5); line(20, 5, 20, 9)
        line(20, 15, 20, 19); line(20, 19, 16, 19)
        line(8, 19, 4, 19); line(4, 19, 4, 15)
        rect(7, 8, 10, 8, 1.2)
        line(9, 11, 15, 11); line(9, 14, 13, 14)
    elif name == "notes":
        rect(5, 3, 14, 18, 1.5)
        line(8, 8, 16, 8); line(8, 12, 16, 12); line(8, 16, 13, 16)
    elif name == "settings":
        ellipse(9, 9, 6, 6)
        for x1, y1, x2, y2 in [(12,2,12,5),(12,19,12,22),(2,12,5,12),(19,12,22,12),(5,5,7,7),(17,17,19,19),(17,7,19,5),(5,19,7,17)]:
            line(x1, y1, x2, y2)
        ellipse(5, 5, 14, 14)
    elif name in {"upload", "download"}:
        line(4, 19, 20, 19); line(4, 19, 4, 15); line(20, 19, 20, 15)
        if name == "upload":
            line(12, 16, 12, 5); line(8, 9, 12, 5); line(16, 9, 12, 5)
        else:
            line(12, 5, 12, 16); line(8, 12, 12, 16); line(16, 12, 12, 16)
    elif name == "search":
        ellipse(4, 4, 11, 11); line(13, 13, 20, 20)
    elif name == "swap":
        line(5, 8, 18, 8); line(15, 5, 18, 8); line(15, 11, 18, 8)
        line(19, 16, 6, 16); line(9, 13, 6, 16); line(9, 19, 6, 16)
    elif name == "copy":
        rect(8, 8, 11, 12, 1.2); rect(4, 4, 11, 12, 1.2)
    elif name == "trash":
        line(5, 7, 19, 7); line(9, 4, 15, 4); rect(7, 7, 10, 14, 1)
        line(10, 11, 10, 17); line(14, 11, 14, 17)
    elif name == "file":
        path = QPainterPath(QPointF(6, 3)); path.lineTo(14, 3); path.lineTo(19, 8); path.lineTo(19, 21); path.lineTo(6, 21); path.closeSubpath(); painter.drawPath(path)
        line(14, 3, 14, 8); line(14, 8, 19, 8)
    elif name == "save":
        rect(4, 3, 16, 18, 1.5); rect(8, 4, 8, 6, 0.8); rect(7, 14, 10, 7, 0.8)
    elif name == "panel":
        rect(3, 4, 18, 16, 1.5); line(15, 4, 15, 20); line(17.5, 10, 19, 12); line(19, 12, 17.5, 14)
    elif name in {"chevron-left", "chevron-right"}:
        if name.endswith("left"):
            line(15, 5, 8, 12); line(8, 12, 15, 19)
        else:
            line(9, 5, 16, 12); line(16, 12, 9, 19)
    elif name == "history":
        path = QPainterPath(QPointF(5, 8)); path.cubicTo(8, 3, 16, 3, 19, 8); path.cubicTo(23, 15, 17, 21, 11, 20); path.cubicTo(7, 20, 4, 17, 4, 13); painter.drawPath(path)
        line(5, 4, 5, 8); line(5, 8, 9, 8); line(12, 8, 12, 13); line(12, 13, 16, 15)
    elif name == "play":
        path = QPainterPath(QPointF(8, 5)); path.lineTo(19, 12); path.lineTo(8, 19); path.closeSubpath(); painter.drawPath(path)
    elif name == "pause":
        rect(7, 5, 3, 14, 0.6); rect(14, 5, 3, 14, 0.6)
    elif name == "stop":
        rect(6, 6, 12, 12, 1)
    elif name == "rewind":
        path = QPainterPath(QPointF(11, 6)); path.lineTo(4, 12); path.lineTo(11, 18); path.closeSubpath(); painter.drawPath(path)
        path = QPainterPath(QPointF(20, 6)); path.lineTo(13, 12); path.lineTo(20, 18); path.closeSubpath(); painter.drawPath(path)
    elif name == "sun":
        ellipse(8, 8, 8, 8)
        for x1, y1, x2, y2 in [(12,2,12,5),(12,19,12,22),(2,12,5,12),(19,12,22,12),(5,5,7,7),(17,17,19,19),(17,7,19,5),(5,19,7,17)]: line(x1,y1,x2,y2)
    elif name == "moon":
        path = QPainterPath(QPointF(17, 4)); path.cubicTo(9, 4, 6, 10, 8, 15); path.cubicTo(10, 20, 16, 21, 20, 17); path.cubicTo(14, 18, 10, 13, 12, 8); path.cubicTo(13, 6, 15, 5, 17, 4); painter.drawPath(path)
    elif name == "info":
        ellipse(3, 3, 18, 18); line(12, 10, 12, 17); painter.drawPoint(QPointF(12, 7))
    else:
        ellipse(5, 5, 14, 14)

    painter.end()
    return pixmap


def app_icon(
    name: str,
    size: int = 20,
    normal: str = "#52606D",
    active: str = "#0B57D0",
    selected: str = "#FFFFFF",
    disabled: str = "#A7B0BD",
) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_paint_icon(name, normal, size), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_paint_icon(name, selected, size), QIcon.Normal, QIcon.On)
    icon.addPixmap(_paint_icon(name, active, size), QIcon.Active, QIcon.Off)
    icon.addPixmap(_paint_icon(name, selected, size), QIcon.Active, QIcon.On)
    icon.addPixmap(_paint_icon(name, disabled, size), QIcon.Disabled, QIcon.Off)
    icon.addPixmap(_paint_icon(name, disabled, size), QIcon.Disabled, QIcon.On)
    return icon
