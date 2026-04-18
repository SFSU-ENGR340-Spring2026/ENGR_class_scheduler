"""Class scheduler: load from DB, solve with OR-Tools, print schedule."""

import sqlite3
from collections import defaultdict
from ortools.sat.python import cp_model

DATABASE = "db_classes.db"


def display_professor(name):
    if name is None:
        return "N/A"
    s = str(name).strip()
    return s if s else "N/A"


class Professor:
    def __init__(self, name, can_teach, availability):
        self.name = name
        self.can_teach = can_teach
        self.availability = availability

    def is_available(self, days, start, end):
        for d in days:
            if d not in self.availability:
                return False
            if not any(s <= start and end <= e for s, e in self.availability[d]):
                return False
        return True


class Section:
    def __init__(self, section_id, course_id, activity_type="", slot_type="", units=None):
        self.id = section_id
        self.course_id = course_id
        self.activity_type = activity_type  # Lecture / Lab / Activity
        self.slot_type = slot_type  # e.g. 50min_lecture — must match time_slots.slot_type
        self.units = float(units) if units is not None else None


class Slot:
    def __init__(self, slot_id, days, start, end, slot_type=""):
        self.id = slot_id
        self.days = days
        self.start = start
        self.end = end
        self.slot_type = slot_type  # e.g. 50min_lecture, 75min_lecture


class Scheduler:
    def __init__(self, db_path=DATABASE):
        self.db_path = db_path      #path to the database
        self.sections = []          #blank list of Sections
        self.professors = []        #blank list of Professors
        self.slots = []             #blank list of Slots
        self.slot_by_id = {}        #blank dictionary of Slots with id

    #loading data from DB to Scheduler
    def load(self):
        #SQLite cursor to read from database
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        #store sections from DB (class_type + slot_type must match a time_slots row later)
        # DB column is `capacity`; used as credit units for 50min MWF vs MW/TR rules.
        cur.execute("SELECT section_id, class_id, class_type, slot_type, capacity FROM db_classes")
        self.sections = [
            Section(r[0], r[1], (r[2] or "").strip(), (r[3] or "").strip(), r[4])
            for r in cur.fetchall()
        ]

        #store all professors in temp var prof_names, used for next 2 operations
        cur.execute("SELECT faculty_name FROM faculty ORDER BY faculty_code")
        prof_names = [r[0] for r in cur.fetchall()]

        #store availability from DB
        cur.execute("""SELECT f.faculty_name, a.day_of_week, a.start_time, a.end_time
            FROM availability a JOIN faculty f ON a.faculty_code = f.faculty_code""")
        #avail is dict of lists(prof, day)
        avail = defaultdict(lambda: defaultdict(list))
        for prof, day, start, end in cur.fetchall():
            avail[prof][day].append((start, end))
            #avail holds all timeslots that are available for a professor

        #store can_teach from DB
        cur.execute("""SELECT f.faculty_name, fc.course_id
            FROM faculty_can_teach fc JOIN faculty f ON fc.faculty_code = f.faculty_code""")
        #can_teach is a set of can_teach classes
        can_teach = defaultdict(set)
        for prof, course in cur.fetchall():
            can_teach[prof].add(course)

        #Create Professor object for the time slots available and list of classes the one can teach
        self.professors = [
            Professor(name, can_teach[name], dict(avail[name]))
            for name in prof_names
        ]

        #store time slots from DB (slot_type links to db_classes.slot_type)
        cur.execute(
            "SELECT slot_id, day_pattern, start_time, end_time, slot_type FROM time_slots"
        )
        self.slots = [Slot(r[0], r[1], r[2], r[3], (r[4] or "").strip()) for r in cur.fetchall()]
        self.slot_by_id = {s.id: s for s in self.slots}

        conn.close()


    def solve(self):
        """
       Find a valid schedule. Idea: each "assignment" (section + professor + time slot)
       is a yes/no decision. We list all allowed assignments, add rules, then let the
       solver pick which ones to use.
        """
        # solving model: https://developers.google.com/optimization/scheduling/employee_scheduling
        # scheduling example: https://github.com/google/or-tools/blob/stable/examples/contrib/school_scheduling_sat.py

        model = cp_model.CpModel()

        # --- STEP 1: List every allowed assignment (section, professor, slot) ---
        # For each such triple we create one variable: 1 = "use this", 0 = "don't".
        # We also group them: by section (for "each section gets one slot") and
        # by (professor, slot) (for "professor can't do two classes in same slot").

        assignment_var = {}           # (section_id, prof_name, slot_id) -> variable
        vars_for_section = defaultdict(list)   # section_id -> [vars that assign this section]
        vars_for_prof_slot = defaultdict(list) # (prof_name, slot_id) -> [vars that use this prof+slot]

        for section in self.sections:
            for prof in self.professors:
                if section.course_id not in prof.can_teach:
                    continue
                for slot in self.slots:
                    # Section duration/type must match the slot row (50min vs 75min, etc.)
                    if section.slot_type != slot.slot_type:
                        continue
                    # 50-min: 3-unit → MWF; else MW or TR. 75-min: MW or TR only (policy).
                    if section.slot_type == "50min_lecture":
                        u = section.units
                        if u == 3.0:
                            if slot.days != "MWF":
                                continue
                        else:
                            if slot.days not in ("MW", "TR"):
                                continue
                    elif section.slot_type == "75min_lecture":
                        if slot.days not in ("MW", "TR"):
                            continue
                    if not prof.is_available(slot.days, slot.start, slot.end):
                        continue
                    # This assignment is allowed: create one 0/1 variable for it
                    key = (section.id, prof.name, slot.id)
                    var = model.NewBoolVar(str(key))
                    assignment_var[key] = var
                    vars_for_section[section.id].append(var)
                    vars_for_prof_slot[(prof.name, slot.id)].append(var)

# --- STEP 2: Rule "each section gets exactly one slot" ---
        problem_sections = []
        for section in self.sections:
            if not vars_for_section[section.id]:
                # If a section has 0 valid variables, it's impossible to schedule
                problem_sections.append(f"{section.course_id} (Sec {section.id})")
            else:
                model.Add(sum(vars_for_section[section.id]) == 1)
        
        # If any sections are unschedulable, stop the solver and send an error to the GUI
        if problem_sections:
            error_msg = f"Impossible to schedule: {', '.join(problem_sections)}. Check 'Can Teach', availability, and Slot Types."
            raise ValueError(error_msg)

        # --- STEP 3: Rule "professor cannot teach overlapping times" ---
        # Your DB may contain multiple `slot_id`s whose time intervals overlap
        # (for example, one slot could be 09:00-09:50 and another 09:30-12:15).
        # So we must block BOTH:
        #   3a) the same exact (professor, slot_id) being used twice
        #   3b) different slot_ids that overlap in clock time on at least one day.
        for prof in self.professors:
            for slot in self.slots:
                model.Add(sum(vars_for_prof_slot[(prof.name, slot.id)]) <= 1)

        # --- 3b) Different slot_ids that overlap in clock time ---
        # If two slots overlap and share at least one day letter (e.g. both contain 'F'),
        # then a professor cannot be assigned to both of them.
        def _to_minutes(hhmm):
            h, m = hhmm.split(":")
            return int(h) * 60 + int(m)

        slot_start_end = {s.id: (_to_minutes(s.start), _to_minutes(s.end)) for s in self.slots}
        slot_days_set = {s.id: set(s.days) for s in self.slots}  # slot_id -> {'M','W',...}

        overlap_pairs = []
        slot_list = list(self.slots)
        for i in range(len(slot_list)):
            a = slot_list[i]
            a_s, a_e = slot_start_end[a.id]
            a_days = slot_days_set[a.id]
            for j in range(i + 1, len(slot_list)):
                b = slot_list[j]
                # If they don't share any day letter, they cannot overlap for the professor.
                if not (a_days & slot_days_set[b.id]):
                    continue
                b_s, b_e = slot_start_end[b.id]
                # Overlap test on clock interval: [a_s, a_e) intersects [b_s, b_e)
                # (end is exclusive, so back-to-back slots like 09:00-09:30 and 09:30-10:00
                # are allowed).
                if a_s < b_e and b_s < a_e:
                    overlap_pairs.append((a.id, b.id))

        for prof in self.professors:
            for slot1_id, slot2_id in overlap_pairs:
                vars1 = vars_for_prof_slot[(prof.name, slot1_id)]
                vars2 = vars_for_prof_slot[(prof.name, slot2_id)]
                if not vars1 or not vars2:
                    continue
                # At most one of the two overlapping slots can be chosen for this professor.
                model.Add(sum(vars1) + sum(vars2) <= 1)

        # --- STEP 4: Prefer balanced week (minimize max−min meetings per weekday) ---
        slot_to_days = {s.id: set(s.days) for s in self.slots}  # "MW" -> {'M','W'}
        vars_on_day = defaultdict(list)  # 'M' -> [all vars that put a class on Monday]
        for (sec_id, prof_name, slot_id), var in assignment_var.items():
            for day in slot_to_days[slot_id]:
                vars_on_day[day].append(var)
        max_classes_any_day = model.NewIntVar(0, len(self.sections), "max_per_day")
        min_classes_any_day = model.NewIntVar(0, len(self.sections), "min_per_day")
        for day in "MTWRF":
            vlist = vars_on_day[day]
            if vlist:
                day_sum = sum(vlist)
                model.Add(max_classes_any_day >= day_sum)
                model.Add(min_classes_any_day <= day_sum)
            else:
                model.Add(max_classes_any_day >= 0)
                model.Add(min_classes_any_day <= 0)
        day_spread = model.NewIntVar(0, len(self.sections), "day_spread")
        model.Add(day_spread + min_classes_any_day == max_classes_any_day)
        model.Minimize(day_spread)

        # --- STEP 5: Run the solver ---
        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

        # --- STEP 6: Read back the solution ---
        # Every variable that is 1 in the solution is a chosen assignment.
        section_by_id = {s.id: s for s in self.sections}
        result = []
        for (sec_id, prof_name, slot_id), var in assignment_var.items():
            if solver.Value(var) == 1:
                slot = self.slot_by_id[slot_id]
                activity_type = section_by_id[sec_id].activity_type
                result.append((sec_id, activity_type, slot.days, slot.start + "-" + slot.end, display_professor(prof_name)))
        return result


def print_schedule(result):
    print("\nSchedule:")
    print(f"{'Section':<14}\t{'Type':<10}\t{'Days':<5}\t{'Time':<14}\tProfessor")
    for sec, typ, days, tim, prof in sorted(result, key=lambda r: (r[0], r[3])):
        print(f"{sec:<14}\t{typ:<10}\t{days:<5}\t{tim:<14}\t{display_professor(prof)}")


def main():
    #connect to database and load data
    sched = Scheduler()
    sched.load()

    print("Loading...", len(sched.sections), "sections,", len(sched.professors), "professors")
    #solving with OR-Tools here
    result = sched.solve()

    #no solution was found for the input - terminate
    if not result:
        print("No solution.")
        return

    print_schedule(result)


if __name__ == "__main__":
    main()