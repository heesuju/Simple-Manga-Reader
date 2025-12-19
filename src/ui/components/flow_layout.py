from PyQt6.QtWidgets import QLayout, QSizePolicy, QWidget, QSpacerItem, QWidgetItem
from PyQt6.QtCore import QSize, Qt, QPoint, QRect

class FlowLayout(QLayout):
    """A layout that arranges child widgets like a flow/grid and wraps rows."""
    def __init__(self, parent=None, margin=0, spacing=10):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []
        self._single_row = False

    def setSingleRow(self, single_row: bool):
        if self._single_row != single_row:
            self._single_row = single_row
            self.invalidate()

    def addItem(self, item):
        self.itemList.append(item)

    def insertWidget(self, index, widget):
        item = QWidgetItem(widget)
        if index < 0 or index >= len(self.itemList):
            self.itemList.append(item)
        else:
            self.itemList.insert(index, item)
        self.addChildWidget(widget) # Important for Qt logic if needed, usually addWidget manages parenting
        self.invalidate()

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
        return not self._single_row

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
        
        # In single row, width is sum of all widths
        if self._single_row:
            total_w = 0
            max_h = 0
            spacing = self.spacing()
            for item in self.itemList:
                s = item.minimumSize() # or sizeHint?
                total_w += s.width() + spacing
                max_h = max(max_h, s.height())
            if self.itemList: total_w -= spacing
            size = QSize(total_w, max_h)
        else:
            # Standard min size for flow/grid? usually assumes wrapping is allowed so min is largest item
            pass 

        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x, y, lineHeight = rect.x(), rect.y(), 0
        spacing = self.spacing()

        for item in self.itemList:
            widget = item.widget()
            size = item.sizeHint()
            
            nextX = x + size.width() + spacing
            
            # WRAP LOGIC
            # Only wrap if NOT single_row AND space is insufficient
            should_wrap = (not self._single_row) and (nextX - spacing > rect.right() and lineHeight > 0)
            
            if should_wrap:
                x = rect.x()
                y += lineHeight + spacing
                nextX = x + size.width() + spacing
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), size))

            x = nextX
            lineHeight = max(lineHeight, size.height())

        return y + lineHeight - rect.y()