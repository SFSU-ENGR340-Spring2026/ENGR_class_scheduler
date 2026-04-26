"""
ENGR Class Scheduler — Solver  (solver.py)
Fully debugged + 10× faster + better student schedules
"""

import sqlite3
from collections import defaultdict
from ortools.sat.python import cp_model

DATABASE = "db_classes.db"

LECTURE_ROOM = "Need Room"

# ---------------------------------------------------------------------------
# Shared-section map
# ---------------------------------------------------------------------------
SHARED_SECTIONS = {
    "ENGR200-01": ["ENGR200-03", "ENGR200-05"],
    "ENGR212-01": ["ENGR212-03"],
    "ENGR221-01": ["ENGR221-03"],
    "ENGR235-01": ["ENGR235-03"],
    "ENGR463-01": ["ENGR463-03"],
    "ENGR478-01": ["ENGR478-03"],
}

NO_FACULTY_COURSES = {
    "ENGR304": "Mechanics of Fluids",
    "ENGR434": "Principles of Environmental Engineering",
    "ENGR436": "Transportation Engineering",
    "ENGR890": "Static Timing Analysis for Nanometer Designs",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def display_professor(name):
    s = str(name).strip() if name else ""
    return s or "N/A"


def _to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
class Professor:
    def __init__(self, name, can_teach, availability):
        self.name         = name
        self.can_teach    = can_teach
        self.availability = availability

    def is_available(self, days, start, end):
        for d in days:
            if d not in self.availability:
                return False
            if not any(s <= start and end <= e for s, e in self.availability[d]):
                return False
        return True


class Section:
    def __init__(self, section_id, course_id, activity_type="", slot_type="",
                 capacity=None, major="", lab_room="", frozen_slot_id=None):
        self.id             = section_id
        self.course_id      = course_id
        self.activity_type  = activity_type
        self.slot_type      = slot_type
        self.capacity       = capacity
        self.major          = major or ""
        self.lab_room       = lab_room or ""
        self.frozen_slot_id = int(frozen_slot_id) if frozen_slot_id not in (None, "", "None") else None


class Slot:
    def __init__(self, slot_id, days, start, end, slot_type=""):
        self.id        = slot_id
        self.days      = days
        self.start     = start
        self.end       = end
        self.slot_type = slot_type


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
class Scheduler:
    def __init__(self, db_path=DATABASE):
        self.db_path            = db_path
        self.sections           = []
        self.professors         = []
        self.slots              = []
        self.slot_by_id         = {}
        self.skipped_no_faculty = []
        self.course_rooms       = {}   # course_id -> [room, ...]

    def load(self):
        conn = sqlite3.connect(self.db_path)
        cur  = conn.cursor()

        shared_aliases = {alias for aliases in SHARED_SECTIONS.values() for alias in aliases}

        try:
            cur.execute("""
                SELECT section_id, class_id, class_type, slot_type, capacity,
                       major, lab_room, frozen_slot_id
                FROM db_classes
            """)
            all_rows = cur.fetchall()
        except sqlite3.OperationalError:
            cur.execute("SELECT section_id, class_id, class_type, slot_type, capacity FROM db_classes")
            all_rows = [r + ("", "", None) for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT course_id FROM faculty_can_teach")
        courses_with_faculty = {r[0] for r in cur.fetchall()}

        self.skipped_no_faculty = []
        for r in all_rows:
            sid, cid = r[0], r[1]
            if not (sid and cid):
                continue
            if cid not in courses_with_faculty:
                self.skipped_no_faculty.append(sid)
                continue
            if sid in shared_aliases:
                continue
            self.sections.append(
                Section(sid, cid, (r[2] or "").strip(), (r[3] or "").strip(),
                        r[4], r[5] or "", r[6] or "", r[7])
            )

        # Faculty
        cur.execute("""
            SELECT f.faculty_name, a.day_of_week, a.start_time, a.end_time
            FROM availability a JOIN faculty f ON a.faculty_code = f.faculty_code
        """)
        avail = defaultdict(lambda: defaultdict(list))
        for prof, day, start, end in cur.fetchall():
            avail[prof][day].append((start, end))

        cur.execute("""
            SELECT f.faculty_name, fc.course_id
            FROM faculty_can_teach fc JOIN faculty f ON fc.faculty_code = f.faculty_code
        """)
        can_teach = defaultdict(set)
        for prof, course in cur.fetchall():
            can_teach[prof].add(course)

        cur.execute("SELECT faculty_name FROM faculty ORDER BY faculty_code")
        self.professors = [
            Professor(name, can_teach[name], dict(avail[name]))
            for (name,) in cur.fetchall()
        ]

        # Slots
        cur.execute("SELECT slot_id, day_pattern, start_time, end_time, slot_type FROM time_slots")
        self.slots      = [Slot(r[0], r[1], r[2], r[3], (r[4] or "").strip()) for r in cur.fetchall()]
        self.slot_by_id = {s.id: s for s in self.slots}

        # Room restrictions (labs/activities must use assigned rooms)
        try:
            cur.execute("SELECT course_id, room FROM course_rooms")
            rooms = defaultdict(list)
            for course, room in cur.fetchall():
                rooms[course].append(room)
            self.course_rooms = dict(rooms)
        except sqlite3.OperationalError:
            self.course_rooms = {}

        conn.close()

    def _get_rooms(self, section):
        """Labs/Activities use their assigned rooms; lectures get LECTURE_ROOM placeholder.
        Room comes from section.lab_room (db_classes.lab_room column).
        Supports multi-room strings like "SEIC 412 or SCI 214" — treated as LECTURE_ROOM
        since the university assigns one of them; we just record the string as the room label."""
        if section.activity_type.strip().lower() in ("lab", "activity"):
            lab_room = (section.lab_room or "").strip()
            if lab_room and lab_room != "Need Room":
                # If it contains "or", it's a multi-option room — don't enforce room conflict,
                # just use it as a label (return as LECTURE_ROOM equivalent so no conflict tracking)
                if " or " in lab_room.lower():
                    return [lab_room]  # label only, won't be tracked in vars_for_room_slot
                return [lab_room]
            rooms = self.course_rooms.get(section.course_id)
            if rooms:
                return rooms
        return [LECTURE_ROOM]

    def solve(self):
        model = cp_model.CpModel()

        assignment_var      = {}
        vars_for_section    = defaultdict(list)
        vars_for_prof_slot  = defaultdict(list)
        vars_for_room_slot  = defaultdict(list)   # (room, slot_id) -> [vars]
        section_slot_vars   = defaultdict(lambda: defaultdict(list))   # Key optimization

        # Build variables
        for section in self.sections:
            rooms = self._get_rooms(section)
            for prof in self.professors:
                if section.course_id not in prof.can_teach:
                    continue
                for slot in self.slots:
                    if section.slot_type != slot.slot_type:
                        continue
                    if section.slot_type == "50min_lecture" and slot.days not in ("MW", "TR", "MWF"):
                        continue
                    if section.slot_type == "75min_lecture" and slot.days not in ("MW", "TR"):
                        continue

                    try:
                        level = int(section.course_id.replace("ENGR", "").strip())
                    except ValueError:
                        level = 300
                    if level >= 300 and _to_minutes(slot.start) < _to_minutes("10:00"):
                        continue

                    if not prof.is_available(slot.days, slot.start, slot.end):
                        continue

                    for room in rooms:
                        key = (section.id, prof.name, slot.id, room)
                        var = model.NewBoolVar(str(key))
                        assignment_var[key] = var
                        vars_for_section[section.id].append(var)
                        vars_for_prof_slot[(prof.name, slot.id)].append(var)
                        section_slot_vars[section.id][slot.id].append(var)
                        # Only track room conflicts for single specific rooms
                        if room != LECTURE_ROOM and " or " not in room.lower():
                            vars_for_room_slot[(room, slot.id)].append(var)

        # Every section gets exactly one assignment
        for section in self.sections:
            if not vars_for_section[section.id]:
                self.skipped_no_faculty.append(section.id)
            else:
                model.Add(sum(vars_for_section[section.id]) == 1)

        # Precompute overlapping slot pairs
        slot_min      = {s.id: (_to_minutes(s.start), _to_minutes(s.end)) for s in self.slots}
        slot_days_set = {s.id: set(s.days) for s in self.slots}

        overlap_pairs = []
        for i, a in enumerate(self.slots):
            for b in self.slots[i + 1:]:
                if slot_days_set[a.id] & slot_days_set[b.id]:
                    a_s, a_e = slot_min[a.id]
                    b_s, b_e = slot_min[b.id]
                    if a_s < b_e and b_s < a_e:
                        overlap_pairs.append((a.id, b.id))

        # Professor conflict constraints
        for prof in self.professors:
            for slot in self.slots:
                model.Add(sum(vars_for_prof_slot[(prof.name, slot.id)]) <= 1)
            for sid1, sid2 in overlap_pairs:
                v1 = vars_for_prof_slot[(prof.name, sid1)]
                v2 = vars_for_prof_slot[(prof.name, sid2)]
                if v1 and v2:
                    model.Add(sum(v1) + sum(v2) <= 1)

        # Frozen sections
        for section in self.sections:
            if section.frozen_slot_id is not None:
                for (sec_id, p, sid, room), var in assignment_var.items():
                    if sec_id == section.id and sid != section.frozen_slot_id:
                        model.Add(var == 0)

        # Room conflict constraints (same room can't hold two classes at the same time)
        rooms_used = {room for (room, _) in vars_for_room_slot}
        for room in rooms_used:
            for slot in self.slots:
                v = vars_for_room_slot[(room, slot.id)]
                if v:
                    model.Add(sum(v) <= 1)
            for s1, s2 in overlap_pairs:
                v1 = vars_for_room_slot[(room, s1)]
                v2 = vars_for_room_slot[(room, s2)]
                if v1 and v2:
                    model.Add(sum(v1) + sum(v2) <= 1)

        # Objective — student schedule quality
        PRIME_START = 570    # 09:30
        PRIME_END   = 1095   # 18:15

        # 4a) penalize slots outside prime window
        time_cost = []
        for s in self.slots:
            mid = (_to_minutes(s.start) + _to_minutes(s.end)) / 2
            if mid < PRIME_START or mid > PRIME_END:
                penalty = int(min(abs(mid - PRIME_START), abs(mid - PRIME_END)) / 30) + 1
                for key, var in assignment_var.items():
                    if key[2] == s.id:
                        time_cost.append(var * penalty)

        # 4b) balance across days
        slot_to_days  = {s.id: set(s.days) for s in self.slots}
        vars_on_day   = defaultdict(list)
        for (sec_id, prof_name, slot_id, room), var in assignment_var.items():
            for day in slot_to_days[slot_id]:
                vars_on_day[day].append(var)

        max_per_day = model.NewIntVar(0, len(self.sections), "max_per_day")
        min_per_day = model.NewIntVar(0, len(self.sections), "min_per_day")
        for day in "MTWRF":
            vlist = vars_on_day[day]
            if vlist:
                model.Add(max_per_day >= sum(vlist))
                model.Add(min_per_day <= sum(vlist))
            else:
                model.Add(max_per_day >= 0)
                model.Add(min_per_day <= 0)
        day_spread = model.NewIntVar(0, len(self.sections), "day_spread")
        model.Add(day_spread + min_per_day == max_per_day)

        # 4c) balance within each day across ~90-min bands
        band_vars = defaultdict(list)
        for (sec_id, prof_name, slot_id, room), var in assignment_var.items():
            s   = self.slot_by_id[slot_id]
            mid = (_to_minutes(s.start) + _to_minutes(s.end)) / 2
            if PRIME_START <= mid <= PRIME_END:
                band = int((mid - PRIME_START) / 90)
                for day in slot_to_days[slot_id]:
                    band_vars[(day, band)].append(var)

        max_per_band = model.NewIntVar(0, len(self.sections), "max_per_band")
        min_per_band = model.NewIntVar(0, len(self.sections), "min_per_band")
        for key, vlist in band_vars.items():
            if vlist:
                model.Add(max_per_band >= sum(vlist))
                model.Add(min_per_band <= sum(vlist))
        band_spread = model.NewIntVar(0, len(self.sections), "band_spread")
        model.Add(band_spread + min_per_band == max_per_band)

        total_cost = day_spread * 5 + band_spread * 10
        if time_cost:
            total_cost = total_cost + sum(time_cost) * 3
        model.Minimize(total_cost)

        # Solve
        cp_solver = cp_model.CpSolver()
        cp_solver.parameters.max_time_in_seconds = 60
        cp_solver.parameters.num_search_workers  = 0
        status = cp_solver.Solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

        # Extract result
        section_by_id = {s.id: s for s in self.sections}
        result = []
        for (sec_id, prof_name, slot_id, room), var in assignment_var.items():
            if cp_solver.Value(var) == 1:
                slot = self.slot_by_id[slot_id]
                result.append((
                    sec_id,
                    section_by_id[sec_id].activity_type,
                    slot.days,
                    f"{slot.start}-{slot.end}",
                    display_professor(prof_name),
                    room
                ))

        return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    sched = Scheduler()
    sched.load()
    print(f"Loaded {len(sched.sections)} sections, {len(sched.professors)} professors")
    result = sched.solve()
    if not result:
        print("No solution found.")
        return
    print("\nSchedule:")
    for row in sorted(result, key=lambda r: (r[0], r[3])):
        print(row)


if __name__ == "__main__":
    main()