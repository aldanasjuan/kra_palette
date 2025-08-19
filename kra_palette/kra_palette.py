from krita import Krita, DockWidget, DockWidgetFactory, DockWidgetFactoryBase, ManagedColor
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import json, re

ANNOTATION_TYPE = "com.example.kra-palette"
ANNOTATION_DESC = "Per-document palette (stored in .kra as annotation)"
_PALETTE_BUFFER = []

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
		self._swatch_px = 20

		# UI
		root = ResizeAwareWidget(self)
		root.setContentsMargins(8, 8, 8, 8)
		self.setWidget(root)
		vbox = QVBoxLayout(root)
		vbox.setContentsMargins(6, 6, 6, 6)
		vbox.setSpacing(4)

		row = QHBoxLayout()
		row2 = QHBoxLayout()
		row3 = QHBoxLayout()
		row4 = QHBoxLayout()

		self.btn_fg = QPushButton("Add FG")
		self.btn_bg = QPushButton("Add BG")
		self.btn_rm = QPushButton("Remove")
		# self.btn_sort = QPushButton("Sort")
		self.btn_copy = QPushButton("Copy")
		self.btn_paste = QPushButton("Paste")
		self.btn_rm.setEnabled(False)

		row.addWidget(self.btn_fg)
		row.addWidget(self.btn_bg)
		row2.addWidget(self.btn_rm)
		# row2.addWidget(self.btn_sort)
		row3.addWidget(self.btn_copy)
		row3.addWidget(self.btn_paste)
		row4.addWidget(QLabel("Size"))

		self.size_spin = QSpinBox()
		self.size_spin.setRange(8, 64)
		self.size_spin.setSingleStep(1)
		self.size_spin.setValue(self._swatch_px)
		row4.addWidget(self.size_spin)

		vbox.addLayout(row)
		vbox.addLayout(row3)
		vbox.addLayout(row4)
		vbox.addLayout(row2)

		self.area = _SwatchArea()
		self.grid = FlowLayout(self.area)
		
		# self.grid.setContentsMargins(0, 0, 0, 0)
		# self.grid.setSpacing(1)
		# self.grid.setSizeConstraint(QLayout.SetMinimumSize)

		#scroll
		self.scroll = QScrollArea()
		self.scroll.setWidgetResizable(True)
		self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # vertical only
		self.scroll.setFrameShape(QFrame.NoFrame)
		self.area.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
		self.scroll.setWidget(self.area)
		vbox.addWidget(self.scroll, 1)

		root.resized.connect(self._sort_and_save)
		self.btn_fg.clicked.connect(self._add_fg)
		self.btn_bg.clicked.connect(self._add_bg)
		self.btn_rm.clicked.connect(self._remove_selected)
		# self.btn_sort.clicked.connect(self._sort_and_save)
		self.size_spin.valueChanged.connect(self._on_size_changed)
		self.btn_copy.clicked.connect(self._copy_palette)
		self.btn_paste.clicked.connect(self._paste_palette)

	def canvasChanged(self, canvas):
		# Canvas has no .document(); grab active document when canvas exists
		self._doc = Krita.instance().activeDocument() if canvas else None
		self._load_from_doc()

	def _on_size_changed(self, val: int):
		self._swatch_px = int(val)
		self._sort_and_save()
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
				self._sort_and_save()
		except Exception:
			self._colors = []
		

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
		self._sort_and_save()

	def _add_bg(self):
		view = self._active_view()
		if not view:
			return
		mc = view.backgroundColor()
		qc = mc.colorForCanvas(view.canvas())
		self._colors.append(qc.name())
		self._sort_and_save()

	def _remove_selected(self):
		if self._sel_idx is None:
			return
		if 0 <= self._sel_idx < len(self._colors):
			self._colors.pop(self._sel_idx)
		self._sel_idx = None
		self.btn_rm.setEnabled(False)
		self._sort_and_save()

	def _sort_and_save(self):

		self._colors = self._sort_colors_smart(self._colors)
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
		# cols = self._cols_for_width()
		for i, hexcol in enumerate(self._colors):
			sw = self._make_swatch(hexcol, i)
			self._swatches.append(sw)
			self.grid.addWidget(sw)

		self._update_selection_styles()

	# def _cols_for_width(self) -> int:
	# 	avail = max(1, self.area.width())
	# 	cell = self._swatch_px + self.grid.spacing()
	# 	cols = max(1, avail // cell)
	# 	return cols
	
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

	# ----- color sorting -----
	def _sort_colors_smart(self, hex_list):
		"""
		Sort swatches as a rainbow using HSL:
		- Colors: by Hue (0..359), then Lightness DESC (lighter first), then Saturation DESC
		- Grays (very low saturation or no hue): placed after colors, Lightness ASC (light -> dark)
		"""
		GRAY_SAT = 20  # 0..255 (Qt). <=20 ≈ achromatic

		def key(hexcol: str):
			qc = QColor(hexcol)
			h = qc.hslHue()         # 0..359, or -1 if achromatic
			s = qc.hslSaturation()  # 0..255
			l = qc.lightness()      # 0..255

			is_gray = (s <= GRAY_SAT) or (h < 0)
			if is_gray:
				# group 1 (after colors): sort by lightness (light -> dark)
				return (1, l)

			# group 0 (colors): Hue rainbow, then lighter first, then more saturated
			return (0, h, -l, -s)

		return sorted(hex_list, key=key)
	
	def _copy_palette(self):
		# Copy current hex list to both our buffer and the system clipboard as JSON
		global _PALETTE_BUFFER
		_PALETTE_BUFFER = list(self._colors)
		payload = {"type": ANNOTATION_TYPE, "colors": self._colors}
		try:
			QApplication.clipboard().setText(json.dumps(payload))
		except Exception:
			pass  # clipboard might be unavailable; buffer still works

	def _paste_palette(self):
		# Append colors from clipboard (or our buffer) into this doc's palette
		colors = []

		# 1) try system clipboard
		try:
			txt = QApplication.clipboard().text()
			if txt:
				try:
					obj = json.loads(txt)
					if isinstance(obj, dict) and "colors" in obj:
						colors = obj["colors"]
					elif isinstance(obj, list):
						colors = obj
					else:
						# maybe a plain string of hex codes
						colors = [t for t in re.split(r"[,\s;]+", txt) if t]
				except Exception:
					colors = [t for t in re.split(r"[,\s;]+", txt) if t]
		except Exception:
			pass

		# 2) fallback to our in-memory buffer
		if not colors:
			global _PALETTE_BUFFER
			colors = list(_PALETTE_BUFFER)

		if not colors:
			return

		# normalize & validate (#rrggbb, lower-case)
		valid = []
		for c in colors:
			qc = QColor(str(c))
			if qc.isValid():
				valid.append(qc.name())  # Krita/Qt returns '#rrggbb'

		if not valid:
			return

		# append deduped, preserving order
		seen = set(self._colors)
		appended = False
		for hexcol in valid:
			if hexcol not in seen:
				self._colors.append(hexcol)
				seen.add(hexcol)
				appended = True

		if not appended:
			return

		self._sort_and_save()
# register docker
Krita.instance().addDockWidgetFactory(
	DockWidgetFactory("kra_palette_docker", DockWidgetFactoryBase.DockRight, KRA_Palette_Docker)
)

class ResizeAwareWidget(QWidget):
	resized = pyqtSignal(object)  # emits QResizeEvent or size as you prefer
	def resizeEvent(self, e):
		self.resized.emit(e.size())   # or emit(e)
		super().resizeEvent(e)


class FlowLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)

        if parent is not None:
            self.setContentsMargins(QMargins(0, 0, 0, 0))

        self._item_list = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]

        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)

        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()

        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())

        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._item_list:
            style = item.widget().style()
            layout_spacing_x = style.layoutSpacing(
                QSizePolicy.ControlType.PushButton, QSizePolicy.ControlType.PushButton,
                Qt.Orientation.Horizontal
            )
            layout_spacing_y = style.layoutSpacing(
                QSizePolicy.ControlType.PushButton, QSizePolicy.ControlType.PushButton,
                Qt.Orientation.Vertical
            )
            space_x = spacing + layout_spacing_x
            space_y = spacing + layout_spacing_y
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()