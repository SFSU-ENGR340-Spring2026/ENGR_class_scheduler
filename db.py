"""
ENGR Class Scheduler - Database helpers.
All functions that read from or write to db_classes.db live here.
gui.py imports from this file; solver.py reads the DB directly on its own.
"""

import sqlite3
from collections import defaultdict


def load_course_rooms(db_path):
    """Return {course_id: [room, ...]} from the course_rooms table (legacy)."""
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    try:
        cur.execute("SELECT course_id, room FROM course_rooms")
        out = defaultdict(list)
        for course, room in cur.fetchall():
            out[course].append(room)
    except sqlite3.OperationalError:
        out = {}
    conn.close()
    return dict(out)


def load_sections(db_path):
    """Return every row from db_classes.
    Tries full 8-column schema first; falls back to legacy 5-column schema."""
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    try:
        cur.execute("""
            SELECT section_id, class_id, class_type, slot_type, capacity,
                   major, lab_room, frozen_slot_id
            FROM   db_classes
            ORDER  BY class_id, section_id
        """)
    except sqlite3.OperationalError:
        cur.execute("""
            SELECT section_id, class_id, class_type, slot_type, capacity
            FROM   db_classes
            ORDER  BY class_id, section_id
        """)
    rows = cur.fetchall()
    conn.close()
    return rows


def save_sections(db_path, rows):
    """Upsert sections. Silently skips blank or incomplete rows.
    Migrates older DBs that are missing the newer columns."""
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    # Migrate older DBs
    for col_sql in [
        "ALTER TABLE db_classes ADD COLUMN major          TEXT    DEFAULT ''",
        "ALTER TABLE db_classes ADD COLUMN lab_room       TEXT    DEFAULT ''",
        "ALTER TABLE db_classes ADD COLUMN frozen_slot_id INTEGER DEFAULT NULL",
    ]:
        try:
            cur.execute(col_sql)
        except sqlite3.OperationalError:
            pass  # column already exists

    for row in rows:
        if len(row) == 5:
            sid, cid, ctype, stype, cap = row
            major, lab_room, frozen = "", "", None
        else:
            sid, cid, ctype, stype, cap, major, lab_room, frozen = row

        sid_s = str(sid).strip()
        cid_s = str(cid).strip()
        if not sid_s or not cid_s or sid_s in ("-", "_"):
            continue

        try:
            frozen_val = int(frozen) if frozen not in (None, "", "None") else None
        except (ValueError, TypeError):
            frozen_val = None

        cur.execute("SELECT 1 FROM db_classes WHERE section_id=?", (sid_s,))
        if cur.fetchone():
            cur.execute("""
                UPDATE db_classes
                SET    class_id=?, class_type=?, slot_type=?, capacity=?,
                       major=?, lab_room=?, frozen_slot_id=?
                WHERE  section_id=?
            """, (cid_s, ctype, stype, cap, major or "", lab_room or "",
                  frozen_val, sid_s))
        else:
            cur.execute("""
                INSERT INTO db_classes
                    (section_id, class_id, class_type, slot_type, capacity,
                     major, lab_room, frozen_slot_id)
                VALUES (?,?,?,?,?,?,?,?)
            """, (sid_s, cid_s, ctype, stype, cap,
                  major or "", lab_room or "", frozen_val))

    conn.commit()
    conn.close()


def delete_section(db_path, sid):
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM db_classes WHERE section_id=?", (sid,))
    conn.commit()
    conn.close()


def load_faculty(db_path):
    """Return list of (faculty_code, faculty_name, wtu_str, courses_str, avail_dict).
    avail_dict → {day: [(start, end), ...]}"""
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    # Auto-migrate: add wtu column to older DBs
    try:
        cur.execute("ALTER TABLE faculty ADD COLUMN wtu REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cur.execute("SELECT faculty_code, faculty_name, wtu FROM faculty ORDER BY faculty_code")
    faculty = cur.fetchall()

    cur.execute("SELECT faculty_code, course_id FROM faculty_can_teach")
    can_teach = defaultdict(list)
    for code, course in cur.fetchall():
        can_teach[code].append(course)

    cur.execute("SELECT faculty_code, day_of_week, start_time, end_time FROM availability")
    avail = defaultdict(lambda: defaultdict(list))
    for code, day, s, e in cur.fetchall():
        avail[code][day].append((s, e))

    conn.close()

    result = []
    for code, name, wtu in faculty:
        courses_str = ", ".join(sorted(can_teach[code]))
        wtu_str = f"{wtu:g}" if wtu is not None else ""
        result.append((code, name, wtu_str, courses_str, dict(avail[code])))
    return result


def save_faculty(db_path, rows):
    """Upsert faculty rows including availability windows and can-teach lists."""
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    try:
        cur.execute("ALTER TABLE faculty ADD COLUMN wtu REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    for code, name, wtu, courses_str, avail_dict in rows:
        if not code.strip():
            continue

        try:
            wtu_val = float(wtu)
        except (ValueError, TypeError):
            wtu_val = 0.0

        cur.execute("INSERT OR REPLACE INTO faculty (faculty_code, faculty_name, wtu) VALUES (?,?,?)",
                    (code, name.strip(), wtu_val))

        cur.execute("DELETE FROM faculty_can_teach WHERE faculty_code=?", (code,))
        for c in courses_str.split(","):
            c = c.strip()
            if c:
                cur.execute("INSERT OR IGNORE INTO faculty_can_teach (faculty_code, course_id) VALUES (?,?)",
                            (code, c))

        cur.execute("DELETE FROM availability WHERE faculty_code=?", (code,))
        for day, windows in avail_dict.items():
            if isinstance(windows, list):
                for s, e in windows:
                    cur.execute("""INSERT INTO availability
                        (faculty_code, day_of_week, start_time, end_time) VALUES (?,?,?,?)""",
                        (code, day, s, e))
            else:
                # Defensive: single tuple instead of list
                s, e = windows
                cur.execute("""INSERT INTO availability
                    (faculty_code, day_of_week, start_time, end_time) VALUES (?,?,?,?)""",
                    (code, day, s, e))

    conn.commit()
    conn.close()


def delete_faculty(db_path, code):
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM faculty           WHERE faculty_code=?", (code,))
    conn.execute("DELETE FROM faculty_can_teach WHERE faculty_code=?", (code,))
    conn.execute("DELETE FROM availability      WHERE faculty_code=?", (code,))
    conn.commit()
    conn.close()


def load_time_slots(db_path):
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    cur.execute("""
        SELECT slot_id, slot_type, day_pattern, start_time, end_time
        FROM   time_slots
        ORDER  BY slot_type, day_pattern, start_time
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def save_time_slots(db_path, rows):
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    for slot_id, stype, pattern, start, end in rows:
        sid = str(slot_id).strip()
        if not sid:
            continue
        if not any([stype, pattern, start, end]):
            continue
        if sid.isdigit():
            cur.execute("""
                UPDATE time_slots
                SET    slot_type=?, day_pattern=?, start_time=?, end_time=?
                WHERE  slot_id=?
            """, (stype, pattern, start, end, int(sid)))
        else:
            cur.execute("""
                INSERT INTO time_slots (slot_type, day_pattern, start_time, end_time)
                VALUES (?,?,?,?)
            """, (stype, pattern, start, end))
    conn.commit()
    conn.close()


def delete_time_slot(db_path, slot_id):
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM time_slots WHERE slot_id=?", (int(slot_id),))
    conn.commit()
    conn.close()
