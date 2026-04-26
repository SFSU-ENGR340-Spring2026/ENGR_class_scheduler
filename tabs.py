"""
ENGR Class Scheduler - DB Editor Tabs
The three QWidget tab classes used inside the left panel of the main window.
Each tab loads from / saves to the database via db.py.
"""

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QIntValidator, QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from db import (
    load_sections, save_sections, delete_section,
    load_faculty,  save_faculty,  delete_faculty,
    load_time_slots, save_time_slots, delete_time_slot,
)

AVAIL_START = "08:00"
AVAIL_END   = "18:30"
DAY_ORDER   = ["M", "T", "W", "R", "F"]

# Slider covers 7:00–22:00 in 30-minute steps
SLIDER_MIN_HOUR = 7
SLIDER_MAX_HOUR = 22
STEPS = (SLIDER_MAX_HOUR - SLIDER_MIN_HOUR) * 2   # 30 steps total


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def minutes_to_step(hhmm):
    try:
        h, m = hhmm.split(":")
        total = int(h) * 60 + int(m)
        base  = SLIDER_MIN_HOUR * 60
        return max(0, min(STEPS, (total - base) // 30))
    except Exception:
        return 0


def step_to_time(step):
    total = SLIDER_MIN_HOUR * 60 + step * 30
    return f"{total // 60:02d}:{total % 60:02d}"


def _placeholder_combo(placeholder, options):
    """Editable combo with grey placeholder hint — used for new empty rows."""
    cb = QComboBox()
    cb.setEditable(True)
    cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    cb.lineEdit().setPlaceholderText(placeholder)
    cb.addItems([""] + list(options))
    cb.setCurrentIndex(0)
    cb.setStyleSheet("QComboBox { border: none; }")
    return cb


class IntegerDelegate(QStyledItemDelegate):
    """Forces table cells to only accept integer input."""
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setValidator(QIntValidator(0, 999, editor))
        return editor


# ---------------------------------------------------------------------------
# Custom Time Range Slider (replaces the old checkbox + QLineEdit pair)
# ---------------------------------------------------------------------------

class TimeRangeSlider(QWidget):
    """Double-handle slider for one day of faculty availability.
    Checkbox sits to the LEFT of the slider with a small gap."""

    HANDLE_W = 12
    TRACK_H  = 6
    LABEL_H  = 18
    CB_R     = 7    # checkbox circle radius
    CB_GAP   = 6    # gap between checkbox right edge and track start

    def __init__(self, is_avail, st, et, parent=None):
        super().__init__(parent)
        self._avail    = is_avail
        self._lo       = minutes_to_step(st)
        self._hi       = minutes_to_step(et)
        self._drag     = None
        self.setMinimumWidth(110)
        self.setFixedHeight(62)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    @property
    def is_available(self):
        return self._avail

    @property
    def start_time(self):
        return step_to_time(self._lo)

    @property
    def end_time(self):
        return step_to_time(self._hi)

    def set_available(self, val):
        self._avail = val
        self.update()

    def _track_rect(self):
        """Track starts after checkbox on the left."""
        hw    = self.HANDLE_W
        # left offset: checkbox diameter + gap + handle half-width
        x     = self.CB_R * 2 + self.CB_GAP + hw
        w     = self.width() - x - hw
        y     = self.LABEL_H + (self.height() - self.LABEL_H - self.TRACK_H) // 2
        return x, y, w

    def _step_to_px(self, step):
        x, _, w = self._track_rect()
        return x + int(step / STEPS * w)

    def _px_to_step(self, px):
        x, _, w = self._track_rect()
        if w == 0:
            return 0
        return max(0, min(STEPS, round((px - x) / w * STEPS)))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x, y, tw = self._track_rect()
        th   = self.TRACK_H
        cb_r = self.CB_R
        # Checkbox on the LEFT, centred vertically in the track area
        cb_x = self.CB_R + 1          # flush left with small margin
        cb_y = self.LABEL_H + (self.height() - self.LABEL_H) // 2

        # Checkbox circle — left of track
        p.setPen(QPen(QColor("#888"), 1.5))
        p.setBrush(QColor("#4e79a7") if self._avail else QColor("#ffffff"))
        p.drawEllipse(cb_x - cb_r, cb_y - cb_r, cb_r * 2, cb_r * 2)
        if self._avail:
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawLine(cb_x - 3, cb_y, cb_x - 1, cb_y + 2)
            p.drawLine(cb_x - 1, cb_y + 2, cb_x + 3, cb_y - 2)

        if not self._avail:
            p.setPen(QColor("#aaaaaa"))
            font = QFont()
            font.setPointSize(9)
            p.setFont(font)
            # text starts just after the checkbox + gap
            p.drawText(self.CB_R * 2 + self.CB_GAP + 2, cb_y + 4, "Not available")
            p.end()
            return

        # Track background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#dddddd"))
        p.drawRoundedRect(x, y, tw, th, 3, 3)

        # Selected range
        lo_px = self._step_to_px(self._lo)
        hi_px = self._step_to_px(self._hi)
        p.setBrush(QColor("#4e79a7"))
        p.drawRoundedRect(lo_px, y, max(0, hi_px - lo_px), th, 3, 3)

        # Hour tick marks
        p.setPen(QPen(QColor("#bbbbbb"), 1))
        for step in range(0, STEPS + 1, 2):
            tx = self._step_to_px(step)
            p.drawLine(tx, y + th, tx, y + th + 3)

        # Handles
        for step in (self._lo, self._hi):
            hx = self._step_to_px(step)
            hw = self.HANDLE_W
            p.setPen(QPen(QColor("#1a4f7f"), 1))
            p.setBrush(QColor("#2a5f8f"))
            p.drawRoundedRect(hx - hw // 2, y - 5, hw, th + 10, 3, 3)

        # Time labels
        font = QFont()
        font.setPointSize(8)
        p.setFont(font)
        p.setPen(QColor("#333333"))
        p.drawText(QRect(x, 2, tw // 2, self.LABEL_H - 2),
                   Qt.AlignmentFlag.AlignLeft,  step_to_time(self._lo))
        p.drawText(QRect(x + tw // 2, 2, tw // 2, self.LABEL_H - 2),
                   Qt.AlignmentFlag.AlignRight, step_to_time(self._hi))
        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        px  = event.position().x()
        x, y, tw = self._track_rect()
        cb_r = self.CB_R
        cb_x = self.CB_R + 1
        cb_y = self.LABEL_H + (self.height() - self.LABEL_H) // 2
        if abs(px - cb_x) <= cb_r + 4 and abs(event.position().y() - cb_y) <= cb_r + 4:
            self._avail = not self._avail
            self.update()
            return
        if not self._avail:
            return
        lo_px = self._step_to_px(self._lo)
        hi_px = self._step_to_px(self._hi)
        self._drag = 'lo' if abs(px - lo_px) <= abs(px - hi_px) else 'hi'

    def mouseMoveEvent(self, event):
        if self._drag is None or not self._avail:
            return
        step = self._px_to_step(event.position().x())
        if self._drag == 'lo':
            self._lo = max(0, min(self._hi - 1, step))
        else:
            self._hi = max(self._lo + 1, min(STEPS, step))
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag = None


# ---------------------------------------------------------------------------
# Sections tab
# ---------------------------------------------------------------------------

class SectionsTab(QWidget):
    """Columns: #, Course ID, Type, Slot Type, Cap, Major, Room, Freeze Slot, ×"""

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter sections...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "#", "Course ID", "Type", "Slot Type", "Cap",
            "Major", "Room", "Freeze Slot", "", ""
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)            # #
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)            # Course ID
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)            # Type
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # Slot Type
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)            # Cap
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents) # Major
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)          # Room — fills remaining space
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents) # Freeze Slot
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)            # ×
        hdr.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)            # right cushion
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 68)
        self.table.setColumnWidth(4, 40)
        self.table.setColumnWidth(8, 30)
        self.table.setColumnWidth(9, 16)  # right breathing room
        self.table.setColumnHidden(2, True)  # Type hidden — duration already shown in Slot Type
        layout.addWidget(self.table)

        int_del = IntegerDelegate(self.table)
        self.table.setItemDelegateForColumn(0, int_del)   # section #
        self.table.setItemDelegateForColumn(4, int_del)   # capacity
        self.table.setItemDelegateForColumn(7, int_del)   # freeze slot ID

        add_btn = QPushButton("+ Add Section")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(12)

        self.load()

    def _apply_filter(self, text):
        term = text.lower()
        for r in range(self.table.rowCount()):
            match = any(self._cell_text(r, c) and term in self._cell_text(r, c).lower()
                        for c in range(8))
            self.table.setRowHidden(r, not match)

    def load(self):
        self.table.setRowCount(0)
        rows = sorted(load_sections(self.db_path), key=lambda x: (x[1], x[0]))
        for row in rows:
            if len(row) == 5:
                sid, cid, ctype, stype, cap = row
                major, lab_room, frozen = "", "", ""
            else:
                sid, cid, ctype, stype, cap, major, lab_room, frozen = row
            self._insert_row(sid, cid, ctype, stype, cap,
                             major or "", lab_room or "",
                             "" if frozen is None else str(frozen))

    def _insert_row(self, sid="", cid="", ctype="", stype="", cap="",
                    major="", lab_room="", frozen=""):
        r = self.table.rowCount()
        self.table.insertRow(r)
        short = sid.split("-")[-1] if "-" in str(sid) else ""
        for col, val in enumerate([short, cid, ctype, stype, str(cap),
                                    major, lab_room, frozen]):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, col, item)
        self.table.setCellWidget(r, 8, self._make_delete_btn())
        self.table.resizeRowToContents(r)

    def _make_delete_btn(self):
        btn = QPushButton("×")
        btn.setFixedSize(28, 22)
        btn.setStyleSheet("color:red; font-weight:bold;")
        btn.clicked.connect(lambda _, b=btn: self._delete_row_by_btn(b))
        container = QWidget()
        cl = QHBoxLayout(container)
        cl.addWidget(btn)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setContentsMargins(0, 0, 0, 0)
        return container

    def _delete_row_by_btn(self, btn):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 8)
            if w and w.findChild(QPushButton) is btn:
                self._delete_row(r)
                return

    def _cell_text(self, r, c):
        w = self.table.cellWidget(r, c)
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        item = self.table.item(r, c)
        return item.text().strip() if item else ""

    def _add_row(self):
        # Block if there is already an unfilled row (ignore spacer rows tagged with UserRole)
        for r in range(self.table.rowCount()):
            item0 = self.table.item(r, 0)
            if item0 and item0.data(Qt.ItemDataRole.UserRole) == "_spacer":
                continue
            if not self._cell_text(r, 0) or not self._cell_text(r, 1):
                self.table.selectRow(r)
                QMessageBox.warning(self, "Notice",
                    "Please fill out # and Course ID for the highlighted row before adding a new one.")
                return
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(""))
        self.table.setCellWidget(r, 1, _placeholder_combo(
            "e.g. ENGR340",
            ["ENGR100","ENGR101","ENGR102","ENGR104","ENGR200","ENGR201",
             "ENGR205","ENGR206","ENGR212","ENGR213","ENGR214","ENGR221",
             "ENGR235","ENGR271","ENGR282","ENGR291","ENGR295","ENGR300",
             "ENGR301","ENGR302","ENGR303","ENGR304","ENGR305","ENGR306",
             "ENGR307","ENGR309","ENGR323","ENGR340","ENGR350","ENGR353",
             "ENGR356","ENGR357","ENGR363","ENGR364","ENGR378","ENGR410",
             "ENGR413","ENGR414","ENGR425","ENGR427","ENGR429","ENGR430",
             "ENGR431","ENGR434","ENGR436","ENGR442","ENGR446","ENGR447",
             "ENGR448","ENGR449","ENGR451","ENGR456","ENGR461","ENGR463",
             "ENGR465","ENGR467","ENGR476","ENGR478","ENGR498","ENGR610",
             "ENGR696","ENGR697","ENGR836","ENGR838","ENGR839","ENGR844",
             "ENGR852","ENGR856","ENGR867","ENGR869","ENGR890"]))
        self.table.setCellWidget(r, 2, _placeholder_combo(
            "Type", ["Lecture", "Lab", "Activity"]))
        self.table.setCellWidget(r, 3, _placeholder_combo(
            "Slot type",
            ["50min_lecture","75min_lecture","100min_activity","165min_lab"]))
        self.table.setItem(r, 4, QTableWidgetItem(""))   # Cap
        self.table.setCellWidget(r, 5, _placeholder_combo(
            "Major",
            ["All 4","CE","Civil","Civil/ME","CompE","EE","EE/CE",
             "EE/CE/ME","EE/CompE","Grad","ME","MSCivil","MSECE","MSME"]))
        self.table.setCellWidget(r, 6, _placeholder_combo(
            "Room",
            ["Need Room",
             "SEIC 101","SEIC 103","SEIC 400","SEIC 401","SEIC 402",
             "SEIC 403","SEIC 412","SEIC 414","SEIC 416","SEIC 417",
             "SCI 111","SCI 115","SCI 214",
             "SEIC 412 or SCI 214","SEIC 416 or SEIC 417",
             "SEIC 412 or SEIC 416 or SEIC 417"]))
        self.table.setItem(r, 7, QTableWidgetItem(""))   # Freeze Slot
        self.table.setCellWidget(r, 8, self._make_delete_btn())
        self.table.scrollToBottom()
        # Extra blank row for breathing room at the bottom
        self.table.insertRow(r + 1)
        spacer_item = QTableWidgetItem("")
        spacer_item.setData(Qt.ItemDataRole.UserRole, "_spacer")
        self.table.setItem(r + 1, 0, spacer_item)
        self.table.setRowHidden(r + 1, False)
        # NOTE: do NOT call setCurrentCell here — triggers Qt recursion crash on macOS

    def _delete_row(self, row):
        short = self._cell_text(row, 0)
        cid   = self._cell_text(row, 1)
        sid   = f"{cid}-{short}" if cid and short else ""
        if sid:
            reply = QMessageBox.question(self, "Delete", f"Delete {sid}?")
            if reply != QMessageBox.StandardButton.Yes:
                return
            delete_section(self.db_path, sid)
        self.table.removeRow(row)

    def save(self):
        rows = []
        for r in range(self.table.rowCount()):
            short    = self._cell_text(r, 0)
            cid      = self._cell_text(r, 1)
            ctype    = self._cell_text(r, 2)
            stype    = self._cell_text(r, 3)
            cap      = self._cell_text(r, 4)
            major    = self._cell_text(r, 5)
            lab_room = self._cell_text(r, 6)
            frozen   = self._cell_text(r, 7)
            sid = f"{cid}-{short}" if cid and short else ""
            if sid:
                rows.append([sid, cid, ctype, stype, cap, major, lab_room, frozen])
        save_sections(self.db_path, rows)


# ---------------------------------------------------------------------------
# Faculty tab
# ---------------------------------------------------------------------------

class FacultyTab(QWidget):
    """Columns: Code, Name, WTU, Can Teach, Mon–Fri (sliders), ×"""

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        hint = QLabel("Code: unique ID  |  WTU: teaching units  |  "
                      "Can Teach: comma-separated IDs  |  "
                      "Drag slider handles to set availability per day")
        hint.setStyleSheet("color:#666; font-size:11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter faculty...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "Code", "Name", "WTU", "Can Teach",
            "Mon", "Tue", "Wed", "Thu", "Fri", "", ""
        ])
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        for i in range(4, 10):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(10, QHeaderView.ResizeMode.Fixed)  # right spacer
        self.table.setColumnWidth(0, 72)
        self.table.setColumnWidth(2, 45)
        self.table.setColumnWidth(3, 185)
        for col in range(4, 9):
            self.table.setColumnWidth(col, 145)
        self.table.setColumnWidth(9, 28)
        self.table.setColumnWidth(10, 16)  # right breathing room
        hdr.setMinimumHeight(36)
        layout.addWidget(self.table)

        add_btn = QPushButton("+ Add Faculty")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(12)

        self.load()

    def _apply_filter(self, text):
        term = text.lower()
        for r in range(self.table.rowCount()):
            match = any(
                self.table.item(r, c) and term in self.table.item(r, c).text().lower()
                for c in range(4)
            )
            self.table.setRowHidden(r, not match)

    def load(self):
        self.table.setRowCount(0)
        for code, name, wtu, courses, avail_dict in load_faculty(self.db_path):
            self._insert_row(code, name, wtu, courses, avail_dict)

    def _insert_row(self, code="", name="", wtu="", courses="", avail_dict=None):
        if avail_dict is None:
            avail_dict = {}
        r = self.table.rowCount()
        self.table.insertRow(r)

        self.table.setItem(r, 0, QTableWidgetItem(code))
        self.table.setItem(r, 1, QTableWidgetItem(name))
        wtu_item = QTableWidgetItem(wtu)
        wtu_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r, 2, wtu_item)
        teach_item = QTableWidgetItem(courses)
        teach_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r, 3, teach_item)

        for col, day in enumerate(DAY_ORDER, start=4):
            if day in avail_dict and avail_dict[day]:
                is_avail = True
                st, et   = avail_dict[day][0]
            else:
                is_avail = False
                st, et   = AVAIL_START, AVAIL_END
            slider = TimeRangeSlider(is_avail, st, et)
            self.table.setCellWidget(r, col, slider)

        self.table.setRowHeight(r, 68)
        self.table.setCellWidget(r, 9, self._make_delete_btn())

    def _make_delete_btn(self):
        btn = QPushButton("×")
        btn.setFixedSize(28, 22)
        btn.setStyleSheet("color:red; font-weight:bold;")
        btn.clicked.connect(lambda _, b=btn: self._delete_row_by_btn(b))
        container = QWidget()
        cl = QHBoxLayout(container)
        cl.addWidget(btn)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setContentsMargins(0, 0, 0, 0)
        return container

    def _delete_row_by_btn(self, btn):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 9)
            if w and w.findChild(QPushButton) is btn:
                self._delete_row(r)
                return

    def _add_row(self):
        for r in range(self.table.rowCount()):
            # skip spacer rows
            item0 = self.table.item(r, 0)
            if item0 and item0.data(Qt.ItemDataRole.UserRole) == "_spacer":
                continue
            # col 0 may be a QComboBox (new unsaved row) or plain QTableWidgetItem (loaded row)
            w = self.table.cellWidget(r, 0)
            if isinstance(w, QComboBox):
                code = w.currentText().strip()
            else:
                code = self.table.item(r, 0).text().strip() if self.table.item(r, 0) else ""
            if not code:
                self.table.selectRow(r)
                self.table.scrollToBottom()
                QMessageBox.warning(self, "Notice",
                    "Please enter a Faculty Code for the highlighted row before adding a new one.")
                return
        r = self.table.rowCount()
        self.table.insertRow(r)
        # Code — editable combo with existing codes as suggestions
        self.table.setCellWidget(r, 0, _placeholder_combo(
            "e.g. TTF01",
            ["TTF 01","TTF 02","TTF 03","TTF 04","TTF 05","TTF 06","TTF 07",
             "TTF 08","TTF 09","TTF 10","TTF 11","TTF 12","TTF 13","TTF 14",
             "TTF 15","TTF 16","TTF 17","TTF 18","TTF 19",
             "GTA 01","GTA 02","GTA 03","GTA 04","GTA 05","GTA 06","GTA 07",
             "LF 01","LF 02","LF 03","LF 04","LF 05","LF 06","LF 07",
             "LF 08","LF 09","LF 10","LF 11","LF 12","LF 13","LF 14","LF 15"]))
        self.table.setItem(r, 1, QTableWidgetItem(""))   # Name
        self.table.setItem(r, 2, QTableWidgetItem(""))   # WTU
        # Can Teach — editable combo listing every course
        self.table.setCellWidget(r, 3, _placeholder_combo(
            "e.g. ENGR340, ENGR221",
            ["ENGR100","ENGR101","ENGR102","ENGR104","ENGR200","ENGR201",
             "ENGR205","ENGR206","ENGR212","ENGR213","ENGR214","ENGR221",
             "ENGR235","ENGR271","ENGR282","ENGR291","ENGR295","ENGR300",
             "ENGR301","ENGR302","ENGR303","ENGR304","ENGR305","ENGR306",
             "ENGR307","ENGR309","ENGR323","ENGR340","ENGR350","ENGR353",
             "ENGR356","ENGR357","ENGR363","ENGR364","ENGR378","ENGR410",
             "ENGR413","ENGR414","ENGR425","ENGR427","ENGR429","ENGR430",
             "ENGR431","ENGR434","ENGR436","ENGR442","ENGR446","ENGR447",
             "ENGR448","ENGR449","ENGR451","ENGR456","ENGR461","ENGR463",
             "ENGR465","ENGR467","ENGR476","ENGR478","ENGR498","ENGR610",
             "ENGR696","ENGR697","ENGR836","ENGR838","ENGR839","ENGR844",
             "ENGR852","ENGR856","ENGR867","ENGR869","ENGR890"]))
        # Day sliders — default unavailable
        for col in range(4, 9):
            slider = TimeRangeSlider(False, AVAIL_START, AVAIL_END)
            self.table.setCellWidget(r, col, slider)
        self.table.setRowHeight(r, 68)
        self.table.setCellWidget(r, 9, self._make_delete_btn())
        self.table.scrollToBottom()
        # Extra blank row for breathing room at the bottom
        self.table.insertRow(r + 1)
        spacer_item = QTableWidgetItem("")
        spacer_item.setData(Qt.ItemDataRole.UserRole, "_spacer")
        self.table.setItem(r + 1, 0, spacer_item)
        self.table.setRowHeight(r + 1, 8)
        # NOTE: do NOT call setCurrentCell/editItem here — triggers Qt recursion crash on macOS

    def _delete_row(self, row):
        w0 = self.table.cellWidget(row, 0)
        code = w0.currentText().strip() if isinstance(w0, QComboBox) else (
            self.table.item(row, 0).text().strip() if self.table.item(row, 0) else "")
        name = self.table.item(row, 1).text().strip() if self.table.item(row, 1) else code
        if code:
            reply = QMessageBox.question(self, "Delete", f"Delete {name} ({code})?")
            if reply != QMessageBox.StandardButton.Yes:
                return
            delete_faculty(self.db_path, code)
        self.table.removeRow(row)

    def save(self):
        errors = []
        seen_codes = set()
        rows = []
        for r in range(self.table.rowCount()):
            # col 0 and col 3 may be QComboBox widgets on newly-added (unsaved) rows
            w0 = self.table.cellWidget(r, 0)
            code = w0.currentText().strip() if isinstance(w0, QComboBox) else (
                self.table.item(r, 0).text().strip() if self.table.item(r, 0) else "")
            name  = self.table.item(r, 1).text().strip() if self.table.item(r, 1) else ""
            wtu   = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else ""
            w3 = self.table.cellWidget(r, 3)
            teach = w3.currentText().strip() if isinstance(w3, QComboBox) else (
                self.table.item(r, 3).text().strip() if self.table.item(r, 3) else "")

            if not code:
                # skip the blank spacer row inserted by _add_row for breathing room
                continue
            if code in seen_codes:
                errors.append(f"Row {r + 1}: Duplicate code '{code}'.")
                continue
            seen_codes.add(code)

            avail = {}
            for col, day in enumerate(DAY_ORDER, start=4):
                slider = self.table.cellWidget(r, col)
                if slider and slider.is_available:
                    avail[day] = [(slider.start_time, slider.end_time)]

            rows.append((code, name, wtu, teach, avail))

        if errors:
            QMessageBox.warning(self, "Save Errors", "\n".join(errors))
            return

        save_faculty(self.db_path, rows)


# ---------------------------------------------------------------------------
# Time Slots tab
# ---------------------------------------------------------------------------

class TimeSlotsTab(QWidget):

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter time slots...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

        self.table = QTableWidget(0, 6)  # ID, Slot Type, Day Pattern, Start, End, ×
        self.table.setHorizontalHeaderLabels(["ID", "Slot Type", "Day Pattern", "Start", "End", ""])
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        for i in range(6):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 32)
        # ID column visible — users need it to set frozen_slot_id in Sections tab
        layout.addWidget(self.table)

        add_btn = QPushButton("+ Add Time Slot")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(12)

        self.load()

    def _apply_filter(self, text):
        term = text.lower()
        for r in range(self.table.rowCount()):
            match = any(
                self.table.item(r, c) and term in self.table.item(r, c).text().lower()
                for c in range(5)
            )
            self.table.setRowHidden(r, not match)

    def load(self):
        self.table.setRowCount(0)
        rows = sorted(load_time_slots(self.db_path), key=lambda x: x[0])  # ascending by slot_id
        for sid, stype, pattern, start, end in rows:
            self._insert_row(str(sid), stype, pattern, start, end)

    def _insert_row(self, slot_id="NEW", stype="", pattern="", start="", end=""):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(slot_id))
        self.table.setItem(r, 1, QTableWidgetItem(stype))
        self.table.setItem(r, 2, QTableWidgetItem(pattern))
        self.table.setItem(r, 3, QTableWidgetItem(start))
        self.table.setItem(r, 4, QTableWidgetItem(end))
        self.table.setCellWidget(r, 5, self._make_delete_btn())

    def _make_delete_btn(self):
        btn = QPushButton("×")
        btn.setFixedSize(28, 22)
        btn.setStyleSheet("color:red; font-weight:bold;")
        btn.clicked.connect(lambda _, b=btn: self._delete_row_by_btn(b))
        container = QWidget()
        cl = QHBoxLayout(container)
        cl.addWidget(btn)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setContentsMargins(0, 0, 0, 0)
        return container

    def _delete_row_by_btn(self, btn):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 5)
            if w and w.findChild(QPushButton) is btn:
                self._delete_row(r)
                return

    def _cell_text(self, r, c):
        w = self.table.cellWidget(r, c)
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        item = self.table.item(r, c)
        return item.text().strip() if item else ""

    # Duration (minutes) for each slot type
    SLOT_DURATIONS = {
        "50min_lecture":    50,
        "75min_lecture":    75,
        "100min_activity": 100,
        "165min_lab":      165,
    }
    # Standard SFSU start times (HH:MM)
    START_TIMES = [
        "08:00","08:30","09:00","09:30","10:00","10:30",
        "11:00","11:30","12:00","12:30","13:00","13:30",
        "14:00","14:30","15:00","15:30","16:00","16:30",
        "17:00","17:30","18:00","18:30","19:00",
    ]

    def _next_tmp_id(self):
        """Return a temporary display ID one above the current max numeric ID."""
        max_id = 0
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.text().isdigit():
                max_id = max(max_id, int(item.text()))
        return f"~{max_id + 1}"   # ~ prefix signals unsaved

    def _add_row(self):
        # Block if an existing row is incomplete (ignore spacer rows)
        for r in range(self.table.rowCount()):
            item0 = self.table.item(r, 0)
            if item0 and item0.data(Qt.ItemDataRole.UserRole) == "_spacer":
                continue
            vals = [self._cell_text(r, c) for c in range(1, 5)]
            if not all(vals):
                self.table.selectRow(r)
                QMessageBox.warning(self, "Notice",
                    "Please fill all fields (Slot Type, Pattern, Start, End) "
                    "for the highlighted row before adding another.")
                return
        r = self.table.rowCount()
        self.table.insertRow(r)

        # Auto-ID: show estimated next ID with ~ prefix
        id_item = QTableWidgetItem(self._next_tmp_id())
        id_item.setForeground(QColor("#aaaaaa"))
        self.table.setItem(r, 0, id_item)

        # Slot type combo — triggers end-time auto-fill
        stype_cb = _placeholder_combo(
            "Slot type",
            ["50min_lecture", "75min_lecture", "100min_activity", "165min_lab"])
        stype_cb.currentTextChanged.connect(lambda _, row=r: self._auto_end_time(row))
        self.table.setCellWidget(r, 1, stype_cb)

        self.table.setCellWidget(r, 2, _placeholder_combo(
            "Day pattern", ["MW", "TR", "MWF", "F", "M", "T", "W", "R"]))

        # Start time dropdown
        start_cb = _placeholder_combo("Start", self.START_TIMES)
        start_cb.currentTextChanged.connect(lambda _, row=r: self._auto_end_time(row))
        self.table.setCellWidget(r, 3, start_cb)

        # End time dropdown — auto-filled from start+duration, but also editable
        # to reverse-calculate start time when end is set first.
        end_cb = _placeholder_combo("End", self.START_TIMES)
        end_cb.currentTextChanged.connect(lambda _, row=r: self._auto_start_time(row))
        self.table.setCellWidget(r, 4, end_cb)

        self.table.setCellWidget(r, 5, self._make_delete_btn())
        self.table.scrollToBottom()
        # Breathing room row
        self.table.insertRow(r + 1)
        spacer_item = QTableWidgetItem("")
        spacer_item.setData(Qt.ItemDataRole.UserRole, "_spacer")
        self.table.setItem(r + 1, 0, spacer_item)
        self.table.setRowHidden(r + 1, False)

    def _auto_end_time(self, row):
        """Calculate end time from start + slot type duration and populate end combo."""
        stype = self._cell_text(row, 1)
        start = self._cell_text(row, 3)
        duration = self.SLOT_DURATIONS.get(stype)
        if not duration or not start or ":" not in start:
            return
        try:
            h, m = start.split(":")
            total = int(h) * 60 + int(m) + duration
            end_str = f"{total // 60:02d}:{total % 60:02d}"
            end_w = self.table.cellWidget(row, 4)
            if isinstance(end_w, QComboBox):
                end_w.blockSignals(True)
                end_w.lineEdit().setText(end_str)
                end_w.blockSignals(False)
            else:
                item = self.table.item(row, 4)
                if item:
                    item.setText(end_str)
        except Exception:
            pass

    def _auto_start_time(self, row):
        """Calculate start time from end - slot type duration and populate start combo."""
        stype = self._cell_text(row, 1)
        end = self._cell_text(row, 4)
        duration = self.SLOT_DURATIONS.get(stype)
        if not duration or not end or ":" not in end:
            return
        try:
            h, m = end.split(":")
            total = int(h) * 60 + int(m) - duration
            if total < 0:
                return
            start_str = f"{total // 60:02d}:{total % 60:02d}"
            start_w = self.table.cellWidget(row, 3)
            if isinstance(start_w, QComboBox):
                start_w.blockSignals(True)
                start_w.lineEdit().setText(start_str)
                start_w.blockSignals(False)
        except Exception:
            pass

    def _delete_row(self, row):
        slot_id = self.table.item(row, 0).text() if self.table.item(row, 0) else ""
        if slot_id.isdigit():
            reply = QMessageBox.question(self, "Delete", f"Delete slot {slot_id}?")
            if reply != QMessageBox.StandardButton.Yes:
                return
            delete_time_slot(self.db_path, slot_id)
        self.table.removeRow(row)

    def save(self):
        rows = []
        for r in range(self.table.rowCount()):
            vals = [self._cell_text(r, c) for c in range(5)]
            if any(vals[1:]):   # skip fully empty rows
                rows.append(vals)
        save_time_slots(self.db_path, rows)
        # Reload so newly inserted rows get real DB-assigned IDs
        self.load()