from PyQt6.QtWidgets import QLayout, QSizePolicy, QWidget, QSpacerItem
from PyQt6.QtCore import QSize, Qt, QPoint, QRect

class FlowLayout(QLayout):
    """A layout that arranges child widgets like a flow/grid and wraps rows."""
    def __init__(self, parent=None, margin=0, spacing=10):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x, y, lineHeight = rect.x(), rect.y(), 0
        spacing = self.spacing()

        for item in self.itemList:
            widget = item.widget()
            if widget is None:
                continue
            nextX = x + widget.width() + spacing
            if nextX - spacing > rect.right() and lineHeight > 0:
                x = rect.x()
                y += lineHeight + spacing
                nextX = x + widget.width() + spacing
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), widget.size()))

            x = nextX
            lineHeight = max(lineHeight, widget.height())

        return y + lineHeight - rect.y()