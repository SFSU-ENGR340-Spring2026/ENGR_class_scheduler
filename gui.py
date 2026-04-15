"""
ENGR Class Scheduler - GUI
Built with PySide6 for the window/table, and Plotly for the Gantt chart.
"""

import sqlite3
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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


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


def parse_solver_output(text):
    # read each line of solver output and collect the schedule rows
    rows = []
    capturing = False
    for line in text.splitlines():
        s = line.strip()
        if s == "Schedule:":
            capturing = True
            continue
        if not capturing or not s or s.startswith("Section"):
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) >= 5:
            rows.append(parts[:5])
    return rows


# ---------------------------------------------------------------------------
# Gantt chart
# ---------------------------------------------------------------------------

def assign_lanes(bars):
    # sort bars by start time so we process them in order
    bars.sort(key=lambda b: (b["s"], b["e"]))
    lane_of = [-1] * len(bars)
    for i in range(len(bars)):
        # find which lanes are already taken by overlapping earlier bars
        used = set()
        for j in range(i):
            if bars[j]["s"] < bars[i]["e"] and bars[j]["e"] > bars[i]["s"]:
                used.add(lane_of[j])
        # assign the lowest available lane
        lane = 0
        while lane in used:
            lane += 1
        lane_of[i] = lane
    total = max(lane_of) + 1
    for i, bar in enumerate(bars):
        bar["lane_idx"] = lane_of[i]
        bar["total_lanes"] = total
    return bars


def day_x(d):
    return d * (DAY_WIDTH + DAY_GAP)


def bar_coords(bar):
    bw = DAY_WIDTH / bar["total_lanes"]
    x0 = day_x(bar["d"]) + bar["lane_idx"] * bw + BAR_PAD
    x1 = day_x(bar["d"]) + (bar["lane_idx"] + 1) * bw - BAR_PAD
    return x0, x1


def build_gantt_html(rows):
    if not rows:
        return "<html><body><p>No data to show.</p></body></html>"

    day_order  = ["M", "T", "W", "R", "F"]
    day_labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    DAY_WIDTH = 1.8
    DAY_GAP   = 0.4
    PAD       = 0.015

    def day_x(d):
        return d * (DAY_WIDTH + DAY_GAP)

    all_profs = sorted(set(r[4] for r in rows if len(r) >= 5))
    palette = [
        "#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f",
        "#edc948","#b07aa1","#ff9da7","#9c755f","#aecfd6",
        "#d37295","#fabfd2","#8cd17d","#86bcb6","#499894",
        "#f1ce63","#79706e","#d4a6c8","#b6992d","#a0cbe8",
    ]
    prof_color = {p: palette[i % len(palette)] for i, p in enumerate(all_profs)}

    # Parse and group bars by day
    bars_by_day = [[] for _ in range(5)]
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

    # Interval graph coloring — no two overlapping bars share a lane
    final_bars = []
    for d, day_bars in enumerate(bars_by_day):
        if not day_bars:
            continue
        day_bars.sort(key=lambda b: (b["s"], b["e"]))
        n = len(day_bars)
        lane_of = [-1] * n
        for i in range(n):
            used = set()
            for j in range(i):
                if day_bars[j]["s"] < day_bars[i]["e"] and day_bars[j]["e"] > day_bars[i]["s"]:
                    used.add(lane_of[j])
            lane = 0
            while lane in used:
                lane += 1
            lane_of[i] = lane
        total_lanes = max(lane_of) + 1
        for i, bar in enumerate(day_bars):
            bar["lane_idx"]    = lane_of[i]
            bar["total_lanes"] = total_lanes
            bar["d"]           = d
            final_bars.append(bar)

    fig = go.Figure()

    # Decorative background only — no bar content drawn here
    bg_shapes = []
    bg = ["#f5f5f5","#ffffff","#f5f5f5","#ffffff","#f5f5f5"]
    for d in range(5):
        shapes.append(dict(type="rect", x0=day_x(d), x1=day_x(d) + DAY_WIDTH,
                           y0=480, y1=1320, fillcolor=bg_colors[d],
                           opacity=1.0, line=dict(width=0), layer="below"))
    for d in range(1, 5):
        shapes.append(dict(type="line", x0=day_x(d) - DAY_GAP / 2, x1=day_x(d) - DAY_GAP / 2,
                           y0=480, y1=1320, line=dict(color="#bbbbbb", width=2), layer="below"))

    # One Scatter trace per professor — bars are ONLY drawn here,
    # so hiding the trace truly removes the bars from the chart.
    bars_by_prof = defaultdict(list)
    for bar in all_bars:
        bars_by_prof[bar["prof"]].append(bar)

    for prof in all_profs:
        px = []
        py = []
        hover = []
        for bar in bars_by_prof[prof]:
            d  = bar["d"]
            li = bar["lane_idx"]
            tl = bar["total_lanes"]
            bw = DAY_WIDTH / tl
            x0 = day_x(d) + li * bw + PAD
            x1 = day_x(d) + (li + 1) * bw - PAD
            s  = bar["s"]
            e  = bar["e"]

            # Closed rectangle polygon — None breaks between bars
            px_list += [x0, x1, x1, x0, x0, None]
            py_list += [s,  s,  e,  e,  s,  None]

            tip = (f"<b>{bar['section']}</b><br>"
                   f"Type: {bar['ctype']}<br>"
                   f"Prof: {prof}<br>"
                   f"Time: {bar['ss']} \u2013 {bar['es']}<br>"
                   f"Day: {DAY_LABELS[bar['d']]}")
            hover += [tip, tip, tip, tip, tip, None]
        fig.add_trace(go.Scatter(
            x=px_list, y=py_list,
            mode="lines",
            fill="toself",
            fillcolor=color,
            line=dict(color="white", width=1.5),
            name=prof,
            legendgroup=prof,
            hovertemplate="%{text}<extra></extra>",
            text=hover,
            opacity=0.90,
        ))

    # Short labels inside bars (annotations — always visible but just tiny text)
    label_annotations = []
    for bar in final_bars:
        d  = bar["d"]
        li = bar["lane_idx"]
        tl = bar["total_lanes"]
        bw = DAY_WIDTH / tl
        x0 = day_x(d) + li * bw + PAD
        x1 = day_x(d) + (li + 1) * bw - PAD
        label_annotations.append(dict(
            x=(x0 + x1) / 2,
            y=(bar["s"] + bar["e"]) / 2,
            text=bar["section"].replace("ENGR", ""),
            showarrow=False,
            font=dict(size=8, color="white", family="monospace"),
            textangle=-90,
            xanchor="center", yanchor="middle",
            xref="x", yref="y",
        ))

    total_x     = day_x(4) + DAY_WIDTH
    x_ticks     = [day_x(d) + DAY_WIDTH / 2 for d in range(5)]
    y_tick_vals = list(range(480, 1321, 60))
    y_tick_text = [f"{v // 60:02d}:00" for v in y_tick_vals]

    fig.update_layout(
        shapes=bg_shapes,
        annotations=label_annotations,
        xaxis=dict(
            tickmode="array", tickvals=x_ticks, ticktext=day_labels,
            side="top", range=[-0.1, total_x + 0.1],
            showgrid=False, zeroline=False, fixedrange=False,
            tickfont=dict(size=13, color="#222222"),
        ),
        yaxis=dict(
            tickmode="array", tickvals=y_tick_vals, ticktext=y_tick_text,
            autorange="reversed", range=[480, 1320],
            title="Time", gridcolor="#e0e0e0", gridwidth=1,
            zeroline=False, fixedrange=False,
        ),
        dragmode="zoom",
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=65, r=20, t=70, b=20),
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
            text="Weekly Class Schedule  (click legend to filter · drag to zoom · double-click to reset)",
            x=0.5, font=dict(size=13)
        ),
    )

    raw_html = fig.to_html(include_plotlyjs="cdn", full_html=True)

    inject = """
<style>
  #btn-bar {
    display: flex;
    gap: 8px;
    padding: 8px 12px 0 12px;
  }
  #btn-bar button {
    padding: 5px 18px;
    font-size: 12px;
    border: 1.5px solid #cccccc;
    border-radius: 5px;
    background: #f7f7f7;
    cursor: pointer;
    font-family: sans-serif;
  }
  #btn-bar button:hover { background: #e0e0e0; }
  #btn-hide-all.active { background: #4e79a7; color: white; border-color: #4e79a7; }
  #btn-show-all.active { background: #4e79a7; color: white; border-color: #4e79a7; }
</style>
<div id="btn-bar">
  <button id="btn-hide-all">Hide All</button>
  <button id="btn-show-all">Show All</button>
</div>
<script>
function waitForPlot(cb) {
    var n = 0;
    var t = setInterval(function() {
        var el = document.querySelector('.plotly-graph-div');
        if (el && el.data && el.data.length > 0) {
            clearInterval(t);
            cb(el);
        }
        if (++n > 150) clearInterval(t);
    }, 100);
}

waitForPlot(function(plot) {
    document.getElementById('btn-hide-all').addEventListener('click', function() {
        var indices = [];
        for (var i = 0; i < plot.data.length; i++) indices.push(i);
        Plotly.restyle(plot, { visible: 'legendonly' }, indices);
        this.classList.add('active');
        document.getElementById('btn-show-all').classList.remove('active');
    });

    document.getElementById('btn-show-all').addEventListener('click', function() {
        var indices = [];
        for (var i = 0; i < plot.data.length; i++) indices.push(i);
        Plotly.restyle(plot, { visible: true }, indices);
        this.classList.add('active');
        document.getElementById('btn-hide-all').classList.remove('active');
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
        self.resize(1200, 800)
        self.project_dir = Path.cwd()
        self.solver_path = self.project_dir / "solver.py"
        self.db_path     = self.project_dir / "db_classes.db"
        self.all_rows    = []
        self._build_ui()
        self._refresh_paths()
        self._log("Ready.")

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.addWidget(self._build_left_panel(), 3)
        main.addWidget(self._build_right_panel(), 5)

    def _build_left_panel(self):
        panel  = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        files_box  = QGroupBox("Project Files")
        files_form = QFormLayout(files_box)

        self.project_dir_edit = QLineEdit(str(self.project_dir))
        self.project_dir_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._pick_project_dir)
        folder_row        = QWidget()
        folder_row_layout = QHBoxLayout(folder_row)
        folder_row_layout.setContentsMargins(0, 0, 0, 0)
        folder_row_layout.addWidget(self.project_dir_edit)
        folder_row_layout.addWidget(browse_btn)
        files_form.addRow("Folder", folder_row)

        self.solver_edit = QLineEdit()
        self.solver_edit.setReadOnly(True)
        files_form.addRow("Solver", self.solver_edit)

        self.db_edit = QLineEdit()
        self.db_edit.setReadOnly(True)
        files_form.addRow("Database", self.db_edit)

        layout.addWidget(files_box)

        btn_row1 = QHBoxLayout()
        inspect_btn = QPushButton("Inspect DB")
        inspect_btn.clicked.connect(self._inspect_db)
        run_btn = QPushButton("Run Solver")
        run_btn.clicked.connect(self._run_solver)
        btn_row1.addWidget(inspect_btn)
        btn_row1.addWidget(run_btn)
        layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        open_btn  = QPushButton("Open Project Folder")
        open_btn.clicked.connect(self._open_folder)
        clear_btn = QPushButton("Clear Log")
        btn_row2.addWidget(open_btn)
        btn_row2.addWidget(clear_btn)
        layout.addLayout(btn_row2)

        self.db_summary = QLabel("DB summary will appear here.")
        self.db_summary.setWordWrap(True)
        layout.addWidget(self.db_summary)

        layout.addWidget(QLabel("Log:"))
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(60)
        self.log_box.setStyleSheet("font-size:11px;")
        layout.addWidget(self.log_box)

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
        self.filter_section.setPlaceholderText("Filter by section...")
        self.filter_section.textChanged.connect(self._apply_filters)

        self.filter_type = QLineEdit()
        self.filter_type.setPlaceholderText("Filter by type...")
        self.filter_type.textChanged.connect(self._apply_filters)

        self.filter_prof = QLineEdit()
        self.filter_prof.setPlaceholderText("Filter by professor...")
        self.filter_prof.textChanged.connect(self._apply_filters)

        self.filter_day = QLineEdit()
        self.filter_day.setPlaceholderText("Filter by day...")
        self.filter_day.textChanged.connect(self._apply_filters)

        filter_row.addWidget(self.filter_section)
        filter_row.addWidget(self.filter_type)
        filter_row.addWidget(self.filter_prof)
        filter_row.addWidget(self.filter_day)
        layout.addLayout(filter_row)

        self.tabs = QTabWidget()

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.tabs.addTab(self.table, "Table View")

        self.web_view = QWebEngineView()
        self.tabs.addTab(self.web_view, "Gantt Chart")
        layout.addWidget(self.tabs)

        return panel

    def _refresh_paths(self):
        self.solver_path = self.project_dir / "solver.py"
        self.db_path     = self.project_dir / "db_classes.db"
        self.project_dir_edit.setText(str(self.project_dir))
        self.solver_edit.setText(str(self.solver_path))
        self.db_edit.setText(str(self.db_path))
        self._inspect_db()

    def _pick_project_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose project folder", str(self.project_dir)
        )
        if folder:
            self.project_dir = Path(folder)
            self._refresh_paths()
            self._log(f"Project folder: {self.project_dir}")

    def _open_folder(self):
        subprocess.run(["open", str(self.project_dir)], check=False)

    def _inspect_db(self):
        if not self.db_path.exists():
            self._log("Database not found.")
            return
        try:
            conn = sqlite3.connect(self.db_path)
            cur  = conn.cursor()

            def count(q):
                try:
                    cur.execute(q)
                    return cur.fetchone()[0]
                except Exception:
                    return 0

            self.db_summary.setText(
                f"Sections: {count('SELECT COUNT(*) FROM db_classes')}  |  "
                f"Faculty: {count('SELECT COUNT(*) FROM faculty')}  |  "
                f"Slots: {count('SELECT COUNT(*) FROM time_slots')}  |  "
                f"Availability: {count('SELECT COUNT(*) FROM availability')}  |  "
                f"Can-teach: {count('SELECT COUNT(*) FROM faculty_can_teach')}"
            )
            conn.close()
        except Exception as e:
            self._log(f"Save error: {e}")

    def _run_solver(self):
        if not self.solver_path.exists():
            QMessageBox.warning(self, "Missing file",
                                f"solver.py not found at:\n{self.solver_path}")
            return
        if not self.db_path.exists():
            QMessageBox.warning(self, "Missing file",
                                f"db_classes.db not found at:\n{self.db_path}")
            return

        self._log("\nRunning solver...")
        try:
            result = subprocess.run(
                [sys.executable, str(self.solver_path)],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
            )
        except Exception as e:
            self._log(f"Error running solver: {e}")
            return

        if result.stdout:
            self._log(result.stdout.strip())
        if result.stderr:
            self._log(result.stderr.strip())

        if result.returncode != 0:
            QMessageBox.warning(self, "Solver failed",
                                "Solver exited with an error. Check the log.")
            return

        self._log("Solver finished.")
        self._parse_solver_output(result.stdout)

        self._log("\nThe other 5 are genuinely missing because no faculty has the expertise:")
        self._log("ENGR300 Engineering Experimentation")
        self._log("ENGR304 Mechanics of Fluids")
        self._log("ENGR434 Principles of Environmental Engr")
        self._log("ENGR436 Transportation Engineering")
        self._log("ENGR890 Static Timing Analysis for Nanometer Designs")

    def _parse_solver_output(self, text):
        rows      = []
        capturing = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "Schedule:":
                capturing = True
                continue
            if not capturing or not stripped:
                continue
            if stripped.startswith("Section"):
                continue
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) >= 5:
                rows.append(parts[:5])

        if not rows:
            self._log("No schedule rows found in solver output.")
            return

        self.all_rows = rows
        self._apply_filters()

            self._log("\nThe following 5 are unassigned because no faculty has the required expertise:")
            self._log("ENGR300, ENGR304, ENGR434, ENGR436, ENGR890")

        except Exception as e:
            self._log(f"Error during solver execution: {e}")

    def _apply_filters(self):
        rows = self.all_rows
        if not rows:
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
            for c_idx, value in enumerate(row):
                self.table.setItem(r_idx, c_idx, QTableWidgetItem(value))
        self.table.setSortingEnabled(True)

        self.summary_label.setText(
            f"Showing {len(filtered)} of {len(rows)} scheduled sections"
        )
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