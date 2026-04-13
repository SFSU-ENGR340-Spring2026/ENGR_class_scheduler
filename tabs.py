"""
ENGR Class Scheduler - DB Editor Tabs
The three QWidget tab classes used inside the left panel of the main window.
Each tab loads from / saves to the database via db.py.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
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


# ---------------------------------------------------------------------------
# Sections tab
# ---------------------------------------------------------------------------

class SectionsTab(QWidget):

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.table = QTableWidget(0, 6)   # #, Course ID, Type, Slot Type, Capacity, ×
        self.table.setHorizontalHeaderLabels(["#", "Course ID", "Type", "Slot Type", "Capacity", ""])
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 75)
        self.table.setColumnWidth(3, 140)
        self.table.setColumnWidth(4, 65)
        self.table.setColumnWidth(5, 32)
        layout.addWidget(self.table)

        add_btn = QPushButton("+ Add Section")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.load()

    def load(self):
        self.table.setRowCount(0)
        rows = sorted(load_sections(self.db_path), key=lambda x: (x[1], x[0]))
        for sid, cid, ctype, stype, cap in rows:
            self._insert_row(sid, cid, ctype, stype, cap)

    def _insert_row(self, sid="", cid="", ctype="", stype="", cap=""):
        r = self.table.rowCount()
        self.table.insertRow(r)

        short = sid.split("-")[-1] if "-" in sid else ""

        item0 = QTableWidgetItem(short)
        item1 = QTableWidgetItem(cid)
        item2 = QTableWidgetItem(ctype)
        item3 = QTableWidgetItem(stype)
        item4 = QTableWidgetItem(str(cap))

        self.table.setItem(r, 0, item0)
        self.table.setItem(r, 1, item1)
        self.table.setItem(r, 2, item2)
        self.table.setItem(r, 3, item3)
        self.table.setItem(r, 4, item4)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(28, 22)
        del_btn.setStyleSheet("color:red; font-weight:bold;")
        del_btn.clicked.connect(lambda _, row=r: self._delete_row(row))
        container = QWidget()
        cl = QHBoxLayout(container)
        cl.addWidget(del_btn)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(r, 5, container)

    def _add_row(self):
        self._insert_row()

    def _delete_row(self, row):
        short = self.table.item(row, 0).text().strip() if self.table.item(row, 0) else ""
        cid   = self.table.item(row, 1).text().strip() if self.table.item(row, 1) else ""
        sid   = f"{cid}-{short}" if cid and short else ""
        if sid:
            reply = QMessageBox.question(self, "Delete", f"Delete {sid}?")
            if reply != QMessageBox.StandardButton.Yes:
                return
            delete_section(self.db_path, sid)
        self.table.removeRow(row)
        # reconnect all delete buttons so row indices stay correct
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 5)
            if w:
                btn = w.findChild(QPushButton)
                if btn:
                    btn.clicked.disconnect()
                    btn.clicked.connect(lambda _, row=r: self._delete_row(row))

    def save(self):
        rows = []
        for r in range(self.table.rowCount()):
            short = self.table.item(r, 0).text() if self.table.item(r, 0) else ""
            cid   = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            ctype = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            stype = self.table.item(r, 3).text() if self.table.item(r, 3) else ""
            cap   = self.table.item(r, 4).text() if self.table.item(r, 4) else ""
            sid   = f"{cid}-{short}" if cid and short else ""
            if sid:
                rows.append([sid, cid, ctype, stype, cap])
        save_sections(self.db_path, rows)


# ---------------------------------------------------------------------------
# Faculty tab
# ---------------------------------------------------------------------------

class FacultyTab(QWidget):

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self._fac_codes = []  # stores faculty_code for each row so we can save/delete correctly

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        hint = QLabel("Can Teach: comma-separated course IDs  |  Check a day to mark availability")
        hint.setStyleSheet("color:#666; font-size:11px;")
        layout.addWidget(hint)

        # columns: Name, Can Teach, M, T, W, R, F, ×
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Name", "Can Teach",
            f"M\n{AVAIL_START}-{AVAIL_END}",
            f"T\n{AVAIL_START}-{AVAIL_END}",
            f"W\n{AVAIL_START}-{AVAIL_END}",
            f"R\n{AVAIL_START}-{AVAIL_END}",
            f"F\n{AVAIL_START}-{AVAIL_END}",
            ""
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(2, 72)
        self.table.setColumnWidth(3, 72)
        self.table.setColumnWidth(4, 72)
        self.table.setColumnWidth(5, 72)
        self.table.setColumnWidth(6, 72)
        self.table.setColumnWidth(7, 32)
        hdr.setMinimumHeight(36)
        layout.addWidget(self.table)

        add_btn = QPushButton("+ Add Faculty")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.load()

    def load(self):
        self.table.setRowCount(0)
        self._fac_codes = []
        for code, name, courses, avail_dict in load_faculty(self.db_path):
            self._insert_row(code, name, courses, avail_dict)

    def _insert_row(self, code="", name="", courses="", avail_dict=None):
        if avail_dict is None:
            avail_dict = {}
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._fac_codes.append(code)

        self.table.setItem(r, 0, QTableWidgetItem(name))
        teach_item = QTableWidgetItem(courses)
        teach_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r, 1, teach_item)

        # one checkbox per day column (cols 2-6)
        for col, day in enumerate(DAY_ORDER, start=2):
            cb = QCheckBox()
            cb.setChecked(day in avail_dict)
            container = QWidget()
            cl = QHBoxLayout(container)
            cl.addWidget(cb)
            cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(r, col, container)
        self.table.setRowHeight(r, 24)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(28, 22)
        del_btn.setStyleSheet("color:red; font-weight:bold;")
        del_btn.clicked.connect(lambda _, row=r: self._delete_row(row))
        container = QWidget()
        cl = QHBoxLayout(container)
        cl.addWidget(del_btn)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(r, 7, container)

    def _add_row(self):
        self._insert_row()

    def _delete_row(self, row):
        code = self._fac_codes[row] if row < len(self._fac_codes) else ""
        name = self.table.item(row, 0).text() if self.table.item(row, 0) else code
        if code:
            reply = QMessageBox.question(self, "Delete", f"Delete {name}?")
            if reply != QMessageBox.StandardButton.Yes:
                return
            delete_faculty(self.db_path, code)
        self.table.removeRow(row)
        if row < len(self._fac_codes):
            self._fac_codes.pop(row)
        # reconnect all delete buttons so row indices stay correct
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 7)
            if w:
                btn = w.findChild(QPushButton)
                if btn:
                    btn.clicked.disconnect()
                    btn.clicked.connect(lambda _, row=r: self._delete_row(row))

    def save(self):
        rows = []
        for r in range(self.table.rowCount()):
            code  = self._fac_codes[r] if r < len(self._fac_codes) else ""
            name  = self.table.item(r, 0).text() if self.table.item(r, 0) else ""
            teach = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            avail = {}
            for col, day in enumerate(DAY_ORDER, start=2):
                w = self.table.cellWidget(r, col)
                if w:
                    cb = w.findChild(QCheckBox)
                    if cb and cb.isChecked():
                        avail[day] = (AVAIL_START, AVAIL_END)
            rows.append((code, name, teach, avail))
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

        self.table = QTableWidget(0, 6)  # ID, Slot Type, Day Pattern, Start, End, ×
        self.table.setHorizontalHeaderLabels(["ID", "Slot Type", "Day Pattern", "Start", "End", ""])
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 32)
        layout.addWidget(self.table)

        add_btn = QPushButton("+ Add Time Slot")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.load()

    def load(self):
        self.table.setRowCount(0)
        rows = sorted(load_time_slots(self.db_path), key=lambda x: (x[1], x[2], x[3]))
        for sid, stype, pattern, start, end in rows:
            self._insert_row(str(sid), stype, pattern, start, end)

    def _insert_row(self, slot_id="NEW", stype="", pattern="", start="", end=""):
        r = self.table.rowCount()
        self.table.insertRow(r)

        item0 = QTableWidgetItem(slot_id)
        item1 = QTableWidgetItem(stype)
        item2 = QTableWidgetItem(pattern)
        item3 = QTableWidgetItem(start)
        item4 = QTableWidgetItem(end)

        self.table.setItem(r, 0, item0)
        self.table.setItem(r, 1, item1)
        self.table.setItem(r, 2, item2)
        self.table.setItem(r, 3, item3)
        self.table.setItem(r, 4, item4)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(28, 22)
        del_btn.setStyleSheet("color:red; font-weight:bold;")
        del_btn.clicked.connect(lambda _, row=r: self._delete_row(row))
        container = QWidget()
        cl = QHBoxLayout(container)
        cl.addWidget(del_btn)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(r, 5, container)

    def _add_row(self):
        self._insert_row()

    def _delete_row(self, row):
        slot_id = self.table.item(row, 0).text() if self.table.item(row, 0) else ""
        if slot_id.isdigit():
            reply = QMessageBox.question(self, "Delete", f"Delete slot {slot_id}?")
            if reply != QMessageBox.StandardButton.Yes:
                return
            delete_time_slot(self.db_path, slot_id)
        self.table.removeRow(row)
        # reconnect all delete buttons so row indices stay correct
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 5)
            if w:
                btn = w.findChild(QPushButton)
                if btn:
                    btn.clicked.disconnect()
                    btn.clicked.connect(lambda _, row=r: self._delete_row(row))

    def save(self):
        rows = []
        for r in range(self.table.rowCount()):
            slot_id = self.table.item(r, 0).text() if self.table.item(r, 0) else ""
            stype   = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            pattern = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            start   = self.table.item(r, 3).text() if self.table.item(r, 3) else ""
            end     = self.table.item(r, 4).text() if self.table.item(r, 4) else ""
            rows.append([slot_id, stype, pattern, start, end])
        save_time_slots(self.db_path, rows)