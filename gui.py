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
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tabs import SectionsTab, FacultyTab, TimeSlotsTab
from solver import Scheduler

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
DAY_SPAN  = 1.8
DAY_GAP    = 0.4
BAR_PAD    = 0.015

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def time_to_minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def open_folder(path):
    system = platform.system()
    if system == "Windows":
        subprocess.run(["explorer", str(path)], check=False)
    elif system == "Darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


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
        section, ctype, days, time_str, prof = row
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
                                           ss=ss, es=es, s=s, e=e))

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
        x_min = max(0,    (x_min // 60) * 60 - 30)   # floor to prev hour - 30 min padding
        x_max = min(1440, (x_max // 60) * 60 + 90)   # ceil  to next hour + 30 min padding
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
                   f"Time: {bar['ss']} \u2013 {bar['es']}<br>"
                   f"Day: {DAY_LABELS[bar['d']]}")
            hover += [tip, tip, tip, tip, tip, None]
        
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
        ))

   # add section name labels inside each horizontal bar
    annotations = []
    for bar in all_bars:
        y0, y1 = bar_coords(bar)
        
        # Ensure there is a space between ENGR and the number
        # (e.g., "ENGR101-01" becomes "ENGR 101-01")
        section_name = bar["section"].replace("ENGR", "ENGR ").replace("  ", " ")
        
        # Stack the course prefix/number and the section number
        # This turns "ENGR 101-01" into "ENGR 101" on top and "-01" on the bottom
        if "-" in section_name:
            parts = section_name.split("-")
            label_text = f"{parts[0]}<br>-{parts[1]}"
        else:
            label_text = section_name

        annotations.append(dict(
            x=(bar["s"] + bar["e"]) / 2,
            y=(y0 + y1) / 2,
            text=label_text,
            showarrow=False,
            textangle=0,
            xanchor="center",
            yanchor="middle",
            font=dict(size=10, color="black", family="monospace"),
            xref="x",
            yref="y",
        ))

    # configure axes and layout
    x_vals = list(range(x_min, x_max + 1, 30)) # Changed step to 30
    x_text = [f"{v // 60:02d}:{v % 60:02d}" for v in x_vals] # Added minutes calculation
    y_ticks = [day_pos(d) + DAY_SPAN / 2 for d in range(5)]

    fig.update_layout(
        shapes=shapes,
        annotations=annotations,
        
        # X-Axis is now TIME
        xaxis=dict(
            tickmode="array", tickvals=x_vals, ticktext=x_text,
            side="top", range=[x_min, x_max],
            gridcolor="#e0e0e0", zeroline=False, fixedrange=False,
        ),
        
        # Y-Axis is now DAYS
        yaxis=dict(
            tickmode="array", tickvals=y_ticks, ticktext=DAY_LABELS,
            autorange="reversed", range=[-0.1, day_pos(4) + DAY_SPAN + 0.1],
            showgrid=False, zeroline=False, fixedrange=False,
            tickfont=dict(size=13, color="#222222"),
        ),
        
        dragmode="zoom",
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=80, r=20, t=110, b=20),
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
    document.getElementById('btn-hide').onclick = function() {
        Plotly.restyle(plot, { visible: 'legendonly' }, idx);
        this.classList.add('active');
        document.getElementById('btn-show').classList.remove('active');
    };
    document.getElementById('btn-show').onclick = function() {
        Plotly.restyle(plot, { visible: true }, idx);
        this.classList.add('active');
        document.getElementById('btn-hide').classList.remove('active');
    };
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
        self._build_ui()
        self._refresh_paths()

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
        run_btn.clicked.connect(self._run_solver)
        save_btn = QPushButton("💾  Save DB")
        save_btn.clicked.connect(self._save_db)
        open_btn = QPushButton("Open Folder")
        open_btn.clicked.connect(lambda: open_folder(self.project_dir))
        btn_row.addWidget(run_btn)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(open_btn)
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

        title = QLabel("Schedule Preview")
        title.setStyleSheet("font-size:15px; font-weight:bold;")
        layout.addWidget(title)

        self.summary_label = QLabel("No schedule loaded yet.")
        layout.addWidget(self.summary_label)

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
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.result_tabs.addTab(self.result_table, "Table View")
        self.web_view = QWebEngineView()
        self.result_tabs.addTab(self.web_view, "Gantt Chart")
        layout.addWidget(self.result_tabs)

        return panel

    def _refresh_paths(self):
        self.db_path = self.project_dir / "db_classes.db"
        self.project_dir_edit.setText(str(self.project_dir))
        if self.db_path.exists():
            self._sections_tab.db_path = self.db_path
            self._sections_tab.load()
            self._faculty_tab.db_path = self.db_path
            self._faculty_tab.load()
            self._slots_tab.db_path = self.db_path
            self._slots_tab.load()
        else:
            self._log("Database not found.")

    def _pick_project_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose project folder", str(self.project_dir))
        if folder:
            self.project_dir = Path(folder)
            self._refresh_paths()

    def _save_db(self):
        if not self.db_path.exists():
            self._log("Database not found.")
            return
        try:
            self._sections_tab.save()
            self._faculty_tab.save()
            self._slots_tab.save()
            self._log("Database saved.")
        except Exception as e:
            self._log(f"Save error: {e}")

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
            result = sched.solve()
        except Exception as e:
            self._log(f"Solver error: {e}")
            return
        if not result:
            self._log("Solver finished but no feasible schedule found.")
            return
        rows = [[sec, typ, days, time, prof] for sec, typ, days, time, prof in result]
        rows.sort(key=lambda r: (r[0], r[3]))
        self.all_rows = rows
        self._apply_filters()
        self._log(f"Solved: {len(rows)} sections scheduled.")

    def _apply_filters(self):
        if not self.all_rows:
            return
        f_sec  = self.filter_section.text().strip().lower()
        f_type = self.filter_type.text().strip().lower()
        f_day  = self.filter_day.text().strip().lower()
        f_prof = self.filter_prof.text().strip().lower()

        filtered = []
        for row in self.all_rows:
            r = (row + [""] * 5)[:5]
            if f_sec  and f_sec  not in r[0].lower(): continue
            if f_type and f_type not in r[1].lower(): continue
            if f_day  and f_day  not in r[2].lower(): continue
            if f_prof and f_prof not in r[4].lower(): continue
            filtered.append(r)

        headers = ["Section", "Type", "Days", "Time", "Professor"]
        self.result_table.setSortingEnabled(False)
        self.result_table.clear()
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)
        self.result_table.setRowCount(len(filtered))
        for r_idx, row in enumerate(filtered):
            for c_idx, val in enumerate(row):
                self.result_table.setItem(r_idx, c_idx, QTableWidgetItem(val))
        self.result_table.setSortingEnabled(True)
        self.summary_label.setText(f"Showing {len(filtered)} of {len(self.all_rows)} scheduled sections")
        self.web_view.setHtml(build_gantt_html(filtered))

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
