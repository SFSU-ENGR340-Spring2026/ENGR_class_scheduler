"""
ENGR Class Scheduler - DB Editor Tabs
The three QWidget tab classes used inside the left panel of the main window.
Each tab loads from / saves to the database via db.py.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
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
# Helpers
# ---------------------------------------------------------------------------

class IntegerDelegate(QStyledItemDelegate):
    """Forces table cells to only accept integer input."""
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        # Allow numbers from 0 to 200, which should be sufficient for class capacities and time slot counts
        editor.setValidator(QIntValidator(0, 200, editor))
        return editor

# ---------------------------------------------------------------------------
# Sections tab
# ---------------------------------------------------------------------------

class SectionsTab(QWidget):

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter sections...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)
        
        self.table = QTableWidget(0, 6)   # #, Course ID, Type, Slot Type, Capacity, ×
        self.table.setHorizontalHeaderLabels(["Section", "Course ID", "Type", "Slot Type", "Capacity", ""])
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
        self.int_delegate = IntegerDelegate(self.table)
        self.table.setItemDelegateForColumn(0, self.int_delegate) # Section column
        self.table.setItemDelegateForColumn(4, self.int_delegate) # Capacity column
        add_btn = QPushButton("+ Add Section")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.load()

    def _apply_filter(self, text):
        search_term = text.lower()
        for r in range(self.table.rowCount()):
            match = False
            # Check columns 0 through 4 (the text columns)
            for c in range(5):
                item = self.table.item(r, c)
                if item and search_term in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(r, not match)

    def load(self):
        self.table.setRowCount(0)
        rows = sorted(load_sections(self.db_path), key=lambda x: (x[1], x[0]))
        for sid, cid, ctype, stype, cap in rows:
            self._insert_row(sid, cid, ctype, stype, cap)

    def _insert_row(self, sid="", cid="", ctype="", stype="", cap=""):
        r = self.table.rowCount()
        self.table.insertRow(r)

        short = sid.split("-")[-1] if "-" in sid else ""

        self.table.setItem(r, 0, QTableWidgetItem(short))
        self.table.setItem(r, 1, QTableWidgetItem(cid))
        self.table.setItem(r, 2, QTableWidgetItem(ctype))
        self.table.setItem(r, 3, QTableWidgetItem(stype))
        self.table.setItem(r, 4, QTableWidgetItem(str(cap)))
        self.table.setCellWidget(r, 5, self._make_delete_btn(r))

    def _make_delete_btn(self, row):
        """Return a centred × button wired to delete the given row."""
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
        # Prevent multiple blank rows by checking if a row with no Course ID and # exists
        for r in range(self.table.rowCount()):
            """Find the row that owns this button and delete it."""
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 5)
            if w and w.findChild(QPushButton) is btn:
                self._delete_row(r)
                return

    def _add_row(self):
        # Scan for any row missing EITHER the Section # or Course ID
        for r in range(self.table.rowCount()):
            item_short = self.table.item(r, 0)
            item_cid = self.table.item(r, 1)
            
            short = item_short.text().strip() if item_short else ""
            cid = item_cid.text().strip() if item_cid else ""
            
            if not short or not cid:
                self.table.selectRow(r)
                self.table.scrollToItem(item_short)
                QMessageBox.warning(self, "Notice", "Please fill out the Course ID and # for the highlighted row before adding a new one.")
                return
                
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
# Custom Time Range Widget
# ---------------------------------------------------------------------------

class TimeRangeWidget(QWidget):
    def __init__(self, is_avail, st, et):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        # Checkbox
        self.cb = QCheckBox("Availability")
        self.cb.setChecked(is_avail)
        layout.addWidget(self.cb, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Text fields for Start and End time
        time_layout = QHBoxLayout()
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(2)
        
        self.start_edit = QLineEdit(st)
        self.start_edit.setPlaceholderText("08:00")
        
        self.dash_label = QLabel("-")
        
        self.end_edit = QLineEdit(et)
        self.end_edit.setPlaceholderText("18:30")
        
        time_layout.addWidget(self.start_edit)
        time_layout.addWidget(self.dash_label)
        time_layout.addWidget(self.end_edit)
        
        layout.addLayout(time_layout)

        # --- NEW: Connect checkbox to the toggle function ---
        self.cb.toggled.connect(self._toggle_times)
        
        # Run it once immediately to set the initial visible state 
        # when the table first loads
        self._toggle_times(is_avail)

    def _toggle_times(self, checked):
        """Hides or shows the time boxes based on the checkbox state."""
        self.start_edit.setVisible(checked)
        self.dash_label.setVisible(checked)
        self.end_edit.setVisible(checked)
# ---------------------------------------------------------------------------
# Faculty tab
# ---------------------------------------------------------------------------

class FacultyTab(QWidget):

    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        hint = QLabel("Code: unique faculty ID  |  Can Teach: comma-separated course IDs  |  Check a day to mark availability")
        hint.setStyleSheet("color:#666; font-size:11px;")
        layout.addWidget(hint)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter faculty...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

       # columns: Code, Name, WTU, Can Teach, M, T, W, R, F, ×
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "Code", "Name", "WTU", "Can Teach",
            "M", "T", "W", "R", "F",
            ""
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)          # Code
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Name
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)          # WTU
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)          # Can Teach
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)          # M
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)          # T
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)          # W
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)          # R
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)          # F
        hdr.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)          # ×
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(2, 50)
        self.table.setColumnWidth(3, 200)  # Can Teach
        self.table.setColumnWidth(4, 125)  # M
        self.table.setColumnWidth(5, 125)  # T
        self.table.setColumnWidth(6, 125)  # W
        self.table.setColumnWidth(7, 125)  # R
        self.table.setColumnWidth(8, 125)  # F
        self.table.setColumnWidth(9, 32)   # ×
        hdr.setMinimumHeight(36)
        layout.addWidget(self.table)

        add_btn = QPushButton("+ Add Faculty")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.load()

    def _apply_filter(self, text):
        search_term = text.lower()
        for r in range(self.table.rowCount()):
            match = False
            # Check Code (0), Name (1), and Can Teach (3)
            for c in (0, 1, 3):
                item = self.table.item(r, c)
                if item and search_term in item.text().lower():
                    match = True
                    break
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

        # WTU column
        wtu_item = QTableWidgetItem(wtu)
        wtu_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r, 2, wtu_item)

        # Can Teach column
        self.table.setItem(r, 3, QTableWidgetItem(courses))

        # one TimeRangeWidget per day column (cols 4-8)
        for col, day in enumerate(DAY_ORDER, start=4):
            if day in avail_dict:
                is_avail = True
                st, et = avail_dict[day]
            else:
                is_avail = False
                st, et = "08:00", "18:30"

            time_widget = TimeRangeWidget(is_avail, st, et)
            self.table.setCellWidget(r, col, time_widget)

        self.table.setRowHeight(r, 85) # Taller row to fit vertical stack

        self.table.setCellWidget(r, 9, self._make_delete_btn(r))

    def _make_delete_btn(self, row):
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
        # Scan for any row missing the Faculty Code
        for r in range(self.table.rowCount()):
            item_code = self.table.item(r, 0)
            code = item_code.text().strip() if item_code else ""

            if not code:
                # If there's already an empty row, highlight it and warn the user
                self.table.selectRow(r)
                if item_code:
                    self.table.scrollToItem(item_code)
                QMessageBox.warning(self, "Notice", "Please enter a Faculty Code for the highlighted row before adding a new one.")
                return

        # Insert the new row
        self._insert_row()

        # Automatically focus and start editing the "Code" cell of the new row
        new_row = self.table.rowCount() - 1
        self.table.setCurrentCell(new_row, 0)
        self.table.editItem(self.table.item(new_row, 0))

    def _delete_row(self, row):
        code = self.table.item(row, 0).text().strip() if self.table.item(row, 0) else ""
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
            code  = self.table.item(r, 0).text().strip() if self.table.item(r, 0) else ""
            name  = self.table.item(r, 1).text().strip() if self.table.item(r, 1) else ""
            wtu   = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else ""
            teach = self.table.item(r, 3).text().strip() if self.table.item(r, 3) else ""

            if not code:
                errors.append(f"Row {r + 1}: Code is required.")
                continue
            if code in seen_codes:
                errors.append(f"Row {r + 1}: Duplicate code '{code}'.")
                continue
            seen_codes.add(code)

            avail = {}
            for col, day in enumerate(DAY_ORDER, start=4):
                w = self.table.cellWidget(r, col)
                # Correctly check the internal CheckBox and QLineEdits
                if w and w.cb.isChecked():
                    st = w.start_edit.text().strip()
                    et = w.end_edit.text().strip()
                    avail[day] = (st, et)
                    
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
        self.table.setColumnHidden(0, True)
        layout.addWidget(self.table)

        add_btn = QPushButton("+ Add Time Slot")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.load()

    def _apply_filter(self, text):
        search_term = text.lower()
        for r in range(self.table.rowCount()):
            match = False
            # Check columns 0 through 4
            for c in range(5):
                item = self.table.item(r, c)
                if item and search_term in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(r, not match)

    def load(self):
        self.table.setRowCount(0)
        rows = sorted(load_time_slots(self.db_path), key=lambda x: (x[1], x[2], x[3]))
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
        self.table.setCellWidget(r, 5, self._make_delete_btn(r))

    def _make_delete_btn(self, row):
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

    def _add_row(self):
        # Scan for any row missing its required fields instead of forcing a save
        for r in range(self.table.rowCount()):
            stype   = self.table.item(r, 1).text().strip() if self.table.item(r, 1) else ""
            pattern = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else ""
            start   = self.table.item(r, 3).text().strip() if self.table.item(r, 3) else ""
            end     = self.table.item(r, 4).text().strip() if self.table.item(r, 4) else ""
            
            if not stype or not pattern or not start or not end:
                self.table.selectRow(r)
                item_id = self.table.item(r, 0)
                if item_id:
                    self.table.scrollToItem(item_id)
                QMessageBox.warning(self, "Notice", "Please fill out all fields (Slot Type, Pattern, Start, End) for the highlighted row before adding another.")
                return
                
        self._insert_row()

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
            slot_id = self.table.item(r, 0).text() if self.table.item(r, 0) else ""
            stype   = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            pattern = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            start   = self.table.item(r, 3).text() if self.table.item(r, 3) else ""
            end     = self.table.item(r, 4).text() if self.table.item(r, 4) else ""
            rows.append([slot_id, stype, pattern, start, end])
        save_time_slots(self.db_path, rows)
        # Reload so newly inserted rows get their real DB-assigned IDs,
        # preventing duplicate inserts on a subsequent save.
        self.load()
