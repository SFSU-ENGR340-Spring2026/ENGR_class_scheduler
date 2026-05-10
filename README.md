# ENGR Class Scheduler

A desktop GUI app for editing ENGR course scheduling data and generating a weekly schedule with an OR-Tools constraint solver.

## Included files

- `gui.py` - main PySide6 GUI, Gantt chart, solver controls, freeze/unfreeze tools.
- `tabs.py` - editable Sections, Faculty, and Time Slots database tabs.
- `db.py` - SQLite read/write helper functions and lightweight database migrations.
- `solver.py` - OR-Tools CP-SAT scheduler.
- `db_classes.db` - working plain SQLite database.
- `db_classes_default.db` - default/reset plain SQLite database snapshot.
- `schema.sql` - simple table-only database schema.
- `health_check.py` - syntax and database consistency checker.
- `ENGR_Scheduler.spec` - PyInstaller build file.
- `requirements.txt` - Python dependencies.
- `run_scheduler.py` - simple launcher.
- `run_mac_linux.sh` / `run_windows.bat` - install dependencies and run from source.
- `build_mac_linux.sh` / `build_windows.bat` - build a distributable app/executable with PyInstaller.

## Requirements

- Python 3.10 or newer recommended.
- On Windows, install Python from python.org and check **Add Python to PATH**.
- On macOS, install Python 3 from python.org or Homebrew.

## Run from source

### Windows

Double-click:

```bat
run_windows.bat
```

Or run manually:

```bat
py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python gui.py
```

### macOS / Linux

Run:

```bash
chmod +x run_mac_linux.sh
./run_mac_linux.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python gui.py
```

## Build a distributable executable

Build on the same operating system you want to distribute for. For example, build the Windows `.exe` on Windows and the macOS `.app` on macOS.

### Windows

```bat
build_windows.bat
```

Output:

```text
dist\ENGR_Scheduler\ENGR_Scheduler.exe
```

Zip the entire `dist\ENGR_Scheduler` folder before sharing it.

### macOS

```bash
chmod +x build_mac_linux.sh
./build_mac_linux.sh
```

Output:

```text
dist/ENGR_Scheduler.app
```

Zip `dist/ENGR_Scheduler.app` before sharing it.

### Linux

```bash
./build_mac_linux.sh
```

Output:

```text
dist/ENGR_Scheduler/ENGR_Scheduler
```

## How to use

1. Open the app.
2. Use the **Sections**, **Faculty**, and **Time Slots** tabs to edit scheduling data.
3. Click **Save DB** to save edits.
4. Click **Run Solver** to generate a schedule.
5. Use the table filters or Gantt chart to inspect results.
6. Select a section and click **Freeze** to pin it to its current slot, or **Unfreeze** to remove the pin.
7. Use **Restore** to undo the last database save, or **Default** to reset to `db_classes_default.db`.

## Architecture and pipeline

This project is intentionally kept at a solid ENGR340 student-code level:

1. `gui.py` starts the desktop app and owns the main window.
2. `tabs.py` contains the editable table tabs for sections, faculty, and time slots.
3. `db.py` is the only file that saves GUI edits back to SQLite.
4. `solver.py` reads the database, builds the OR-Tools CP-SAT model, and returns schedule rows.
5. `gui.py` displays the solver output in a table and a weekly Gantt chart.

The database is plain SQLite. It has only these five data tables: `db_classes`, `faculty`, `faculty_can_teach`, `availability`, and `time_slots`. There are no views, triggers, stored procedures, or custom extensions. The only indexes are automatic primary-key indexes created by SQLite.

## Health check

Run this before submitting or building:

```bash
python health_check.py
```

It checks Python syntax, verifies the database has only the expected plain tables, and checks for blank IDs, orphan faculty records, and invalid frozen slots.

## Notes

- The first time a bundled executable runs, it copies the included database into the user's app data folder so edits persist.
- The Gantt chart is written to `.gantt_schedule.html` inside the project folder.
- If PyInstaller reports missing Qt WebEngine files, rebuild in a clean virtual environment and make sure `PySide6`, `PySide6-Addons`, and `PySide6-Essentials` are installed.
- I verified the Python files compile successfully and the included databases pass `health_check.py`. I could not run the GUI/solver in this environment because PySide6 and OR-Tools are not installed here.

## Troubleshooting

### `ModuleNotFoundError: PySide6` or `ortools`

Activate the virtual environment, then run:

```bash
python -m pip install -r requirements.txt
```

### Blank Gantt chart

Make sure the app has permission to write files in the selected project folder. The app writes `.gantt_schedule.html` locally and loads it into Qt WebEngine.

### Solver returns skipped sections

Check that each section has:

- a matching `slot_type` in the Time Slots tab,
- at least one faculty member who can teach its course ID,
- faculty availability that covers the selected time slot,
- a valid frozen slot if one is set.
