# ENGR Class Scheduler

Automated course scheduler for SFSU Engineering Department (Civil, ME, EE/CE, CompE).  
Built with PySide6, Google OR-Tools CP-SAT, and Plotly.

**Team:** Joe Le (PM), Francisco, Nikita, Alan  
**Course:** ENGR 340 — Spring 2026

---

## What It Does

- Assigns 132 course sections to time slots and faculty using a constraint satisfaction solver
- Respects faculty availability, room assignments, WTU loads, and same-major non-overlap constraints
- Provides a GUI to edit sections, faculty, and time slots directly
- Displays results in a filterable Table View and interactive Gantt chart
- Supports freeze/unfreeze to pin sections to specific time slots

---

## Requirements

- Python 3.10+
- macOS or Windows

---

## Run from Source

```bash
# 1. Clone the repo
git clone https://github.com/SFSU-ENGR340-Spring2026/ENGR_class_scheduler
cd ENGR_class_scheduler

# 2. Install dependencies
pip install PySide6 ortools plotly

# 3. Run
python3 gui.py
```

---

## Build macOS App

```bash
pip install pyinstaller
pyinstaller ENGR_Scheduler.spec
```

Output: `dist/ENGR_Scheduler.app`

> If macOS blocks it on first launch: right-click → **Open** → **Open**

---

## Build Windows Executable

Run on a Windows machine:

```bat
pip install pyinstaller
pyinstaller ENGR_Scheduler.spec
```

Output: `dist\ENGR_Scheduler\ENGR_Scheduler.exe`  
Zip the entire `dist\ENGR_Scheduler\` folder to distribute.

---

## Project Structure

| File | Description |
|------|-------------|
| `gui.py` | Main window, Gantt chart, solver integration |
| `tabs.py` | DB editor tabs (Sections, Faculty, Time Slots) |
| `solver.py` | CP-SAT constraint solver |
| `db.py` | SQLite read/write helpers |
| `db_classes.db` | Live database |
| `db_classes_default.db` | Default snapshot for reset |
| `ENGR_Scheduler.spec` | PyInstaller build config |

---

## How to Use

1. Launch the app and set the project folder with **Browse**
2. Edit sections, faculty, or time slots in the left panel tabs
3. Click **Run Solver** — results appear in Table View and Gantt Chart
4. Use **Freeze** to pin a section to its current slot (select a row first)
5. Click **Save DB** to persist changes
6. Use **Default** to reset to the original dataset

---

## Known Limitations

- Freeze/unfreeze from Gantt chart requires clicking a bar to select the section first
- The solver does not enforce WTU caps per faculty member
- Building for Windows requires running PyInstaller on a Windows machine
