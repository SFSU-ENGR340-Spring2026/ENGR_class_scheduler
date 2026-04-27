"""
ENGR Class Scheduler - DB Editor Tabs
SectionsTab, FacultyTab, TimeSlotsTab — each loads/saves via db.py.
"""

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QIntValidator, QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSizePolicy, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from db import (
    load_sections, save_sections, delete_section,
    load_faculty,  save_faculty,  delete_faculty,
    load_time_slots, save_time_slots, delete_time_slot,
)

AVAIL_START   = "08:00"
AVAIL_END     = "18:30"
DAY_ORDER     = ["M", "T", "W", "R", "F"]
SLIDER_MIN    = 7
SLIDER_MAX    = 22
STEPS         = (SLIDER_MAX - SLIDER_MIN) * 2

COURSE_LIST = [
    "ENGR100","ENGR101","ENGR102","ENGR104","ENGR200","ENGR201",
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
    "ENGR852","ENGR856","ENGR867","ENGR869","ENGR890",
]
MAJOR_LIST  = ["All 4","CE","Civil","Civil/ME","CompE","EE","EE/CE",
               "EE/CE/ME","EE/CompE","Grad","ME","MSCivil","MSECE","MSME"]
ROOM_LIST   = ["Need Room","SEIC 101","SEIC 103","SEIC 400","SEIC 401",
               "SEIC 402","SEIC 403","SEIC 412","SEIC 414","SEIC 416",
               "SEIC 417","SCI 111","SCI 115","SCI 214",
               "SEIC 412 or SCI 214","SEIC 416 or SEIC 417",
               "SEIC 412 or SEIC 416 or SEIC 417"]
FACULTY_LIST = (
    [f"TTF {i:02d}" for i in range(1, 20)] +
    [f"GTA {i:02d}" for i in range(1, 8)]  +
    [f"LF {i:02d}"  for i in range(1, 16)]
)
SLOT_TYPES  = ["50min_lecture","75min_lecture","100min_activity","165min_lab"]
SLOT_DUR    = {"50min_lecture":50,"75min_lecture":75,"100min_activity":100,"165min_lab":165}
START_TIMES = [f"{h:02d}:{m:02d}" for h in range(8, 20) for m in (0, 30)] + ["20:00"]


# ── helpers ──────────────────────────────────────────────────────────────────

def _min2step(hhmm):
    try:
        h, m = hhmm.split(":")
        return max(0, min(STEPS, (int(h)*60 + int(m) - SLIDER_MIN*60) // 30))
    except Exception:
        return 0

def _step2time(s):
    t = SLIDER_MIN*60 + s*30
    return f"{t//60:02d}:{t%60:02d}"

def _combo(placeholder, options):
    cb = QComboBox(); cb.setEditable(True)
    cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    cb.lineEdit().setPlaceholderText(placeholder)
    cb.addItems([""]+list(options)); cb.setCurrentIndex(0)
    cb.setStyleSheet("QComboBox { border: none; }")
    return cb

def _spacer_row():
    item = QTableWidgetItem("")
    item.setData(Qt.ItemDataRole.UserRole, "_spacer")
    return item

def _del_btn(callback):
    """callback receives the QPushButton so caller can find which row."""
    btn = QPushButton("×"); btn.setFixedSize(28, 22)
    btn.setStyleSheet("color:red;font-weight:bold;")
    btn.clicked.connect(lambda _checked, b=btn: callback(b))
    w = QWidget(); lay = QHBoxLayout(w)
    lay.addWidget(btn); lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.setContentsMargins(0,0,0,0)
    return w


class IntegerDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        e = QLineEdit(parent); e.setValidator(QIntValidator(0, 999, e))
        return e


# ── Time-range slider ─────────────────────────────────────────────────────────

class TimeRangeSlider(QWidget):
    HW = 12; TH = 6; LH = 18; CBR = 7; CBG = 6

    def __init__(self, avail, st, et, parent=None):
        super().__init__(parent)
        self._avail = avail
        self._lo = _min2step(st); self._hi = _min2step(et)
        self._drag = None
        self.setMinimumWidth(110); self.setFixedHeight(62)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    @property
    def is_available(self): return self._avail
    @property
    def start_time(self): return _step2time(self._lo)
    @property
    def end_time(self):   return _step2time(self._hi)

    def _track(self):
        x = self.CBR*2 + self.CBG + self.HW
        w = self.width() - x - self.HW
        y = self.LH + (self.height()-self.LH-self.TH)//2
        return x, y, w

    def _s2px(self, s):
        x,_,w = self._track(); return x + int(s/STEPS*w)

    def _px2s(self, px):
        x,_,w = self._track()
        return max(0, min(STEPS, round((px-x)/w*STEPS))) if w else 0

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x, y, tw = self._track()
        cbx = self.CBR+1; cby = self.LH+(self.height()-self.LH)//2
        p.setPen(QPen(QColor("#888"), 1.5))
        p.setBrush(QColor("#4e79a7") if self._avail else QColor("#ffffff"))
        p.drawEllipse(cbx-self.CBR, cby-self.CBR, self.CBR*2, self.CBR*2)
        if self._avail:
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawLine(cbx-3, cby, cbx-1, cby+2); p.drawLine(cbx-1, cby+2, cbx+3, cby-2)
        if not self._avail:
            p.setPen(QColor("#aaaaaa")); f=QFont(); f.setPointSize(9); p.setFont(f)
            p.drawText(self.CBR*2+self.CBG+2, cby+4, "Not available"); p.end(); return
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#dddddd"))
        p.drawRoundedRect(x, y, tw, self.TH, 3, 3)
        lo_px = self._s2px(self._lo); hi_px = self._s2px(self._hi)
        p.setBrush(QColor("#4e79a7"))
        p.drawRoundedRect(lo_px, y, max(0, hi_px-lo_px), self.TH, 3, 3)
        p.setPen(QPen(QColor("#bbbbbb"), 1))
        for s in range(0, STEPS+1, 2):
            tx = self._s2px(s); p.drawLine(tx, y+self.TH, tx, y+self.TH+3)
        for s in (self._lo, self._hi):
            hx = self._s2px(s); hw = self.HW
            p.setPen(QPen(QColor("#1a4f7f"), 1)); p.setBrush(QColor("#2a5f8f"))
            p.drawRoundedRect(hx-hw//2, y-5, hw, self.TH+10, 3, 3)
        f=QFont(); f.setPointSize(8); p.setFont(f); p.setPen(QColor("#333333"))
        p.drawText(QRect(x,2,tw//2,self.LH-2), Qt.AlignmentFlag.AlignLeft,  _step2time(self._lo))
        p.drawText(QRect(x+tw//2,2,tw//2,self.LH-2), Qt.AlignmentFlag.AlignRight, _step2time(self._hi))
        p.end()

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton: return
        px = ev.position().x(); cbx=self.CBR+1; cby=self.LH+(self.height()-self.LH)//2
        if abs(px-cbx)<=self.CBR+4 and abs(ev.position().y()-cby)<=self.CBR+4:
            self._avail = not self._avail; self.update(); return
        if not self._avail: return
        self._drag = 'lo' if abs(px-self._s2px(self._lo))<=abs(px-self._s2px(self._hi)) else 'hi'

    def mouseMoveEvent(self, ev):
        if not self._drag or not self._avail: return
        s = self._px2s(ev.position().x())
        if self._drag=='lo': self._lo = max(0, min(self._hi-1, s))
        else: self._hi = max(self._lo+1, min(STEPS, s))
        self.update()

    def mouseReleaseEvent(self, ev): self._drag = None


# ── SectionsTab ───────────────────────────────────────────────────────────────

class SectionsTab(QWidget):
    def __init__(self, db_path):
        super().__init__(); self.db_path = db_path
        lay = QVBoxLayout(self); lay.setContentsMargins(4,4,4,4)
        self.filter_edit = QLineEdit(); self.filter_edit.setPlaceholderText("Filter sections...")
        self.filter_edit.textChanged.connect(self._filter); lay.addWidget(self.filter_edit)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            ["#","Course ID","Type","Slot Type","Cap","Major","Room","Freeze Slot","",""])
        self.table.verticalHeader().setVisible(False); self.table.setWordWrap(True)
        hdr = self.table.horizontalHeader()
        modes = [QHeaderView.ResizeMode.Fixed, QHeaderView.ResizeMode.Fixed,
                 QHeaderView.ResizeMode.Fixed, QHeaderView.ResizeMode.ResizeToContents,
                 QHeaderView.ResizeMode.Fixed, QHeaderView.ResizeMode.ResizeToContents,
                 QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.ResizeToContents,
                 QHeaderView.ResizeMode.Fixed,  QHeaderView.ResizeMode.Fixed]
        for i, m in enumerate(modes): hdr.setSectionResizeMode(i, m)
        for col, w in [(0,40),(1,90),(2,68),(4,40),(8,30),(9,16)]: self.table.setColumnWidth(col,w)
        self.table.setColumnHidden(2, True)
        for c in (0,4,7): self.table.setItemDelegateForColumn(c, IntegerDelegate(self.table))
        lay.addWidget(self.table)
        btn = QPushButton("+ Add Section"); btn.clicked.connect(self._add)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft); lay.addSpacing(12)
        self.load()

    def _filter(self, text):
        t = text.lower()
        for r in range(self.table.rowCount()):
            self.table.setRowHidden(r, t and not any(
                self._val(r,c) and t in self._val(r,c).lower() for c in range(8)))

    def load(self):
        self.table.setRowCount(0)
        for row in sorted(load_sections(self.db_path), key=lambda x:(x[1],x[0])):
            if len(row)==5: sid,cid,ct,st,cap=row; maj=lr=frz=""
            else: sid,cid,ct,st,cap,maj,lr,frz=row
            self._insert(sid,cid,ct,st,cap,maj or "",lr or "","" if frz is None else str(frz))

    def _insert(self, sid="",cid="",ct="",st="",cap="",maj="",lr="",frz=""):
        r = self.table.rowCount(); self.table.insertRow(r)
        short = sid.split("-")[-1] if "-" in str(sid) else ""
        for c,v in enumerate([short,cid,ct,st,str(cap),maj,lr,frz]):
            item = QTableWidgetItem(v)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r,c,item)
        self.table.setCellWidget(r,8,_del_btn(self._del_by_btn8))
        self.table.resizeRowToContents(r)

    def _del_by_btn8(self, btn):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r,8)
            if w and w.findChild(QPushButton) is btn:
                self._delete(r); return

    def _val(self, r, c):
        w = self.table.cellWidget(r,c)
        if isinstance(w, QComboBox): return w.currentText().strip()
        item = self.table.item(r,c); return item.text().strip() if item else ""

    def _add(self):
        for r in range(self.table.rowCount()):
            i0 = self.table.item(r,0)
            if i0 and i0.data(Qt.ItemDataRole.UserRole)=="_spacer": continue
            if not self._val(r,0) or not self._val(r,1):
                self.table.selectRow(r)
                QMessageBox.warning(self,"Notice","Fill # and Course ID for highlighted row first.")
                return
        r = self.table.rowCount(); self.table.insertRow(r)
        self.table.setItem(r,0,QTableWidgetItem(""))
        self.table.setCellWidget(r,1,_combo("e.g. ENGR340", COURSE_LIST))
        self.table.setCellWidget(r,2,_combo("Type",["Lecture","Lab","Activity"]))
        self.table.setCellWidget(r,3,_combo("Slot type", SLOT_TYPES))
        self.table.setItem(r,4,QTableWidgetItem(""))
        self.table.setCellWidget(r,5,_combo("Major", MAJOR_LIST))
        self.table.setCellWidget(r,6,_combo("Room", ROOM_LIST))
        self.table.setItem(r,7,QTableWidgetItem(""))
        self.table.setCellWidget(r,8,_del_btn(self._del_by_btn8))
        self.table.insertRow(r+1); self.table.setItem(r+1,0,_spacer_row())
        self.table.scrollToBottom()

    def _delete(self, row):
        short=self._val(row,0); cid=self._val(row,1)
        sid=f"{cid}-{short}" if cid and short else ""
        if sid:
            if QMessageBox.question(self,"Delete",f"Delete {sid}?")!=QMessageBox.StandardButton.Yes: return
            delete_section(self.db_path, sid)
        self.table.removeRow(row)

    def save(self):
        rows=[]
        for r in range(self.table.rowCount()):
            short=self._val(r,0); cid=self._val(r,1)
            sid=f"{cid}-{short}" if cid and short else ""
            if sid:
                rows.append([sid,cid,self._val(r,2),self._val(r,3),self._val(r,4),
                             self._val(r,5),self._val(r,6),self._val(r,7)])
        save_sections(self.db_path, rows)


# ── FacultyTab ────────────────────────────────────────────────────────────────

class FacultyTab(QWidget):
    def __init__(self, db_path):
        super().__init__(); self.db_path = db_path
        lay = QVBoxLayout(self); lay.setContentsMargins(4,4,4,4)
        hint = QLabel("Code: unique ID  |  WTU: teaching units  |  "
                      "Can Teach: comma-separated IDs  |  "
                      "Drag slider handles to set availability per day")
        hint.setStyleSheet("color:#666;font-size:11px;"); hint.setWordWrap(True)
        lay.addWidget(hint)
        self.filter_edit = QLineEdit(); self.filter_edit.setPlaceholderText("Filter faculty...")
        self.filter_edit.textChanged.connect(self._filter); lay.addWidget(self.filter_edit)
        self.table = QTableWidget(0,11)
        self.table.setHorizontalHeaderLabels(
            ["Code","Name","WTU","Can Teach","Mon","Tue","Wed","Thu","Fri","",""])
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        for i in range(4,11): hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0,72); self.table.setColumnWidth(2,45)
        self.table.setColumnWidth(3,185)
        for c in range(4,9): self.table.setColumnWidth(c,145)
        self.table.setColumnWidth(9,28); self.table.setColumnWidth(10,16)
        hdr.setMinimumHeight(36); lay.addWidget(self.table)
        btn = QPushButton("+ Add Faculty"); btn.clicked.connect(self._add)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft); lay.addSpacing(12)
        self.load()

    def _filter(self, text):
        t = text.lower()
        for r in range(self.table.rowCount()):
            self.table.setRowHidden(r, t and not any(
                self.table.item(r,c) and t in self.table.item(r,c).text().lower()
                for c in range(4)))

    def load(self):
        self.table.setRowCount(0)
        for code,name,wtu,courses,avail in load_faculty(self.db_path):
            self._insert(code,name,wtu,courses,avail)

    def _insert(self, code="",name="",wtu="",courses="",avail=None):
        if avail is None: avail={}
        r = self.table.rowCount(); self.table.insertRow(r)
        self.table.setItem(r,0,QTableWidgetItem(code))
        self.table.setItem(r,1,QTableWidgetItem(name))
        wi = QTableWidgetItem(wtu); wi.setTextAlignment(Qt.AlignmentFlag.AlignCenter|Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r,2,wi)
        ti = QTableWidgetItem(courses); ti.setTextAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r,3,ti)
        for col,day in enumerate(DAY_ORDER,4):
            if day in avail and avail[day]: avail_on=True; st,et=avail[day][0]
            else: avail_on=False; st,et=AVAIL_START,AVAIL_END
            self.table.setCellWidget(r,col,TimeRangeSlider(avail_on,st,et))
        self.table.setRowHeight(r,68)
        self.table.setCellWidget(r,9,_del_btn(self._del_by_btn9))

    def _del_by_btn9(self, btn):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r,9)
            if w and w.findChild(QPushButton) is btn:
                self._delete(r); return

    def _add(self):
        for r in range(self.table.rowCount()):
            i0=self.table.item(r,0)
            if i0 and i0.data(Qt.ItemDataRole.UserRole)=="_spacer": continue
            w=self.table.cellWidget(r,0)
            code=(w.currentText().strip() if isinstance(w,QComboBox)
                  else (self.table.item(r,0).text().strip() if self.table.item(r,0) else ""))
            if not code:
                self.table.selectRow(r); self.table.scrollToBottom()
                QMessageBox.warning(self,"Notice","Enter Faculty Code for highlighted row first.")
                return
        r=self.table.rowCount(); self.table.insertRow(r)
        self.table.setCellWidget(r,0,_combo("e.g. TTF01", FACULTY_LIST))
        self.table.setItem(r,1,QTableWidgetItem(""))
        self.table.setItem(r,2,QTableWidgetItem(""))
        self.table.setCellWidget(r,3,_combo("e.g. ENGR340, ENGR221", COURSE_LIST))
        for col in range(4,9): self.table.setCellWidget(r,col,TimeRangeSlider(False,AVAIL_START,AVAIL_END))
        self.table.setRowHeight(r,68)
        self.table.setCellWidget(r,9,_del_btn(self._del_by_btn9))
        self.table.insertRow(r+1); si=_spacer_row(); si.setData(Qt.ItemDataRole.UserRole,"_spacer")
        self.table.setItem(r+1,0,si); self.table.setRowHeight(r+1,8)
        self.table.scrollToBottom()

    def _delete(self, row):
        w0=self.table.cellWidget(row,0)
        code=(w0.currentText().strip() if isinstance(w0,QComboBox)
              else (self.table.item(row,0).text().strip() if self.table.item(row,0) else ""))
        name=self.table.item(row,1).text().strip() if self.table.item(row,1) else code
        if code:
            if QMessageBox.question(self,"Delete",f"Delete {name} ({code})?")!=QMessageBox.StandardButton.Yes: return
            delete_faculty(self.db_path, code)
        self.table.removeRow(row)

    def save(self):
        errors=[]; seen=set(); rows=[]
        for r in range(self.table.rowCount()):
            w0=self.table.cellWidget(r,0)
            code=(w0.currentText().strip() if isinstance(w0,QComboBox)
                  else (self.table.item(r,0).text().strip() if self.table.item(r,0) else ""))
            if not code: continue
            if code in seen: errors.append(f"Row {r+1}: duplicate '{code}'."); continue
            seen.add(code)
            name=self.table.item(r,1).text().strip() if self.table.item(r,1) else ""
            wtu =self.table.item(r,2).text().strip() if self.table.item(r,2) else ""
            w3=self.table.cellWidget(r,3)
            teach=(w3.currentText().strip() if isinstance(w3,QComboBox)
                   else (self.table.item(r,3).text().strip() if self.table.item(r,3) else ""))
            avail={day:[(self.table.cellWidget(r,col).start_time,self.table.cellWidget(r,col).end_time)]
                   for col,day in enumerate(DAY_ORDER,4)
                   if self.table.cellWidget(r,col) and self.table.cellWidget(r,col).is_available}
            rows.append((code,name,wtu,teach,avail))
        if errors: QMessageBox.warning(self,"Save Errors","\n".join(errors)); return
        save_faculty(self.db_path, rows)


# ── TimeSlotsTab ──────────────────────────────────────────────────────────────

class TimeSlotsTab(QWidget):
    def __init__(self, db_path):
        super().__init__(); self.db_path = db_path
        lay = QVBoxLayout(self); lay.setContentsMargins(4,4,4,4)
        self.filter_edit = QLineEdit(); self.filter_edit.setPlaceholderText("Filter time slots...")
        self.filter_edit.textChanged.connect(self._filter); lay.addWidget(self.filter_edit)
        self.table = QTableWidget(0,6)
        self.table.setHorizontalHeaderLabels(["ID","Slot Type","Day Pattern","Start","End",""])
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        for i in range(6): hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
        for col,w in [(0,40),(1,140),(2,100),(3,60),(4,60),(5,32)]: self.table.setColumnWidth(col,w)
        lay.addWidget(self.table)
        btn = QPushButton("+ Add Time Slot"); btn.clicked.connect(self._add)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft); lay.addSpacing(12)
        self.load()

    def _filter(self, text):
        t = text.lower()
        for r in range(self.table.rowCount()):
            self.table.setRowHidden(r, t and not any(
                self.table.item(r,c) and t in self.table.item(r,c).text().lower()
                for c in range(5)))

    def load(self):
        self.table.setRowCount(0)
        for sid,st,pat,s,e in sorted(load_time_slots(self.db_path), key=lambda x:x[0]):
            self._insert(str(sid),st,pat,s,e)

    def _insert(self, sid="NEW",st="",pat="",s="",e=""):
        r=self.table.rowCount(); self.table.insertRow(r)
        for c,v in enumerate([sid,st,pat,s,e]): self.table.setItem(r,c,QTableWidgetItem(v))
        self.table.setCellWidget(r,5,_del_btn(self._del_by_btn5))

    def _del_by_btn5(self, btn):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r,5)
            if w and w.findChild(QPushButton) is btn:
                self._delete(r); return

    def _val(self, r, c):
        w=self.table.cellWidget(r,c)
        if isinstance(w,QComboBox): return w.currentText().strip()
        item=self.table.item(r,c); return item.text().strip() if item else ""

    def _next_id(self):
        mx=max((int(self.table.item(r,0).text()) for r in range(self.table.rowCount())
                if self.table.item(r,0) and self.table.item(r,0).text().isdigit()), default=0)
        return f"~{mx+1}"

    def _add(self):
        for r in range(self.table.rowCount()):
            i0=self.table.item(r,0)
            if i0 and i0.data(Qt.ItemDataRole.UserRole)=="_spacer": continue
            if not all(self._val(r,c) for c in range(1,5)):
                self.table.selectRow(r)
                QMessageBox.warning(self,"Notice","Fill all fields for highlighted row first.")
                return
        r=self.table.rowCount(); self.table.insertRow(r)
        id_item=QTableWidgetItem(self._next_id()); id_item.setForeground(QColor("#aaaaaa"))
        self.table.setItem(r,0,id_item)
        st_cb=_combo("Slot type", SLOT_TYPES)
        st_cb.currentTextChanged.connect(lambda _,row=r: self._auto_end(row))
        self.table.setCellWidget(r,1,st_cb)
        self.table.setCellWidget(r,2,_combo("Day pattern",["MW","TR","MWF","F","M","T","W","R"]))
        s_cb=_combo("Start", START_TIMES); s_cb.currentTextChanged.connect(lambda _,row=r: self._auto_end(row))
        self.table.setCellWidget(r,3,s_cb)
        e_cb=_combo("End", START_TIMES); e_cb.currentTextChanged.connect(lambda _,row=r: self._auto_start(row))
        self.table.setCellWidget(r,4,e_cb)
        self.table.setCellWidget(r,5,_del_btn(self._del_by_btn5))
        self.table.insertRow(r+1); self.table.setItem(r+1,0,_spacer_row())
        self.table.scrollToBottom()

    def _auto_end(self, row):
        st=self._val(row,1); s=self._val(row,3); dur=SLOT_DUR.get(st)
        if not dur or not s or ":" not in s: return
        try:
            h,m=s.split(":"); t=int(h)*60+int(m)+dur
            w=self.table.cellWidget(row,4)
            if isinstance(w,QComboBox): w.blockSignals(True); w.lineEdit().setText(f"{t//60:02d}:{t%60:02d}"); w.blockSignals(False)
            elif self.table.item(row,4): self.table.item(row,4).setText(f"{t//60:02d}:{t%60:02d}")
        except Exception: pass

    def _auto_start(self, row):
        st=self._val(row,1); e=self._val(row,4); dur=SLOT_DUR.get(st)
        if not dur or not e or ":" not in e: return
        try:
            h,m=e.split(":"); t=int(h)*60+int(m)-dur
            if t<0: return
            w=self.table.cellWidget(row,3)
            if isinstance(w,QComboBox): w.blockSignals(True); w.lineEdit().setText(f"{t//60:02d}:{t%60:02d}"); w.blockSignals(False)
        except Exception: pass

    def _delete(self, row):
        sid=self.table.item(row,0).text() if self.table.item(row,0) else ""
        if sid.isdigit():
            if QMessageBox.question(self,"Delete",f"Delete slot {sid}?")!=QMessageBox.StandardButton.Yes: return
            delete_time_slot(self.db_path, sid)
        self.table.removeRow(row)

    def save(self):
        rows=[[self._val(r,c) for c in range(5)] for r in range(self.table.rowCount())
              if any(self._val(r,c) for c in range(1,5))]
        save_time_slots(self.db_path, rows); self.load()
