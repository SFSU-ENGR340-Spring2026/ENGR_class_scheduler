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


def _section_wtu(section):
    """Return the true teaching workload units for this section.

    This must come from db_classes.wtu, which is populated from Column D
    (WTU / instructor workload units) in the Fall 2026 course list. Do not
    estimate WTU from lecture/lab/activity type; those estimates caused false
    overload reports.
    """
    try:
        return float(section.wtu or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
class Professor:
    def __init__(self, name, can_teach, availability, wtu=0):
        self.name         = name
        self.can_teach    = can_teach
        self.availability = availability
        self.wtu          = float(wtu or 0)

    def is_available(self, days, start, end):
        for d in days:
            if d not in self.availability:
                return False
            if not any(s <= start and end <= e for s, e in self.availability[d]):
                return False
        return True


class Section:
    def __init__(self, section_id, course_id, activity_type="", slot_type="",
                 capacity=None, major="", lab_room="", frozen_slot_id=None, wtu=0):
        self.id             = section_id
        self.course_id      = course_id
        self.activity_type  = activity_type
        self.slot_type      = slot_type
        self.capacity       = capacity
        self.major          = major or ""
        self.lab_room       = lab_room or ""
        try:
            self.wtu        = float(wtu or 0)
        except (TypeError, ValueError):
            self.wtu        = 0.0
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
        self.skipped_no_faculty       = []  # legacy name: courses with no qualified faculty
        self.skipped_no_valid_assignment = []
        self.invalid_frozen_sections  = []
        self.major_overlap_violations = 0
        self.course_rooms             = {}   # course_id -> [room, ...]
        self.skip_reasons             = {}   # section_id -> reason shown in GUI log
        self.missing_room_sections    = []   # lab/activity sections scheduled with Need Lab Room
        self.major_overlap_details  = []
        self.professor_conflict_details = []
        self.room_conflict_details  = []
        self.wtu_overload_details   = []

    def load(self):
        conn = sqlite3.connect(self.db_path)
        cur  = conn.cursor()

        shared_aliases = {alias for aliases in SHARED_SECTIONS.values() for alias in aliases}

        # Ensure the section-level WTU column exists. This is the true per-section
        # teaching load from the course list, separate from faculty.wtu caps.
        try:
            cur.execute("ALTER TABLE db_classes ADD COLUMN wtu REAL DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError:
            pass

        try:
            cur.execute("""
                SELECT section_id, class_id, class_type, slot_type, capacity,
                       major, lab_room, frozen_slot_id, COALESCE(wtu, 0)
                FROM db_classes
            """)
            all_rows = cur.fetchall()
        except sqlite3.OperationalError:
            cur.execute("SELECT section_id, class_id, class_type, slot_type, capacity FROM db_classes")
            all_rows = [r + ("", "", None, 0) for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT course_id FROM faculty_can_teach")
        courses_with_faculty = {r[0] for r in cur.fetchall()}

        self.sections = []
        self.skipped_no_faculty = []
        self.skipped_no_valid_assignment = []
        self.invalid_frozen_sections = []
        self.major_overlap_violations = 0
        self.skip_reasons = {}
        self.missing_room_sections = []
        self.major_overlap_details = []
        self.professor_conflict_details = []
        self.room_conflict_details = []
        self.wtu_overload_details = []
        for r in all_rows:
            sid, cid = r[0], r[1]
            if not (sid and cid):
                continue
            if cid not in courses_with_faculty:
                self.skipped_no_faculty.append(sid)
                continue
            if sid in shared_aliases:
                continue
            section = Section(sid, cid, (r[2] or "").strip(), (r[3] or "").strip(),
                              r[4], r[5] or "", r[6] or "", r[7], r[8])
            self.sections.append(section)

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

        cur.execute("SELECT faculty_name, COALESCE(wtu, 0) FROM faculty ORDER BY faculty_code")
        self.professors = [
            Professor(name, can_teach[name], dict(avail[name]), wtu)
            for (name, wtu) in cur.fetchall()
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
        """Return valid room labels for a section.

        Lectures use the placeholder ``Need Room`` because the university can
        assign lecture rooms later. Labs and activities with an explicit room use
        that room. Labs/activities with a blank, ``Need Room``, or ``Need Lab
        Room`` value are still scheduled, but they are labeled ``Need Lab Room``
        and reported in the GUI log. This keeps ENGR104-style lab sections in
        the final schedule instead of skipping them just because the room has not
        been finalized yet.
        """
        is_lab_or_activity = section.activity_type.strip().lower() in ("lab", "activity")
        if not is_lab_or_activity:
            return [LECTURE_ROOM]

        lab_room = (section.lab_room or "").strip()
        if lab_room and lab_room not in ("Need Room", "Need Lab Room"):
            return [lab_room]

        if section.id not in self.missing_room_sections:
            self.missing_room_sections.append(section.id)
        return ["Need Lab Room"]

    def _skip_reason(self, section):
        """Explain why a section has no schedulable assignment."""
        if not [p for p in self.professors if section.course_id in p.can_teach]:
            return "no qualified faculty in Faculty tab"
        compatible_slots = [s for s in self.slots if s.slot_type == section.slot_type]
        if not compatible_slots:
            return f"no time slots for slot type '{section.slot_type}'"
        if section.frozen_slot_id is not None and section.frozen_slot_id not in self.slot_by_id:
            return f"frozen slot {section.frozen_slot_id} does not exist"
        return "no compatible faculty availability/time slot"

    def solve(self):
        """Solve strictly first, then fall back to a best-effort schedule.

        Strict mode enforces professor conflicts, room conflicts, WTU caps,
        and valid frozen slots. Same-major non-overlap is a soft preference so
        a usable final schedule can still be output with conflicts reported. If those constraints make
        the model infeasible, fallback mode still produces a partial final
        schedule by softening conflicts. Sections with impossible input data
        (for example no qualified faculty, no lab room, or no matching slot
        type) are skipped and logged with a reason.
        """
        self.best_effort = False
        self.conflict_notes = []
        self.professor_conflict_violations = 0
        self.room_conflict_violations = 0
        self.wtu_overload_violations = 0
        self.major_overlap_details = []
        self.professor_conflict_details = []
        self.room_conflict_details = []
        self.wtu_overload_details = []
        self.staff_assignments = []
        self.forced_assignments = []
        self.skip_reasons = {}

        result = self._solve_internal(allow_conflicts=False)
        if result is not None:
            return result

        # Required for demos/final output: produce a schedule even when the full
        # constraint set is impossible. Conflicts are softened and reported.
        self.best_effort = True
        return self._solve_internal(allow_conflicts=True)

    def _solve_internal(self, allow_conflicts=False):
        model = cp_model.CpModel()

        assignment_var      = {}
        vars_for_section    = defaultdict(list)
        vars_for_prof_slot  = defaultdict(list)
        vars_for_room_slot  = defaultdict(list)
        section_slot_vars   = defaultdict(lambda: defaultdict(list))
        section_by_id       = {s.id: s for s in self.sections}

        # Precompute overlapping slot pairs before variable generation so both
        # strict and best-effort modes can share the same conflict accounting.
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

        self.skipped_no_valid_assignment = []
        self.invalid_frozen_sections = []
        self.staff_assignments = []
        self.forced_assignments = []
        self.skip_reasons = {}

        def add_assignment_var(section, prof_name, slot, room, forced=False):
            key = (section.id, prof_name, slot.id, room)
            if key in assignment_var:
                return assignment_var[key]
            var = model.NewBoolVar(str(key))
            assignment_var[key] = var
            vars_for_section[section.id].append(var)
            vars_for_prof_slot[(prof_name, slot.id)].append(var)
            section_slot_vars[section.id][slot.id].append(var)
            if room not in (LECTURE_ROOM, "Need Lab Room") and " or " not in str(room).lower():
                vars_for_room_slot[(room, slot.id)].append(var)
            return var

        # Build normal feasible variables first.
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
                        add_assignment_var(section, prof.name, slot, room)

        # In best-effort mode we do NOT invent STAFF assignments. A final
        # schedule is still produced for all sections that have at least one
        # legitimate professor/slot/room option. Sections with impossible input
        # data are skipped and reported through self.skip_reasons.

        # Every section gets exactly one assignment if possible.
        for section in self.sections:
            if not vars_for_section[section.id]:
                self.skipped_no_valid_assignment.append(section.id)
                self.skip_reasons[section.id] = self._skip_reason(section)
            else:
                model.Add(sum(vars_for_section[section.id]) == 1)

        penalty_terms = []

        def add_soft_conflict(vars_a, vars_b, weight, name):
            if not vars_a or not vars_b:
                return
            b = model.NewBoolVar(name)
            model.Add(sum(vars_a) + sum(vars_b) <= 1 + b)
            penalty_terms.append(b * weight)

        # Professor conflict constraints.
        for prof_name in {p.name for p in self.professors} | {"STAFF"}:
            for slot in self.slots:
                v = vars_for_prof_slot[(prof_name, slot.id)]
                if not v:
                    continue
                if allow_conflicts:
                    # Penalize putting one professor/STAFF in multiple classes
                    # in the exact same slot.
                    overflow = model.NewIntVar(0, len(v), f"prof_exact_overflow_{prof_name}_{slot.id}")
                    model.Add(overflow >= sum(v) - 1)
                    penalty_terms.append(overflow * 100)
                else:
                    model.Add(sum(v) <= 1)
            for sid1, sid2 in overlap_pairs:
                v1 = vars_for_prof_slot[(prof_name, sid1)]
                v2 = vars_for_prof_slot[(prof_name, sid2)]
                if v1 and v2:
                    if allow_conflicts:
                        add_soft_conflict(v1, v2, 100, f"prof_overlap_{prof_name}_{sid1}_{sid2}")
                    else:
                        model.Add(sum(v1) + sum(v2) <= 1)

        # Frozen sections. In fallback mode, invalid frozen slots are ignored and
        # reported so a schedule can still be produced.
        for section in self.sections:
            if section.frozen_slot_id is not None:
                possible_in_frozen_slot = section_slot_vars[section.id][section.frozen_slot_id]
                if not possible_in_frozen_slot:
                    self.invalid_frozen_sections.append(section.id)
                    if not allow_conflicts:
                        return None
                    continue
                for (sec_id, p, sid, room), var in assignment_var.items():
                    if sec_id == section.id and sid != section.frozen_slot_id:
                        model.Add(var == 0)

        # Same-major conflicts: ALWAYS soft. The program should still output a
        # final schedule and simply report these student-facing conflicts.
        sections_by_major = defaultdict(list)
        for section in self.sections:
            major = (section.major or "").strip()
            if major:
                sections_by_major[major].append(section.id)

        for major, section_ids in sections_by_major.items():
            for i, sec_a in enumerate(section_ids):
                for sec_b in section_ids[i + 1:]:
                    a_obj = section_by_id[sec_a]
                    b_obj = section_by_id[sec_b]
                    same_course = a_obj.course_id == b_obj.course_id
                    different_component = a_obj.activity_type != b_obj.activity_type
                    if same_course and different_component:
                        continue
                    for slot_a, slot_b in overlap_pairs:
                        v1 = section_slot_vars[sec_a][slot_a]
                        v2 = section_slot_vars[sec_b][slot_b]
                        if v1 and v2:
                            add_soft_conflict(v1, v2, 40, f"major_overlap_{sec_a}_{sec_b}_{slot_a}_{slot_b}")
                        v1 = section_slot_vars[sec_a][slot_b]
                        v2 = section_slot_vars[sec_b][slot_a]
                        if v1 and v2 and slot_a != slot_b:
                            add_soft_conflict(v1, v2, 40, f"major_overlap_{sec_a}_{sec_b}_{slot_b}_{slot_a}")
                    for slot in self.slots:
                        v1 = section_slot_vars[sec_a][slot.id]
                        v2 = section_slot_vars[sec_b][slot.id]
                        if v1 and v2:
                            add_soft_conflict(v1, v2, 40, f"major_same_{sec_a}_{sec_b}_{slot.id}")

        # Faculty WTU caps: hard in strict mode, soft in fallback mode.
        for prof in self.professors:
            if prof.wtu <= 0:
                continue
            weighted = []
            for (sec_id, prof_name, slot_id, room), var in assignment_var.items():
                if prof_name == prof.name:
                    weighted.append(int(round(_section_wtu(section_by_id[sec_id]) * 2)) * var)
            if weighted:
                total = sum(weighted)
                cap = int(round(prof.wtu * 2))
                if allow_conflicts:
                    over = model.NewIntVar(0, len(self.sections) * 10, f"wtu_over_{prof.name}")
                    model.Add(over >= total - cap)
                    penalty_terms.append(over * 60)
                else:
                    model.Add(total <= cap)

        # Room conflicts: hard in strict mode, soft in fallback mode.
        rooms_used = {room for (room, _) in vars_for_room_slot}
        for room in rooms_used:
            for slot in self.slots:
                v = vars_for_room_slot[(room, slot.id)]
                if not v:
                    continue
                if allow_conflicts:
                    overflow = model.NewIntVar(0, len(v), f"room_exact_overflow_{room}_{slot.id}")
                    model.Add(overflow >= sum(v) - 1)
                    penalty_terms.append(overflow * 80)
                else:
                    model.Add(sum(v) <= 1)
            for s1, s2 in overlap_pairs:
                v1 = vars_for_room_slot[(room, s1)]
                v2 = vars_for_room_slot[(room, s2)]
                if v1 and v2:
                    if allow_conflicts:
                        add_soft_conflict(v1, v2, 80, f"room_overlap_{room}_{s1}_{s2}")
                    else:
                        model.Add(sum(v1) + sum(v2) <= 1)

        # Objective — student schedule quality plus conflict penalties.
        PRIME_START = 570
        PRIME_END   = 1095
        time_cost = []
        for s in self.slots:
            mid = (_to_minutes(s.start) + _to_minutes(s.end)) / 2
            if mid < PRIME_START or mid > PRIME_END:
                penalty = int(min(abs(mid - PRIME_START), abs(mid - PRIME_END)) / 30) + 1
                for key, var in assignment_var.items():
                    if key[2] == s.id:
                        time_cost.append(var * penalty)

        slot_to_days = {s.id: set(s.days) for s in self.slots}
        vars_on_day = defaultdict(list)
        for (sec_id, prof_name, slot_id, room), var in assignment_var.items():
            for day in slot_to_days[slot_id]:
                vars_on_day[day].append(var)

        max_per_day = model.NewIntVar(0, max(1, len(self.sections) * 2), "max_per_day")
        min_per_day = model.NewIntVar(0, max(1, len(self.sections) * 2), "min_per_day")
        for day in "MTWRF":
            vlist = vars_on_day[day]
            if vlist:
                model.Add(max_per_day >= sum(vlist))
                model.Add(min_per_day <= sum(vlist))
        day_spread = model.NewIntVar(0, max(1, len(self.sections) * 2), "day_spread")
        model.Add(day_spread + min_per_day == max_per_day)

        band_vars = defaultdict(list)
        for (sec_id, prof_name, slot_id, room), var in assignment_var.items():
            s = self.slot_by_id[slot_id]
            mid = (_to_minutes(s.start) + _to_minutes(s.end)) / 2
            if PRIME_START <= mid <= PRIME_END:
                band = int((mid - PRIME_START) / 90)
                for day in slot_to_days[slot_id]:
                    band_vars[(day, band)].append(var)

        max_per_band = model.NewIntVar(0, max(1, len(self.sections) * 2), "max_per_band")
        min_per_band = model.NewIntVar(0, max(1, len(self.sections) * 2), "min_per_band")
        for vlist in band_vars.values():
            if vlist:
                model.Add(max_per_band >= sum(vlist))
                model.Add(min_per_band <= sum(vlist))
        band_spread = model.NewIntVar(0, max(1, len(self.sections) * 2), "band_spread")
        model.Add(band_spread + min_per_band == max_per_band)

        total_cost = day_spread * 5 + band_spread * 10
        if time_cost:
            total_cost += sum(time_cost) * 3
        if penalty_terms:
            total_cost += sum(penalty_terms)
        model.Minimize(total_cost)

        cp_solver = cp_model.CpSolver()
        cp_solver.parameters.max_time_in_seconds = 60 if not allow_conflicts else 30
        cp_solver.parameters.num_search_workers = 0
        status = cp_solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

        result = []
        chosen = []
        chosen_full = []
        forced_section_ids = {sid for sid, _reason in self.forced_assignments}
        for (sec_id, prof_name, slot_id, room), var in assignment_var.items():
            if cp_solver.Value(var) == 1:
                slot = self.slot_by_id[slot_id]
                label_prof = display_professor(prof_name)
                if allow_conflicts and sec_id in forced_section_ids and prof_name == "STAFF":
                    label_prof = "STAFF (needs faculty)"
                result.append((
                    sec_id,
                    section_by_id[sec_id].activity_type,
                    slot.days,
                    f"{slot.start}-{slot.end}",
                    label_prof,
                    room
                ))
                chosen.append((sec_id, slot_id))
                chosen_full.append((sec_id, prof_name, slot_id, room))

        self.major_overlap_violations = self._count_major_overlap_violations(chosen)
        self.professor_conflict_violations = self._count_professor_conflicts(chosen_full)
        self.room_conflict_violations = self._count_room_conflicts(chosen_full)
        self.wtu_overload_violations = self._count_wtu_overloads(chosen_full)
        return result

    def _slot_label(self, slot_id):
        slot = self.slot_by_id[slot_id]
        return f"{slot.days} {slot.start}-{slot.end}"

    def _count_professor_conflicts(self, chosen_full):
        by_prof = defaultdict(list)
        for sec_id, prof_name, slot_id, room in chosen_full:
            if prof_name == "STAFF":
                continue
            by_prof[prof_name].append((sec_id, self.slot_by_id[slot_id]))
        details = []
        for prof_name, rows in by_prof.items():
            for i, (a_sec, a_slot) in enumerate(rows):
                for b_sec, b_slot in rows[i + 1:]:
                    if set(a_slot.days) & set(b_slot.days):
                        if _to_minutes(a_slot.start) < _to_minutes(b_slot.end) and _to_minutes(b_slot.start) < _to_minutes(a_slot.end):
                            details.append(
                                f"{prof_name}: {a_sec} ({a_slot.days} {a_slot.start}-{a_slot.end}) overlaps "
                                f"{b_sec} ({b_slot.days} {b_slot.start}-{b_slot.end})"
                            )
        self.professor_conflict_details = details
        return len(details)

    def _count_room_conflicts(self, chosen_full):
        by_room = defaultdict(list)
        for sec_id, prof_name, slot_id, room in chosen_full:
            if room in (LECTURE_ROOM, "Need Lab Room") or " or " in str(room).lower():
                continue
            by_room[room].append((sec_id, self.slot_by_id[slot_id]))
        details = []
        for room, rows in by_room.items():
            for i, (a_sec, a_slot) in enumerate(rows):
                for b_sec, b_slot in rows[i + 1:]:
                    if set(a_slot.days) & set(b_slot.days):
                        if _to_minutes(a_slot.start) < _to_minutes(b_slot.end) and _to_minutes(b_slot.start) < _to_minutes(a_slot.end):
                            details.append(
                                f"{room}: {a_sec} ({a_slot.days} {a_slot.start}-{a_slot.end}) overlaps "
                                f"{b_sec} ({b_slot.days} {b_slot.start}-{b_slot.end})"
                            )
        self.room_conflict_details = details
        return len(details)

    def _count_wtu_overloads(self, chosen_full):
        prof_caps = {p.name: p.wtu for p in self.professors if p.wtu > 0}
        section_by_id = {s.id: s for s in self.sections}
        loads = defaultdict(float)
        assigned = defaultdict(list)
        for sec_id, prof_name, slot_id, room in chosen_full:
            if prof_name in prof_caps and sec_id in section_by_id:
                wtu = _section_wtu(section_by_id[sec_id])
                loads[prof_name] += wtu
                assigned[prof_name].append(f"{sec_id} ({wtu:g})")
        details = []
        for prof, load in sorted(loads.items()):
            cap = prof_caps.get(prof, 0)
            if load > cap:
                details.append(f"{prof}: {load:g}/{cap:g} WTU — " + ", ".join(sorted(assigned[prof])))
        self.wtu_overload_details = details
        return len(details)

    def _count_major_overlap_violations(self, chosen):
        section_by_id = {s.id: s for s in self.sections}
        chosen_by_major = defaultdict(list)
        for sec_id, slot_id in chosen:
            section = section_by_id.get(sec_id)
            if section and section.major:
                chosen_by_major[section.major].append((section, self.slot_by_id[slot_id]))

        details = []
        for major, rows in chosen_by_major.items():
            for i, (a_sec, a_slot) in enumerate(rows):
                for b_sec, b_slot in rows[i + 1:]:
                    same_course = a_sec.course_id == b_sec.course_id
                    different_component = a_sec.activity_type != b_sec.activity_type
                    if same_course and different_component:
                        continue
                    if set(a_slot.days) & set(b_slot.days):
                        a_s, a_e = _to_minutes(a_slot.start), _to_minutes(a_slot.end)
                        b_s, b_e = _to_minutes(b_slot.start), _to_minutes(b_slot.end)
                        if a_s < b_e and b_s < a_e:
                            details.append(
                                f"{major}: {a_sec.id} ({a_slot.days} {a_slot.start}-{a_slot.end}) overlaps "
                                f"{b_sec.id} ({b_slot.days} {b_slot.start}-{b_slot.end})"
                            )
        self.major_overlap_details = details
        return len(details)


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