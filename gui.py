"""
ENGR Class Scheduler - GUI
Main window, Gantt chart, and entry point.
Tab classes live in tabs.py. DB functions live in db.py.
"""

import platform
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import plotly.graph_objects as go

from PySide6.QtCore import Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import sqlite3

from tabs import SectionsTab, FacultyTab, TimeSlotsTab
from solver import Scheduler, SHARED_SECTIONS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PALETTE = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#aecfd6",
    "#d37295", "#fabfd2", "#8cd17d", "#86bcb6", "#499894",
    "#f1ce63", "#79706e", "#d4a6c8", "#b6992d", "#a0cbe8",
]
DAY_ORDER  = ["M", "T", "W", "R", "F"]
DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
DAY_SPAN  = 2.6    # taller rows so bars have more vertical room
DAY_GAP    = 0.3
BAR_PAD    = 0.015
MAX_UNDO   = 10

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def time_to_minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _open_folder(path):
    system = platform.system()
    if system == "Windows":
        subprocess.run(["explorer", str(path)], check=False)
    elif system == "Darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def _merge_shared_labels(rows):
    """Append alias section numbers to primary e.g. ENGR478-01 → ENGR478-01/03."""
    merged = []
    for row in rows:
        sec     = row[0]
        aliases = SHARED_SECTIONS.get(sec, [])
        if aliases:
            suffix = "".join(f"/{a.split('-')[1]}" for a in aliases)
            row    = [sec + suffix] + row[1:]
        merged.append(row)
    return merged


# ---------------------------------------------------------------------------
# Gantt chart
# ---------------------------------------------------------------------------

def assign_lanes(bars):
    """Assign non-overlapping horizontal lanes to a list of time bars.
    Returns the same list, each bar augmented with lane_idx and total_lanes.
    Safe to call with an empty list.
    """
    if not bars:
        return bars
    bars.sort(key=lambda b: (b["s"], b["e"]))
    lane_of = [-1] * len(bars)
    for i in range(len(bars)):
        used = set()
        for j in range(i):
            if bars[j]["s"] < bars[i]["e"] and bars[j]["e"] > bars[i]["s"]:
                used.add(lane_of[j])
        lane = 0
        while lane in used:
            lane += 1
        lane_of[i] = lane
    total = max(lane_of) + 1
    for i, bar in enumerate(bars):
        bar["lane_idx"] = lane_of[i]
        bar["total_lanes"] = total
    return bars


def day_pos(d):
    return d * (DAY_SPAN + DAY_GAP)


def bar_coords(bar):
    bw = DAY_SPAN / bar["total_lanes"]
    x0 = day_pos(bar["d"]) + bar["lane_idx"] * bw + BAR_PAD
    x1 = day_pos(bar["d"]) + (bar["lane_idx"] + 1) * bw - BAR_PAD
    return x0, x1


def build_gantt_html(rows):
    if not rows:
        return "<html><body><p>No data to show.</p></body></html>"

    # assign a color to each professor
    all_profs = sorted({r[4] for r in rows if len(r) >= 5})
    prof_color = {p: PALETTE[i % len(PALETTE)] for i, p in enumerate(all_profs)}

    # parse each schedule row into a bar dict, grouped by day
    bars_by_day = [[], [], [], [], []]
    for row in rows:
        if len(row) < 5:
            continue
        section  = row[0]
        ctype    = row[1]
        days     = row[2]
        time_str = row[3]
        prof     = row[4]
        room     = row[5] if len(row) >= 6 else ""
        try:
            ss, es = time_str.split("-")
            s = time_to_minutes(ss)
            e = time_to_minutes(es)
        except Exception:
            continue
        for ch in days:
            if ch in DAY_ORDER:
                d = DAY_ORDER.index(ch)
                bars_by_day[d].append(dict(section=section, ctype=ctype, prof=prof,
                                           room=room, ss=ss, es=es, s=s, e=e))

    # assign non-overlapping lanes per day, then flatten into one list
    all_bars = []
    for d in range(5):
        for bar in assign_lanes(bars_by_day[d]):
            bar["d"] = d
            all_bars.append(bar)

    fig = go.Figure()

    # derive X-axis range (Time) from actual data; fall back to 8am-10pm if empty
    if all_bars:
        x_min = min(b["s"] for b in all_bars)
        x_max = max(b["e"] for b in all_bars)
        x_min = max(0,    (x_min // 60) * 60)         # snap to prev hour
        x_max = min(1440, (x_max // 60 + 1) * 60)     # snap to next hour
    else:
        x_min, x_max = 480, 1320

    # draw alternating row backgrounds and divider lines (horizontal)
    shapes = []
    bg_colors = ["#f5f5f5", "#ffffff", "#f5f5f5", "#ffffff", "#f5f5f5"]
    for d in range(5):
        shapes.append(dict(type="rect", x0=x_min, x1=x_max,
                           y0=day_pos(d), y1=day_pos(d) + DAY_SPAN, fillcolor=bg_colors[d],
                           opacity=1.0, line=dict(width=0), layer="below"))
    for d in range(1, 5):
        shapes.append(dict(type="line", x0=x_min, x1=x_max,
                           y0=day_pos(d) - DAY_GAP / 2, y1=day_pos(d) - DAY_GAP / 2,
                           line=dict(color="#bbbbbb", width=2), layer="below"))

    # draw one Scatter trace per professor so legend click shows/hides their bars
    bars_by_prof = defaultdict(list)
    for bar in all_bars:
        bars_by_prof[bar["prof"]].append(bar)

    for prof in all_profs:
        px = []
        py = []
        hover = []
        for bar in bars_by_prof[prof]:
            y0, y1 = bar_coords(bar)
            x0 = bar["s"]
            x1 = bar["e"]
            px += [x0, x1, x1, x0, x0, None]
            py += [y0, y0, y1, y1, y0, None]
            tip = (f"<b>{bar['section']}</b><br>"
                   f"Type: {bar['ctype']}<br>"
                   f"Prof: {prof}<br>"
                   f"Room: {bar.get('room') or 'Need Room'}<br>"
                   f"Time: {bar['ss']} \u2013 {bar['es']}<br>"
                   f"Day: {DAY_LABELS[bar['d']]}")
            hover += [tip, tip, tip, tip, tip, None]

        # customdata: section ID per point so plotly_click can read it directly
        cdata = []
        for bar in bars_by_prof[prof]:
            sec_id = bar["section"]
            cdata += [sec_id, sec_id, sec_id, sec_id, sec_id, None]

        fig.add_trace(go.Scatter(
            x=px, y=py,
            mode="lines",
            fill="toself",
            fillcolor=prof_color[prof],
            line=dict(color="white", width=1.5),
            name=prof,
            legendgroup=prof,
            opacity=1.0,
            hovertemplate="%{text}<extra></extra>",
            text=hover,
            customdata=cdata,
        ))

   # add section name labels inside each bar
    annotations = []
    for bar in all_bars:
        y0, y1 = bar_coords(bar)
        # short label: just "100-01" instead of "ENGR100-01"
        label = bar["section"].replace("ENGR", "").strip()

        annotations.append(dict(
            x=(bar["s"] + bar["e"]) / 2,
            y=(y0 + y1) / 2,
            text=label,
            name=bar["prof"],
            showarrow=False,
            textangle=0,
            xanchor="center",
            yanchor="middle",
            font=dict(size=9, color="black", family="monospace"),
            xref="x",
            yref="y",
        ))

    # configure axes and layout
    # 30-min ticks: full hours horizontal, half-hours slanted
    x_vals = list(range(x_min, x_max + 1, 30))
    x_text = [f"{v // 60}:00" if v % 60 == 0 else f"{v // 60}:30" for v in x_vals]
    y_ticks = [day_pos(d) + DAY_SPAN / 2 for d in range(5)]

    fig.update_layout(
        shapes=shapes,
        annotations=annotations,

        # X-Axis is now TIME
        xaxis=dict(
            tickmode="array", tickvals=x_vals, ticktext=x_text,
            side="top", range=[x_min, x_max],
            gridcolor="#e0e0e0", zeroline=False, fixedrange=False,
            tickangle=-30,
            tickfont=dict(size=11),
        ),

        # Y-Axis is now DAYS
        yaxis=dict(
            tickmode="array", tickvals=y_ticks, ticktext=DAY_LABELS,
            autorange="reversed", range=[-0.2, day_pos(4) + DAY_SPAN + 0.2],
            showgrid=False, zeroline=False, fixedrange=False,
            tickfont=dict(size=13, color="#222222"),
        ),

        dragmode="zoom",
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=80, r=20, t=130, b=20),
        hovermode="closest",
        legend=dict(
            title="Click to show/hide",
            orientation="v", x=1.01, y=1,
            font=dict(size=11),
            itemclick="toggle",
            itemdoubleclick="toggleothers",
        ),
        height=750,
        title=dict(
            text="Weekly Class Schedule<br><span style='font-size:11px;'>(click legend to filter \u00b7 drag to zoom \u00b7 double-click to reset)</span>",
            x=0.5,
            font=dict(size=14),
        ),
    )

    raw_html = fig.to_html(include_plotlyjs="cdn", full_html=True)

    # inject Hide All / Show All buttons into the page
    inject = """
<style>
  #btn-bar { display: flex; gap: 8px; padding: 8px 12px 0 12px; }
  #btn-bar button {
    padding: 5px 18px; font-size: 12px; border: 1.5px solid #ccc;
    border-radius: 5px; background: #f7f7f7; cursor: pointer; font-family: sans-serif;
  }
  #btn-bar button:hover { background: #e0e0e0; }
  #btn-bar button.active { background: #4e79a7; color: white; border-color: #4e79a7; }
</style>
<div id="btn-bar">
  <button id="btn-hide">Hide All</button>
  <button id="btn-show">Show All</button>
</div>
<script>
function waitForPlot(cb) {
    var n = 0;
    var t = setInterval(function() {
        var el = document.querySelector('.plotly-graph-div');
        if (el && el.data && el.data.length > 0) { clearInterval(t); cb(el); }
        if (++n > 150) clearInterval(t);
    }, 100);
}
waitForPlot(function(plot) {
    var idx = plot.data.map(function(_, i) { return i; });
    var origAnnotations = (plot.layout.annotations || []).map(function(a) { return Object.assign({}, a); });

    // Build map: professor name -> list of annotation indices
    var profAnnMap = {};
    origAnnotations.forEach(function(ann, ai) {
        if (ann.name) {
            if (!profAnnMap[ann.name]) profAnnMap[ann.name] = [];
            profAnnMap[ann.name].push(ai);
        }
    });

    function syncAnnotations() {
        var updated = origAnnotations.map(function(a) { return Object.assign({}, a, { visible: false }); });
        plot.data.forEach(function(trace) {
            if (trace.visible === true || trace.visible === undefined) {
                (profAnnMap[trace.name] || []).forEach(function(ai) {
                    updated[ai] = Object.assign({}, origAnnotations[ai], { visible: true });
                });
            }
        });
        Plotly.relayout(plot, { annotations: updated });
    }

    plot.on('plotly_legendclick', function() { setTimeout(syncAnnotations, 50); return true; });
    plot.on('plotly_legenddoubleclick', function() { setTimeout(syncAnnotations, 50); return true; });

    document.getElementById('btn-hide').onclick = function() {
        Plotly.restyle(plot, { visible: 'legendonly' }, idx).then(syncAnnotations);
        this.classList.add('active');
        document.getElementById('btn-show').classList.remove('active');
    };
    document.getElementById('btn-show').onclick = function() {
        Plotly.restyle(plot, { visible: true }, idx).then(syncAnnotations);
        this.classList.add('active');
        document.getElementById('btn-hide').classList.remove('active');
    };
});
</script>
<script>
waitForPlot(function(plot) {
    plot.on("plotly_click", function(data) {
        if (!data || !data.points || !data.points.length) return;
        var sec = data.points[0].customdata;
        if (sec && sec !== null) {
            document.title = "SELECT:" + sec;
        }
    });
});
</script>"""

    if "<body>" in raw_html:
        raw_html = raw_html.replace("<body>", "<body>" + inject, 1)
    else:
        raw_html = inject + raw_html

    return raw_html


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class SchedulerWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ENGR Class Scheduler")
        self.resize(1400, 860)
        if getattr(sys, "frozen", False):
            # Inside a .app: Contents/MacOS/ENGR_Scheduler → 4 parents up = dist/
            self.project_dir = Path(sys.executable).parent.parent.parent.parent
        else:
            self.project_dir = Path.cwd()
        self.db_path = self.project_dir / "db_classes.db"

        # On first launch of the frozen .app, copy the bundled DB to the
        # writable project folder so the user can actually read/write it.
        if not self.db_path.exists() and getattr(sys, "frozen", False):
            bundled = Path(sys._MEIPASS) / "db_classes.db"
            if bundled.exists():
                shutil.copy(bundled, self.db_path)

        self.all_rows = []
        self._undo_stack = []
        self._section_slot_map = {}
        self._build_ui()
        self._refresh_paths()
        self._ensure_default_snapshot()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        # Create a layout for the root widget
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Create a horizontal splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Build the panels and add them to the splitter
        left_panel = self._build_left_panel()
        right_panel = self._build_right_panel()

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)

        # Maintain your original 3:5 size ratio
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)

        # Add the splitter to the main layout
        main_layout.addWidget(splitter)

    def _build_left_panel(self):
        panel  = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        # project folder picker
        box  = QGroupBox("Project")
        form = QFormLayout(box)
        self.project_dir_edit = QLineEdit(str(self.project_dir))
        self.project_dir_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._pick_project_dir)
        folder_row = QWidget()
        fl = QHBoxLayout(folder_row)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.project_dir_edit)
        fl.addWidget(browse_btn)
        form.addRow("Folder", folder_row)
        layout.addWidget(box)

        # action buttons
        btn_row = QHBoxLayout()
        run_btn = QPushButton("▶  Run Solver")
        run_btn.setFixedHeight(34)
        run_btn.setStyleSheet("font-size:13px;font-weight:bold;"
                              "background:#4e79a7;color:white;border-radius:5px;")
        run_btn.clicked.connect(self._run_solver)
        save_btn = QPushButton("💾  Save DB")
        save_btn.setFixedHeight(34)
        save_btn.clicked.connect(self._save_db)
        self.restore_btn = QPushButton("↩  Restore")
        self.restore_btn.setFixedHeight(34)
        self.restore_btn.setToolTip("Undo last Save DB (up to 10 levels)")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self._restore_db)
        default_btn = QPushButton("🔄  Default")
        default_btn.setFixedHeight(34)
        default_btn.setToolTip("Reset DB to original default data")
        default_btn.clicked.connect(self._default_db)
        open_btn = QPushButton("📂  Open Folder")
        open_btn.setFixedHeight(34)
        open_btn.clicked.connect(lambda: _open_folder(self.project_dir))
        for w in [run_btn, save_btn, self.restore_btn, default_btn, open_btn]:
            btn_row.addWidget(w)
        layout.addLayout(btn_row)

        # DB editor tabs
        self.db_tabs = QTabWidget()
        self._sections_tab = SectionsTab(self.db_path)
        self._faculty_tab  = FacultyTab(self.db_path)
        self._slots_tab    = TimeSlotsTab(self.db_path)
        self.db_tabs.addTab(self._sections_tab, "Sections")
        self.db_tabs.addTab(self._faculty_tab,  "Faculty")
        self.db_tabs.addTab(self._slots_tab,    "Time Slots")

        # --- NEW: Create a vertical splitter ---
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(self.db_tabs)

        # dynamic status log
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-size:11px;")
        # (setFixedHeight is removed so it can flex dynamically)

        left_splitter.addWidget(self.log_box)

        # Set default proportions: tabs get most of the space, log gets the bottom section
        left_splitter.setStretchFactor(0, 5)
        left_splitter.setStretchFactor(1, 1)

        layout.addWidget(left_splitter)

        return panel

    def _build_right_panel(self):
        panel  = QWidget()
        layout = QVBoxLayout(panel)

        # Summary + Freeze/Unfreeze buttons
        action_row = QHBoxLayout()
        self.summary_label = QLabel("Run the solver to see the schedule.")
        self.summary_label.setStyleSheet("font-size:12px;color:#666;")
        action_row.addWidget(self.summary_label, stretch=1)
        self.freeze_btn = QPushButton("📌  Freeze")
        self.freeze_btn.setFixedHeight(28)
        self.freeze_btn.setToolTip("Select a row → pin section to its slot (freeze_slot_id).")
        self.freeze_btn.setEnabled(False)
        self.freeze_btn.clicked.connect(self._freeze_selected)
        action_row.addWidget(self.freeze_btn)
        self.unfreeze_btn = QPushButton("🔓  Unfreeze")
        self.unfreeze_btn.setFixedHeight(28)
        self.unfreeze_btn.setToolTip("Remove the frozen slot pin from the selected section.")
        self.unfreeze_btn.setEnabled(False)
        self.unfreeze_btn.clicked.connect(self._unfreeze_selected)
        action_row.addWidget(self.unfreeze_btn)
        layout.addLayout(action_row)

        # filter bar
        filter_row = QHBoxLayout()
        self.filter_section = QLineEdit()
        self.filter_section.setPlaceholderText("Filter section…")
        self.filter_section.textChanged.connect(self._apply_filters)
        self.filter_type = QLineEdit()
        self.filter_type.setPlaceholderText("Filter type…")
        self.filter_type.textChanged.connect(self._apply_filters)
        self.filter_prof = QLineEdit()
        self.filter_prof.setPlaceholderText("Filter professor…")
        self.filter_prof.textChanged.connect(self._apply_filters)
        self.filter_day = QLineEdit()
        self.filter_day.setPlaceholderText("Filter day…")
        self.filter_day.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self.filter_section)
        filter_row.addWidget(self.filter_type)
        filter_row.addWidget(self.filter_prof)
        filter_row.addWidget(self.filter_day)
        layout.addLayout(filter_row)

        # results: table view + Gantt chart
        self.result_tabs = QTabWidget()
        self.result_table = QTableWidget()
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setSortingEnabled(True)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.itemSelectionChanged.connect(self._on_table_selection)
        self.result_tabs.addTab(self.result_table, "Table View")
        self.web_view = QWebEngineView()
        self.web_view.titleChanged.connect(self._on_gantt_click)
        self.result_tabs.addTab(self.web_view, "Gantt Chart")
        self.result_tabs.currentChanged.connect(self._on_result_tab_changed)
        layout.addWidget(self.result_tabs)

        return panel

    def _refresh_paths(self):
        self.db_path = self.project_dir / "db_classes.db"
        self.project_dir_edit.setText(str(self.project_dir))
        if self.db_path.exists():
            for tab in [self._sections_tab, self._faculty_tab, self._slots_tab]:
                tab.db_path = self.db_path
                tab.load()
        else:
            self._log("Database not found.")

    def _pick_project_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose project folder", str(self.project_dir))
        if folder:
            self.project_dir = Path(folder)
            self._undo_stack.clear()
            self.restore_btn.setEnabled(False)
            self._refresh_paths()
            self._ensure_default_snapshot()

    # ── Backup / Restore / Default ──────────────────────────────────────────

    def _backup_dir(self):
        d = self.project_dir / ".db_backups"
        d.mkdir(exist_ok=True)
        return d

    def _make_backup(self):
        if not self.db_path.exists():
            return
        dest = self._backup_dir() / f"db_backup_{len(self._undo_stack)}.db"
        shutil.copy(self.db_path, dest)
        self._undo_stack.append(dest)
        while len(self._undo_stack) > MAX_UNDO:
            old = self._undo_stack.pop(0)
            try: old.unlink()
            except Exception: pass
        self.restore_btn.setEnabled(True)

    def _ensure_default_snapshot(self):
        default = self.project_dir / "db_classes_default.db"
        if not default.exists() and self.db_path.exists():
            shutil.copy(self.db_path, default)
            self._log("💾  Default snapshot saved (db_classes_default.db).")

    def _restore_db(self):
        if not self._undo_stack:
            self._log("Nothing to restore.")
            return
        if (QMessageBox.question(self, "Restore", "Undo the last Save DB and reload?")
                != QMessageBox.StandardButton.Yes):
            return
        backup = self._undo_stack.pop()
        shutil.copy(backup, self.db_path)
        try: backup.unlink()
        except Exception: pass
        if not self._undo_stack:
            self.restore_btn.setEnabled(False)
        self._refresh_paths()
        self._log("↩  Restored to previous state.")

    def _default_db(self):
        default = self.project_dir / "db_classes_default.db"
        if not default.exists():
            self._log("⚠️  No default snapshot found. Save the DB once first.")
            return
        if (QMessageBox.question(self, "Reset to Default",
                "Overwrite current DB with the original default data?\n"
                "All unsaved changes will be lost.\n\n"
                "You can ↩ Restore afterwards if needed.")
                != QMessageBox.StandardButton.Yes):
            return
        self._make_backup()
        shutil.copy(default, self.db_path)
        self._refresh_paths()
        self._log("🔄  DB reset to original default. (↩ Restore available)")

    # ── Save ────────────────────────────────────────────────────────────────

    def _save_db(self):
        if not self.db_path.exists():
            self._log("Database not found.")
            return
        self._make_backup()
        try:
            self._sections_tab.save()
            self._faculty_tab.save()
            self._slots_tab.save()
            self._log("💾  Database saved.  (↩ Restore available)")
        except Exception as e:
            self._log(f"Save error: {e}")

    # ── Freeze / Unfreeze ────────────────────────────────────────────────────

    def _on_table_selection(self):
        has = bool(self.result_table.selectedItems())
        self.freeze_btn.setEnabled(has)
        self.unfreeze_btn.setEnabled(has)

    def _on_result_tab_changed(self, index):
        pass  # freeze/unfreeze managed by table selection and gantt click only

    def _on_gantt_click(self, title):
        """Bar clicked in Gantt — select matching row in table and enable freeze."""
        if not title.startswith("SELECT:"):
            return
        sec_id = title[7:].strip()
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item and item.text().split("/")[0].strip() == sec_id:
                self.result_table.selectRow(row)
                self.freeze_btn.setEnabled(True)
                self.unfreeze_btn.setEnabled(True)
                self._log(f"\u2714  Selected {sec_id} from Gantt \u2014 press Freeze or Unfreeze.")
                return

    def _primary_id(self):
        r = self.result_table.currentRow()
        if r < 0: return None
        item = self.result_table.item(r, 0)
        if not item: return None
        raw = item.text().split("/")[0]
        if not raw.startswith("ENGR") and "-" in raw:
            raw = "ENGR" + raw
        return raw

    def _slot_label(self, slot_id):
        try:
            conn = sqlite3.connect(str(self.db_path))
            cur  = conn.cursor()
            cur.execute("SELECT day_pattern, start_time, end_time FROM time_slots WHERE slot_id=?", (slot_id,))
            row = cur.fetchone()
            conn.close()
            return f"{row[0]} {row[1]}–{row[2]}" if row else str(slot_id)
        except Exception:
            return str(slot_id)

    def _freeze_selected(self):
        pid = self._primary_id()
        if not pid: return
        slot_id = self._section_slot_map.get(pid)
        if slot_id is None:
            self._log(f"No slot found for {pid} — run the solver first.")
            return
        self._make_backup()
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("UPDATE db_classes SET frozen_slot_id=? WHERE section_id=?", (slot_id, pid))
            conn.commit(); conn.close()
        except Exception as e:
            self._log(f"Freeze error: {e}"); return
        self._sections_tab.load()
        self._log(f"📌  {pid} frozen → slot {slot_id} ({self._slot_label(slot_id)})")

    def _unfreeze_selected(self):
        pid = self._primary_id()
        if not pid: return
        self._make_backup()
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("UPDATE db_classes SET frozen_slot_id=NULL WHERE section_id=?", (pid,))
            conn.commit(); conn.close()
        except Exception as e:
            self._log(f"Unfreeze error: {e}"); return
        self._sections_tab.load()
        self._log(f"🔓  {pid} unfrozen.")

    def _run_solver(self):
        self.log_box.clear()
        if not self.db_path.exists():
            self._log("Database not found.")
            return
        # Save any pending edits first so the solver always sees current data.
        try:
            self._sections_tab.save()
            self._faculty_tab.save()
            self._slots_tab.save()
        except Exception as e:
            self._log(f"Save error before solving: {e}")
            return
        self._log("Saved edits. Running solver…")
        try:
            sched = Scheduler(str(self.db_path))
            sched.load()
        except Exception as e:
            self._log(f"Load error: {e}"); return

        if hasattr(sched, "skipped_no_faculty") and sched.skipped_no_faculty:
            from solver import NO_FACULTY_COURSES
            self._log("─" * 60)
            self._log("⚠️  UNSCHEDULED — No qualified faculty in current roster:")
            by_course: dict = {}
            for sid in sorted(sched.skipped_no_faculty):
                cid = sid.rsplit("-", 1)[0]
                by_course.setdefault(cid, []).append(sid)
            for cid, sids in sorted(by_course.items()):
                name = NO_FACULTY_COURSES.get(cid, cid)
                self._log(f"   {cid} — {name}")
                self._log(f"      Sections: {', '.join(sids)}")
            self._log(f"   Total skipped: {len(sched.skipped_no_faculty)} section(s) across {len(by_course)} course(s)")
            self._log("─" * 60)

        try:
            result = sched.solve()
        except Exception as e:
            self._log(f"Solver error: {e}"); return
        if not result:
            self._log("Solver finished — no feasible schedule found."); return

        self._section_slot_map = {}
        try:
            conn = sqlite3.connect(str(self.db_path))
            cur  = conn.cursor()
            cur.execute("SELECT slot_id, day_pattern, start_time, end_time FROM time_slots")
            slot_lookup = {(r[1], r[2], r[3]): r[0] for r in cur.fetchall()}
            conn.close()
            for row in result:
                sec_id, days, time_str = row[0], row[2], row[3]
                try:
                    start, end = time_str.split("-")
                    sid = slot_lookup.get((days, start, end))
                    if sid is not None:
                        self._section_slot_map[sec_id] = sid
                except Exception: pass
        except Exception: pass

        db_info = {}
        try:
            conn = sqlite3.connect(str(self.db_path))
            cur  = conn.cursor()
            cur.execute("SELECT section_id, slot_type, capacity, major, lab_room, frozen_slot_id FROM db_classes")
            db_info = {r[0]: r[1:] for r in cur.fetchall()}
            conn.close()
        except Exception: pass

        rows_full = []
        for row in result:
            if len(row) == 6:
                sec, typ, days, time, prof, room = row
            else:
                sec, typ, days, time, prof = row; room = ""
            info = db_info.get(sec, ("", "", "", "", ""))
            stype = info[0] or ""; cap = str(info[1]) if info[1] else ""
            major = info[2] or ""
            if not room or room == "Need Room": room = info[3] or room
            frozen = str(info[4]) if info[4] else ""
            rows_full.append([sec, typ, stype, days, time, prof, cap, major, room, frozen])

        raw = sorted(rows_full, key=lambda r: (r[0], r[4]))
        self.all_rows = _merge_shared_labels(raw)
        self._apply_filters()

        scheduled    = len(self.all_rows)
        no_fac_count = len(sched.skipped_no_faculty) if hasattr(sched, "skipped_no_faculty") else 0
        violations   = getattr(sched, "major_overlap_violations", 0)
        self._log("─" * 60)
        self._log(f"✅  SCHEDULE COMPLETE — {scheduled} sections assigned.")
        if no_fac_count:
            self._log(f"⚠️  {no_fac_count} section(s) skipped — no faculty (see above).")
        if violations:
            self._log(f"⚠️  {violations} same-major time conflict(s) unavoidable.")
        else:
            self._log("✅  All same-major sections at non-overlapping times.")
        self._log("─" * 60)

    def _apply_filters(self):
        if not self.all_rows:
            return
        f_sec  = self.filter_section.text().strip().lower()
        f_type = self.filter_type.text().strip().lower()
        f_day  = self.filter_day.text().strip().lower()
        f_prof = self.filter_prof.text().strip().lower()

        filtered = []
        for row in self.all_rows:
            r = (row + [""] * 10)[:10]
            if f_sec  and f_sec  not in r[0].lower(): continue
            if f_type and f_type not in r[1].lower(): continue
            if f_day  and f_day  not in r[3].lower(): continue
            if f_prof and f_prof not in r[5].lower(): continue
            filtered.append(r)

        headers = ["Section", "Type", "Slot Type", "Days", "Time",
                   "Professor", "Cap", "Major", "Room", "Frozen Slot"]
        self.result_table.setSortingEnabled(False)
        self.result_table.clear()
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)
        self.result_table.setRowCount(len(filtered))
        for r_idx, row in enumerate(filtered):
            for c_idx, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                if c_idx == 6:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.result_table.setItem(r_idx, c_idx, item)
        self.result_table.setSortingEnabled(True)
        self.summary_label.setText(
            f"Showing {len(filtered)} of {len(self.all_rows)} sections"
            "  — select a row → 📌 Freeze to pin it")
        gantt_rows = [[r[0], r[1], r[3], r[4], r[5]] for r in filtered]
        self.web_view.setHtml(build_gantt_html(gantt_rows))

    def _log(self, message):
        self.log_box.appendPlainText(message)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    window = SchedulerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()