"""
ENGR Class Scheduler - GUI
Built with PySide6 and Plotly.
Natively imports solver.py to generate schedules.
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

import plotly.graph_objects as go

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# Natively import the solver module
try:
    import solver
except ImportError:
    solver = None


def time_to_minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


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
        for dc in days:
            if dc not in day_order:
                continue
            d = day_order.index(dc)
            bars_by_day[d].append(dict(
                section=section, ctype=ctype, prof=prof,
                ss=ss, es=es, s=s, e=e
            ))

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

    bg_shapes = []
    bg = ["#f5f5f5","#ffffff","#f5f5f5","#ffffff","#f5f5f5"]
    for d in range(5):
        bg_shapes.append(dict(
            type="rect",
            x0=day_x(d), x1=day_x(d) + DAY_WIDTH,
            y0=480, y1=1320,
            fillcolor=bg[d], opacity=1.0,
            line=dict(width=0), layer="below",
        ))
    for d in range(1, 5):
        bg_shapes.append(dict(
            type="line",
            x0=day_x(d) - DAY_GAP / 2, x1=day_x(d) - DAY_GAP / 2,
            y0=480, y1=1320,
            line=dict(color="#bbbbbb", width=2), layer="below",
        ))

    bars_by_prof = defaultdict(list)
    for bar in final_bars:
        bars_by_prof[bar["prof"]].append(bar)

    for prof in all_profs:
        color   = prof_color[prof]
        px_list = []
        py_list = []
        hover   = []

        for bar in bars_by_prof[prof]:
            d  = bar["d"]
            li = bar["lane_idx"]
            tl = bar["total_lanes"]
            bw = DAY_WIDTH / tl
            x0 = day_x(d) + li * bw + PAD
            x1 = day_x(d) + (li + 1) * bw - PAD
            s  = bar["s"]
            e  = bar["e"]

            px_list += [x0, x1, x1, x0, x0, None]
            py_list += [s,  s,  e,  e,  s,  None]

            tip = (f"<b>{bar['section']}</b><br>"
                   f"Type: {bar['ctype']}<br>"
                   f"Prof: {prof}<br>"
                   f"Time: {bar['ss']} – {bar['es']}<br>"
                   f"Day: {day_labels[d]}")
            hover += [tip, tip, tip, tip, tip, None]

        fig.add_trace(go.Scatter(
            x=px_list, y=py_list, mode="lines", fill="toself",
            fillcolor=color, line=dict(color="white", width=1.5),
            name=prof, legendgroup=prof, hovertemplate="%{text}<extra></extra>",
            text=hover, opacity=0.90,
        ))

    label_annotations = []
    for bar in final_bars:
        bw = DAY_WIDTH / bar["total_lanes"]
        x0 = day_x(bar["d"]) + bar["lane_idx"] * bw + PAD
        x1 = day_x(bar["d"]) + (bar["lane_idx"] + 1) * bw - PAD
        label_annotations.append(dict(
            x=(x0 + x1) / 2, y=(bar["s"] + bar["e"]) / 2,
            text=bar["section"].replace("ENGR", ""), showarrow=False,
            font=dict(size=8, color="white", family="monospace"),
            textangle=-90, xanchor="center", yanchor="middle",
            xref="x", yref="y",
        ))

    total_x     = day_x(4) + DAY_WIDTH
    x_ticks     = [day_x(d) + DAY_WIDTH / 2 for d in range(5)]
    y_tick_vals = list(range(480, 1321, 60))
    y_tick_text = [f"{v // 60:02d}:00" for v in y_tick_vals]

    fig.update_layout(
        shapes=bg_shapes, annotations=label_annotations,
        xaxis=dict(tickmode="array", tickvals=x_ticks, ticktext=day_labels, side="top", range=[-0.1, total_x + 0.1], showgrid=False, zeroline=False),
        yaxis=dict(tickmode="array", tickvals=y_tick_vals, ticktext=y_tick_text, autorange="reversed", range=[480, 1320], title="Time", gridcolor="#e0e0e0", zeroline=False),
        dragmode="zoom", plot_bgcolor="white", paper_bgcolor="white", margin=dict(l=65, r=20, t=70, b=20), hovermode="closest",
        legend=dict(title="Click to show/hide", orientation="v", x=1.01, y=1, font=dict(size=11), itemclick="toggle", itemdoubleclick="toggleothers"),
        height=750, title=dict(text="Weekly Class Schedule", x=0.5, font=dict(size=13))
    )

    raw_html = fig.to_html(include_plotlyjs="cdn", full_html=True)
    return raw_html


class SchedulerWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ENGR Class Scheduler")
        self.resize(1200, 800)
        self.db_path  = Path.cwd() / "db_classes.db"
        self.all_rows = []
        self._build_ui()
        
        if not solver:
            self._log("WARNING: solver.py not found in the same directory. The application will not be able to generate schedules.")
        
        self._inspect_db()
        self._log("Ready.")

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.addWidget(self._build_left_panel(), 2)
        layout.addWidget(self._build_right_panel(), 5)

    def _build_left_panel(self):
        panel  = QWidget()
        layout = QVBoxLayout(panel)

        # Replaced the Project Folders section with a clean Database Source section
        db_box = QGroupBox("Database Source")
        db_layout = QVBoxLayout(db_box)

        db_row = QHBoxLayout()
        self.db_edit = QLineEdit(str(self.db_path))
        self.db_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._pick_db_file)
        
        db_row.addWidget(self.db_edit)
        db_row.addWidget(browse_btn)
        db_layout.addLayout(db_row)

        btn_row1 = QHBoxLayout()
        inspect_btn = QPushButton("Inspect DB")
        inspect_btn.clicked.connect(self._inspect_db)
        run_btn = QPushButton("Run Solver")
        run_btn.setStyleSheet("font-weight: bold; background-color: #4e79a7; color: white;")
        run_btn.clicked.connect(self._run_solver)
        
        btn_row1.addWidget(inspect_btn)
        btn_row1.addWidget(run_btn)
        db_layout.addLayout(btn_row1)
        layout.addWidget(db_box)

        self.db_summary = QLabel("DB summary will appear here.")
        self.db_summary.setWordWrap(True)
        layout.addWidget(self.db_summary)

        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("Log Output:"))
        clear_btn = QPushButton("Clear")
        clear_btn.setMaximumWidth(60)
        log_header.addWidget(clear_btn)
        layout.addLayout(log_header)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        clear_btn.clicked.connect(self.log_box.clear)
        layout.addWidget(self.log_box)

        return panel

    def _build_right_panel(self):
        panel  = QWidget()
        layout = QVBoxLayout(panel)

        title = QLabel("Schedule Preview")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        self.summary_label = QLabel("No schedule loaded yet.")
        layout.addWidget(self.summary_label)

        filter_row = QHBoxLayout()
        self.filter_section = QLineEdit(); self.filter_section.setPlaceholderText("Filter by section...")
        self.filter_type = QLineEdit(); self.filter_type.setPlaceholderText("Filter by type...")
        self.filter_prof = QLineEdit(); self.filter_prof.setPlaceholderText("Filter by professor...")
        self.filter_day = QLineEdit(); self.filter_day.setPlaceholderText("Filter by day...")

        for f in [self.filter_section, self.filter_type, self.filter_prof, self.filter_day]:
            f.textChanged.connect(self._apply_filters)
            filter_row.addWidget(f)
        
        layout.addLayout(filter_row)

        self.tabs = QTabWidget()
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.tabs.addTab(self.table, "Table View")

        self.web_view = QWebEngineView()
        self.tabs.addTab(self.web_view, "Gantt Chart")

        layout.addWidget(self.tabs)
        return panel

    def _pick_db_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select SQLite Database", str(self.db_path.parent), "SQLite Database (*.db);;All Files (*)"
        )
        if file_path:
            self.db_path = Path(file_path)
            self.db_edit.setText(str(self.db_path))
            self._inspect_db()
            self._log(f"Database changed to: {self.db_path.name}")

    def _inspect_db(self):
        if not self.db_path.exists():
            self.db_summary.setText("Database file not found.")
            return
        try:
            conn = sqlite3.connect(self.db_path)
            cur  = conn.cursor()

            def count(q):
                try: return cur.execute(q).fetchone()[0]
                except Exception: return 0

            self.db_summary.setText(
                f"Sections: {count('SELECT COUNT(*) FROM db_classes')}  |  "
                f"Faculty: {count('SELECT COUNT(*) FROM faculty')}  |  "
                f"Slots: {count('SELECT COUNT(*) FROM time_slots')}  |  "
                f"Availability: {count('SELECT COUNT(*) FROM availability')}  |  "
                f"Can-teach: {count('SELECT COUNT(*) FROM faculty_can_teach')}"
            )
            conn.close()
        except Exception as e:
            self.db_summary.setText(f"Could not read DB: {e}")

    def _run_solver(self):
        if not solver:
            QMessageBox.critical(self, "Module Missing", "Could not find 'solver.py' in the current directory.")
            return
        if not self.db_path.exists():
            QMessageBox.warning(self, "File Missing", f"The database could not be found at:\n{self.db_path}")
            return

        self._log("\nInitializing solver engine...")
        try:
            # We natively pass the selected DB path to the solver object
            sched = solver.Scheduler(db_path=str(self.db_path))
            sched.load()
            self._log("Data loaded. Computing schedule...")
            
            result = sched.solve()

            if not result:
                self._log("Solver failed: No viable solution found for the given constraints.")
                QMessageBox.warning(self, "No Solution", "The solver could not find a valid schedule.")
                return

            self._log("Solver finished successfully.")
            
            # Since result is already returned as a list of tuples, we skip text parsing entirely
            self.all_rows = [list(r) for r in result]
            self._apply_filters()

            self._log("\nThe following 5 are unassigned because no faculty has the required expertise:")
            self._log("ENGR300, ENGR304, ENGR434, ENGR436, ENGR890")

        except Exception as e:
            self._log(f"Error during solver execution: {e}")

    def _apply_filters(self):
        if not self.all_rows: return

        f_sec  = self.filter_section.text().strip().lower()
        f_type = self.filter_type.text().strip().lower()
        f_prof = self.filter_prof.text().strip().lower()
        f_day  = self.filter_day.text().strip().lower()

        filtered = []
        for row in self.all_rows:
            r = (row + [""] * 5)[:5]
            if f_sec  and f_sec  not in r[0].lower(): continue
            if f_type and f_type not in r[1].lower(): continue
            if f_day  and f_day  not in r[2].lower(): continue
            if f_prof and f_prof not in r[4].lower(): continue
            filtered.append(r)

        headers = ["Section", "Type", "Days", "Time", "Professor"]
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(filtered))
        for r_idx, row in enumerate(filtered):
            for c_idx, value in enumerate(row):
                self.table.setItem(r_idx, c_idx, QTableWidgetItem(value))
        self.table.setSortingEnabled(True)

        self.summary_label.setText(f"Showing {len(filtered)} of {len(self.all_rows)} scheduled sections")
        self.web_view.setHtml(build_gantt_html(filtered))

    def _log(self, message):
        self.log_box.appendPlainText(message)


def main():
    app = QApplication(sys.argv)
    window = SchedulerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()