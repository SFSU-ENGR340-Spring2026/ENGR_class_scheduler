"""
ENGR Class Scheduler - Database helpers.
All functions that read from or write to db_classes.db live here.
gui.py imports from this file; solver.py reads the DB directly on its own.
"""

import sqlite3
from collections import defaultdict


def load_sections(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT section_id, class_id, class_type, slot_type, capacity FROM db_classes ORDER BY class_id, section_id")
    rows = cur.fetchall()
    conn.close()
    return rows


def save_sections(db_path, rows):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for sid, cid, ctype, stype, cap in rows:
        if not sid.strip():
            continue
        cur.execute("SELECT 1 FROM db_classes WHERE section_id=?", (sid,))
        if cur.fetchone():
            cur.execute("UPDATE db_classes SET class_id=?, class_type=?, slot_type=?, capacity=? WHERE section_id=?",
                        (cid, ctype, stype, cap, sid))
        else:
            cur.execute("INSERT INTO db_classes (section_id, class_id, class_type, slot_type, capacity) VALUES (?,?,?,?,?)",
                        (sid, cid, ctype, stype, cap))
    conn.commit()
    conn.close()


def delete_section(db_path, sid):
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM db_classes WHERE section_id=?", (sid,))
    conn.commit()
    conn.close()


def load_faculty(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT faculty_code, faculty_name FROM faculty ORDER BY faculty_code")
    faculty = cur.fetchall()

    cur.execute("SELECT faculty_code, course_id FROM faculty_can_teach")
    can_teach = defaultdict(list)
    for code, course in cur.fetchall():
        can_teach[code].append(course)

    cur.execute("SELECT faculty_code, day_of_week, start_time, end_time FROM availability")
    avail = defaultdict(dict)
    for code, day, s, e in cur.fetchall():
        avail[code][day] = (s, e)

    conn.close()

    result = []
    for code, name in faculty:
        courses_str = ", ".join(sorted(can_teach[code]))
        result.append((code, name, courses_str, avail[code]))
    return result


def save_faculty(db_path, rows):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for code, name, courses_str, avail_dict in rows:
        if not code.strip():
            continue
        cur.execute("INSERT OR REPLACE INTO faculty (faculty_code, faculty_name) VALUES (?,?)",
                    (code, name.strip()))
        cur.execute("DELETE FROM faculty_can_teach WHERE faculty_code=?", (code,))
        for c in courses_str.split(","):
            c = c.strip()
            if c:
                cur.execute("INSERT OR IGNORE INTO faculty_can_teach (faculty_code, course_id) VALUES (?,?)",
                            (code, c))
        cur.execute("DELETE FROM availability WHERE faculty_code=?", (code,))
        for day, (s, e) in avail_dict.items():
            cur.execute("INSERT INTO availability (faculty_code, day_of_week, start_time, end_time) VALUES (?,?,?,?)",
                        (code, day, s, e))
    conn.commit()
    conn.close()


def delete_faculty(db_path, code):
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM faculty WHERE faculty_code=?", (code,))
    conn.execute("DELETE FROM faculty_can_teach WHERE faculty_code=?", (code,))
    conn.execute("DELETE FROM availability WHERE faculty_code=?", (code,))
    conn.commit()
    conn.close()


def load_time_slots(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT slot_id, slot_type, day_pattern, start_time, end_time FROM time_slots ORDER BY slot_type, day_pattern, start_time")
    rows = cur.fetchall()
    conn.close()
    return rows


def save_time_slots(db_path, rows):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for slot_id, stype, pattern, start, end in rows:
        sid = str(slot_id).strip()
        if not sid:
            continue
        if sid.isdigit():
            cur.execute("UPDATE time_slots SET slot_type=?, day_pattern=?, start_time=?, end_time=? WHERE slot_id=?",
                        (stype, pattern, start, end, int(sid)))
        else:
            cur.execute("INSERT INTO time_slots (slot_type, day_pattern, start_time, end_time) VALUES (?,?,?,?)",
                        (stype, pattern, start, end))
    conn.commit()
    conn.close()


def delete_time_slot(db_path, slot_id):
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM time_slots WHERE slot_id=?", (int(slot_id),))
    conn.commit()
    conn.close()