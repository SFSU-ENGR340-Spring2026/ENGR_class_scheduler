import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
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
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class SchedulerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Small ENGR Scheduler")
        self.resize(1180, 760)

        self.project_dir = Path.cwd()
        self.solver_path = self.project_dir / "solver.py"
        self.db_path = self.project_dir / "db_classes.db"

        self.all_headers = []
        self.all_rows = []

        self._build_ui()
        self.refresh_paths()
        self.log("Ready.")

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        top = QWidget()
        top_layout = QHBoxLayout(top)
        splitter.addWidget(top)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)

        left_panel = self._build_controls_panel()
        right_panel = self._build_results_panel()
        top_layout.addWidget(left_panel, 2)
        top_layout.addWidget(right_panel, 5)

        splitter.addWidget(self.log_box)
        splitter.setSizes([620, 140])

    def _build_controls_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        files_group = QGroupBox("Project Files")
        files_form = QFormLayout(files_group)

        self.project_dir_edit = QLineEdit(str(self.project_dir))
        self.project_dir_edit.setReadOnly(True)
        self.project_dir_edit.setMinimumWidth(260)
        browse_project_btn = QPushButton("Browse...")
        browse_project_btn.clicked.connect(self.pick_project_dir)
        project_row = QWidget()
        project_row_layout = QHBoxLayout(project_row)
        project_row_layout.setContentsMargins(0, 0, 0, 0)
        project_row_layout.addWidget(self.project_dir_edit)
        project_row_layout.addWidget(browse_project_btn)
        files_form.addRow("Project Folder", project_row)

        self.solver_edit = QLineEdit()
        self.solver_edit.setReadOnly(True)
        self.solver_edit.setMinimumWidth(260)
        files_form.addRow("Solver Script", self.solver_edit)

        self.db_edit = QLineEdit()
        self.db_edit.setReadOnly(True)
        self.db_edit.setMinimumWidth(260)
        files_form.addRow("Database", self.db_edit)

        layout.addWidget(files_group)

        button_row = QHBoxLayout()
        self.inspect_btn = QPushButton("Inspect DB")
        self.inspect_btn.clicked.connect(self.inspect_database)
        self.run_btn = QPushButton("Run Solver")
        self.run_btn.clicked.connect(self.run_solver)
        self.refresh_btn = QPushButton("Refresh Preview")
        self.refresh_btn.clicked.connect(self.load_schedule_preview)
        button_row.addWidget(self.inspect_btn)
        button_row.addWidget(self.run_btn)
        button_row.addWidget(self.refresh_btn)
        layout.addLayout(button_row)

        open_row = QHBoxLayout()
        self.open_folder_btn = QPushButton("Open Project Folder")
        self.open_folder_btn.clicked.connect(self.open_project_folder)
        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.clicked.connect(self.log_box.clear)
        open_row.addWidget(self.open_folder_btn)
        open_row.addWidget(clear_log_btn)
        layout.addLayout(open_row)

        self.db_summary_label = QLabel("Database summary will appear here.")
        self.db_summary_label.setWordWrap(True)
        layout.addWidget(self.db_summary_label)

        layout.addStretch()
        return panel

    def _build_results_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title = QLabel("Schedule Preview")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        self.summary_label = QLabel("No schedule loaded.")
        layout.addWidget(self.summary_label)

        filter_row = QHBoxLayout()
        self.section_filter_edit = QLineEdit()
        self.section_filter_edit.setPlaceholderText("Filter by section...")
        self.section_filter_edit.textChanged.connect(self.apply_filters)

        self.type_filter_edit = QLineEdit()
        self.type_filter_edit.setPlaceholderText("Filter by type...")
        self.type_filter_edit.textChanged.connect(self.apply_filters)

        self.prof_filter_edit = QLineEdit()
        self.prof_filter_edit.setPlaceholderText("Filter by professor...")
        self.prof_filter_edit.textChanged.connect(self.apply_filters)

        self.day_filter_edit = QLineEdit()
        self.day_filter_edit.setPlaceholderText("Filter by day...")
        self.day_filter_edit.textChanged.connect(self.apply_filters)

        filter_row.addWidget(self.section_filter_edit)
        filter_row.addWidget(self.type_filter_edit)
        filter_row.addWidget(self.prof_filter_edit)
        filter_row.addWidget(self.day_filter_edit)
        layout.addLayout(filter_row)

        # Create Tab Widget for Table vs Gantt views
        self.tabs = QTabWidget()

        # Tab 1: Table
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabs.addTab(self.table, "Table View")

        # Tab 2: Gantt Chart (By Professor)
        self.web_view_prof = QWebEngineView()
        self.tabs.addTab(self.web_view_prof, "Gantt (By Prof)")

        # Tab 3: Gantt Chart (By Class)
        self.web_view_class = QWebEngineView()
        self.tabs.addTab(self.web_view_class, "Gantt (By Class)")

        layout.addWidget(self.tabs)

        return panel

    def refresh_paths(self):
        self.project_dir_edit.setText(str(self.project_dir))
        self.solver_path = self.project_dir / "solver.py"
        self.db_path = self.project_dir / "db_classes.db"

        self.solver_edit.setText(str(self.solver_path))
        self.db_edit.setText(str(self.db_path))

        self.inspect_database()
        self.load_schedule_preview()

    def pick_project_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose project folder", str(self.project_dir))
        if folder:
            self.project_dir = Path(folder)
            self.refresh_paths()
            self.log(f"Project folder set to: {self.project_dir}")

    def log(self, message):
        self.log_box.appendPlainText(message)

    def run_command(self, command, working_dir):
        self.log(f"\n$ {' '.join(command)}")
        try:
            completed = subprocess.run(
                command,
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            self.log(f"Failed to run command: {exc}")
            QMessageBox.critical(self, "Command Error", str(exc))
            return None

        if completed.stdout:
            self.log(completed.stdout.strip())
        if completed.stderr:
            self.log(completed.stderr.strip())

        if completed.returncode != 0:
            QMessageBox.warning(
                self,
                "Command Failed",
                f"Command exited with code {completed.returncode}. See log for details.",
            )
        return completed

    def inspect_database(self):
        if not self.db_path.exists():
            self.db_summary_label.setText("Database not found.")
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()

            section_count = self._safe_count(cur, "SELECT COUNT(*) FROM db_classes")
            faculty_count = self._safe_count(cur, "SELECT COUNT(*) FROM faculty")
            slot_count = self._safe_count(cur, "SELECT COUNT(*) FROM time_slots")
            availability_count = self._safe_count(cur, "SELECT COUNT(*) FROM availability")
            teach_count = self._safe_count(cur, "SELECT COUNT(*) FROM faculty_can_teach")

            conn.close()
        except Exception as exc:
            self.db_summary_label.setText(f"Could not inspect DB: {exc}")
            return

        self.db_summary_label.setText(
            f"Sections: {section_count} | Faculty: {faculty_count} | Slots: {slot_count} | "
            f"Availability rows: {availability_count} | Can-teach rows: {teach_count}"
        )

    def _safe_count(self, cur, query):
        try:
            cur.execute(query)
            row = cur.fetchone()
            return row[0] if row else 0
        except sqlite3.Error:
            return 0

    def run_solver(self):
        if not self.solver_path.exists():
            QMessageBox.warning(self, "Missing File", f"Could not find {self.solver_path.name}")
            return
        if not self.db_path.exists():
            QMessageBox.warning(self, "Missing File", f"Could not find database: {self.db_path}")
            return

        completed = self.run_command([sys.executable, str(self.solver_path)], self.project_dir)
        if completed is None:
            return

        if completed.returncode == 0:
            self.log("Solver run finished.")
            self.parse_schedule_output(completed.stdout)

    def parse_schedule_output(self, stdout_text):
        lines = stdout_text.splitlines()
        rows = []
        capture = False

        for line in lines:
            stripped = line.strip()
            if stripped == "Schedule:":
                capture = True
                continue
            if not capture or not stripped:
                continue
            if stripped.startswith("Section"):
                continue

            parts = [p.strip() for p in line.split("\t")]
            if len(parts) >= 5:
                rows.append(parts[:5])

        if not rows:
            self.log("No printable schedule table found in solver output.")
            return

        self.all_headers = ["Section", "Type", "Days", "Time", "Professor"]
        self.all_rows = rows
        self.apply_filters()

    def load_schedule_preview(self):
        if not self.db_path.exists():
            self.all_headers = []
            self.all_rows = []
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            empty_msg = "<html><body><h3>No schedule loaded.</h3></body></html>"
            self.web_view_prof.setHtml(empty_msg)
            self.web_view_class.setHtml(empty_msg)
            self.summary_label.setText("No preview available.")
            return

        self.all_headers = ["Section", "Type", "Days", "Time", "Professor"]
        self.all_rows = []
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(len(self.all_headers))
        self.table.setHorizontalHeaderLabels(self.all_headers)
        
        default_msg = "<html><body><h3>Run the solver to view Gantt chart.</h3></body></html>"
        self.web_view_prof.setHtml(default_msg)
        self.web_view_class.setHtml(default_msg)
        self.summary_label.setText("Run the solver to load the current schedule preview.")

    def open_project_folder(self):
        try:
            subprocess.run(["open", str(self.project_dir)], check=False)
        except Exception as exc:
            QMessageBox.warning(self, "Open Folder", f"Could not open folder:\n{exc}")

    def apply_filters(self):
        headers = self.all_headers
        rows = self.all_rows
        if not headers:
            return

        section_text = self.section_filter_edit.text().strip().lower()
        type_text = self.type_filter_edit.text().strip().lower()
        prof_text = self.prof_filter_edit.text().strip().lower()
        day_text = self.day_filter_edit.text().strip().lower()

        filtered_rows = []
        for row in rows:
            row_extended = row + [""] * max(0, len(headers) - len(row))
            section_value = row_extended[0].lower()
            type_value = row_extended[1].lower()
            day_value = row_extended[2].lower()
            prof_value = row_extended[4].lower()

            if section_text and section_text not in section_value:
                continue
            if type_text and type_text not in type_value:
                continue
            if prof_text and prof_text not in prof_value:
                continue
            if day_text and day_text not in day_value:
                continue
            filtered_rows.append(row_extended)

        # Update Table
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(filtered_rows))

        for r, row in enumerate(filtered_rows):
            type_value = row[1].strip().lower() if len(row) > 1 else ""
            for c, value in enumerate(row[:len(headers)]):
                item = QTableWidgetItem(value)
                if type_value == "lab":
                    item.setBackground(QColor(235, 245, 255))
                elif type_value == "activity":
                    item.setBackground(QColor(240, 255, 240))
                self.table.setItem(r, c, item)

        self.table.setSortingEnabled(True)
        self.summary_label.setText(f"Showing {len(filtered_rows)} of {len(rows)} scheduled rows")
        
        # Update Gantt Charts
        self.update_gantt_chart(filtered_rows)

    def update_gantt_chart(self, rows):
        empty_html = "<html><body><h3>No data matches your filters.</h3></body></html>"
        if not rows:
            self.web_view_prof.setHtml(empty_html)
            self.web_view_class.setHtml(empty_html)
            return

        df_data = []
        day_map = {
            'M': ('Monday', '2024-01-01'), 
            'T': ('Tuesday', '2024-01-02'), 
            'W': ('Wednesday', '2024-01-03'), 
            'R': ('Thursday', '2024-01-04'), 
            'F': ('Friday', '2024-01-05')
        }

        for row in rows:
            if len(row) < 5:
                continue
            
            section, type_, days, time_str, prof = row
            
            try:
                start_str, end_str = time_str.split('-')
            except ValueError:
                continue

            for day_char in days:
                if day_char in day_map:
                    day_name, date_str = day_map[day_char]
                    start_dt = f"{date_str} {start_str}:00"
                    end_dt = f"{date_str} {end_str}:00"

                    df_data.append({
                        "Section": section,
                        "Professor": prof,
                        "Type": type_.capitalize(),
                        "Day": day_name,
                        "Start": start_dt,
                        "Finish": end_dt
                    })

        if not df_data:
            error_html = "<html><body><h3>Could not parse times for Gantt chart.</h3></body></html>"
            self.web_view_prof.setHtml(error_html)
            self.web_view_class.setHtml(error_html)
            return

        df = pd.DataFrame(df_data)
        
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        df['Day'] = pd.Categorical(df['Day'], categories=day_order, ordered=True)
        df = df.sort_values(['Day', 'Start'])

        # --- Chart 1: Colored By Professor ---
        fig_prof = px.timeline(
            df,
            x_start="Start",
            x_end="Finish",
            y="Day",
            color="Professor",
            hover_name="Section",
            text="Section",
            title="Weekly Class Schedule (Grouped by Professor)"
        )
        
        fig_prof.update_yaxes(autorange="reversed")
        fig_prof.update_layout(
            xaxis=dict(tickformat="%H:%M", title="Time"),
            yaxis=dict(title=""),
            hovermode="closest",
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        self.web_view_prof.setHtml(fig_prof.to_html(include_plotlyjs='cdn'))

        # --- Chart 2: Colored By Class (Section) ---
        fig_class = px.timeline(
            df,
            x_start="Start",
            x_end="Finish",
            y="Day",
            color="Section",
            hover_name="Professor",
            text="Section",
            title="Weekly Class Schedule (Grouped by Class)"
        )
        
        fig_class.update_yaxes(autorange="reversed")
        fig_class.update_layout(
            xaxis=dict(tickformat="%H:%M", title="Time"),
            yaxis=dict(title=""),
            hovermode="closest",
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        self.web_view_class.setHtml(fig_class.to_html(include_plotlyjs='cdn'))


def main():
    app = QApplication(sys.argv)
    window = SchedulerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()