from krita import Krita, DockWidget, DockWidgetFactory, DockWidgetFactoryBase, ManagedColor
from PyQt5.QtCore import QByteArray, Qt, pyqtSignal, QPoint, QRect, QSize
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout, QFrame, QLayout, QStyle
from PyQt5.QtGui import QColor
import json

ANNOTATION_TYPE = "com.example.kra-palette"
ANNOTATION_DESC = "Per-document palette (stored in .kra as annotation)"


class _SwatchArea(QWidget):
	resized = pyqtSignal()
	def resizeEvent(self, e):
		self.resized.emit()
		super().resizeEvent(e)

class KRA_Palette_Docker(DockWidget):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("KRA Palette")
		self._doc = None
		self._colors = []          # list[str] like "#RRGGBB"
		self._swatches = []        # list[QFrame]
		self._sel_idx = None       # selected swatch index
		self._swatch_px = 18

		# UI
		root = QWidget(self)
		root.setContentsMargins(8, 8, 8, 8)
		self.setWidget(root)
		vbox = QVBoxLayout(root)
		vbox.setContentsMargins(6, 6, 6, 6)
		vbox.setSpacing(4)

		row = QHBoxLayout()
		row2 = QHBoxLayout()
		self.btn_fg = QPushButton("Add FG")
		self.btn_bg = QPushButton("Add BG")
		self.btn_rm = QPushButton("Remove")
		self.btn_rm.setEnabled(False)
		row.addWidget(self.btn_fg)
		row.addWidget(self.btn_bg)
		row.addStretch(1)
		row2.addWidget(self.btn_rm)
		vbox.addLayout(row)
		vbox.addLayout(row2)
		self.area = _SwatchArea()
		self.grid = FlowLayout(self.area, 0, 4, 4)
		self.grid.setSizeConstraint(QLayout.SetMinimumSize)
		vbox.addWidget(self.area, 1)

		self.btn_fg.clicked.connect(self._add_fg)
		self.btn_bg.clicked.connect(self._add_bg)
		self.btn_rm.clicked.connect(self._remove_selected)
		self.area.resized.connect(self._rebuild_grid)

	def canvasChanged(self, canvas):
		# Canvas has no .document(); grab active document when canvas exists
		self._doc = Krita.instance().activeDocument() if canvas else None
		self._load_from_doc()

	# ----- palette I/O (annotation in .kra) -----
	def _load_from_doc(self):
		self._colors = []
		self._sel_idx = None
		self.btn_rm.setEnabled(False)
		self._clear_grid()
		if not self._doc:
			return
		try:
			data = bytes(self._doc.annotation(ANNOTATION_TYPE))
			if data:
				self._colors = json.loads(data.decode("utf-8")) or []
		except Exception:
			self._colors = []
		self._rebuild_grid()

	def _save_to_doc(self):
		if not self._doc:
			return
		ba = QByteArray(json.dumps(self._colors).encode("utf-8"))
		self._doc.setAnnotation(ANNOTATION_TYPE, ANNOTATION_DESC, ba)
		self._doc.setModified(True)

	# ----- actions -----
	def _add_fg(self):
		view = self._active_view()
		if not view:
			return
		mc = view.foregroundColor()
		qc = mc.colorForCanvas(view.canvas())
		self._colors.append(qc.name())  # "#RRGGBB"
		self._save_to_doc()
		self._rebuild_grid()

	def _add_bg(self):
		view = self._active_view()
		if not view:
			return
		mc = view.backgroundColor()
		qc = mc.colorForCanvas(view.canvas())
		self._colors.append(qc.name())
		self._save_to_doc()
		self._rebuild_grid()

	def _remove_selected(self):
		if self._sel_idx is None:
			return
		if 0 <= self._sel_idx < len(self._colors):
			self._colors.pop(self._sel_idx)
		self._sel_idx = None
		self.btn_rm.setEnabled(False)
		self._save_to_doc()
		self._rebuild_grid()

	# ----- UI helpers -----
	def _rebuild_grid(self):
		# rebuild swatch widgets and lay them out based on current width
		self._clear_grid()
		self._swatches = []
		if not self._colors:
			return

		for i, hexcol in enumerate(self._colors):
			sw = self._make_swatch(hexcol, i)
			self._swatches.append(sw)
			self.grid.addWidget(sw)

		self._update_selection_styles()


	def _clear_grid(self):
		while self.grid.count():
			item = self.grid.takeAt(0)
			w = item.widget()
			if w:
				w.deleteLater()

	def _swatch_style(self, hexcol: str, selected: bool) -> str:
		bw = 2 if selected else 1
		bc = "#68a0ff" if selected else "#444"
		return f"QFrame {{ background: {hexcol}; border: {bw}px solid {bc}; border-radius: 3px; }}"

	def _make_swatch(self, hexcol: str, idx: int) -> QWidget:
		box = QFrame()
		box.setFixedSize(self._swatch_px, self._swatch_px)
		box.setStyleSheet(self._swatch_style(hexcol, idx == self._sel_idx))

		def on_mouse_press(ev):
			view = self._active_view()
			if not view:
				return
			qc = QColor(hexcol)
			mc = ManagedColor.fromQColor(qc, view.canvas())

			# update selection
			self._select_index(idx)

			# left-click -> FG, right-click -> BG
			if ev.button() == Qt.LeftButton:
				view.setForeGroundColor(mc)
			elif ev.button() == Qt.RightButton:
				try:
					view.setBackGroundColor(mc)
				except Exception:
					# Fallback for API name differences
					if hasattr(view, "setBackgroundColor"):
						view.setBackgroundColor(mc)

		box.mousePressEvent = on_mouse_press
		return box

	def _select_index(self, idx: int):
		self._sel_idx = idx
		self.btn_rm.setEnabled(True)
		self._update_selection_styles()

	def _update_selection_styles(self):
		for i, sw in enumerate(self._swatches):
			if i < len(self._colors):
				sw.setStyleSheet(self._swatch_style(self._colors[i], i == self._sel_idx))

	def _active_view(self):
		app = Krita.instance()
		win = app.activeWindow()
		return win.activeView() if win else None

# register docker
Krita.instance().addDockWidgetFactory(
	DockWidgetFactory("kra_palette_docker", DockWidgetFactoryBase.DockRight, KRA_Palette_Docker)
)



class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, hspacing=-1, vspacing=-1):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self._hspace = hspacing
        self._vspace = vspacing

    # --- QLayout abstract methods ---
    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        # No forced expansion; lets container size to contents
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._doLayout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._doLayout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        # Base on laid-out geometry for the current set of items
        mleft, mtop, mright, mbottom = self.getContentsMargins()
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        size += QSize(mleft + mright, mtop + mbottom)
        return size

    # --- helpers ---
    def horizontalSpacing(self):
        if self._hspace >= 0:
            return self._hspace
        return self.smartSpacing(QStyle.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self._vspace >= 0:
            return self._vspace
        return self.smartSpacing(QStyle.PM_LayoutVerticalSpacing)

    def smartSpacing(self, pm):
        parent = self.parent()
        if parent is None:
            return 6  # reasonable default
        from PyQt5.QtWidgets import QWidget, QStyle
        if isinstance(parent, QWidget):
            return parent.style().pixelMetric(pm, None, parent)
        return 6

    def _doLayout(self, rect, test_only):
        from PyQt5.QtWidgets import QStyle
        mleft, mtop, mright, mbottom = self.getContentsMargins()
        x = rect.x() + mleft
        y = rect.y() + mtop
        line_height = 0

        hspace = self._hspace if self._hspace >= 0 else 6
        vspace = self._vspace if self._vspace >= 0 else 6

        effective_rect = QRect(rect.x() + mleft, rect.y() + mtop,
                               rect.width() - (mleft + mright),
                               rect.height() - (mtop + mbottom))

        for item in self._items:
            wid = item.widget()
            if wid and not wid.isVisible():
                continue
            spaceX = hspace
            spaceY = vspace
            next_x = x + item.sizeHint().width() + spaceX
            if next_x - spaceX > effective_rect.right() + 1 and line_height > 0:
                # wrap
                x = effective_rect.x()
                y = y + line_height + spaceY
                next_x = x + item.sizeHint().width() + spaceX
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        total_height = (y + line_height + mbottom) - rect.y()
        return total_height
