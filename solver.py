"""Class scheduler: load from DB, solve with OR-Tools, print schedule."""

import sqlite3
from collections import defaultdict
from ortools.sat.python import cp_model

DATABASE = "db_classes.db"


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
    def __init__(self, section_id, course_id):
        self.id = section_id
        self.course_id = course_id


class Slot:
    def __init__(self, slot_id, days, start, end):
        self.id = slot_id
        self.days = days
        self.start = start
        self.end = end


class Scheduler:
    def __init__(self, db_path=DATABASE):
        self.db_path = db_path
        self.sections = []
        self.professors = []
        self.slots = []
        self.slot_by_id = {}

    def load(self):
        #SQLite cursor to read from database
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        #store sections list from DB
        cur.execute("SELECT section_id, class_id FROM db_classes")
        self.sections = [Section(r[0], r[1]) for r in cur.fetchall()]

        #read faculty from DB
        cur.execute("SELECT faculty_name FROM faculty ORDER BY faculty_code")
        prof_names = [r[0] for r in cur.fetchall()]

        #store availability from DB
        cur.execute("""SELECT f.faculty_name, a.day_of_week, a.start_time, a.end_time
            FROM availability a JOIN faculty f ON a.faculty_code = f.faculty_code""")
        avail = defaultdict(lambda: defaultdict(list))
        for prof, day, start, end in cur.fetchall():
            avail[prof][day].append((start, end))

        #store can_teach from DB
        cur.execute("""SELECT f.faculty_name, fc.course_id
            FROM faculty_can_teach fc JOIN faculty f ON fc.faculty_code = f.faculty_code""")
        can_teach = defaultdict(set)
        for prof, course in cur.fetchall():
            can_teach[prof].add(course)

        #build professor objects with their availability and courses
        self.professors = [
            Professor(name, can_teach[name], dict(avail[name]))
            for name in prof_names
        ]

        #store time slots from DB
        cur.execute("SELECT slot_id, day_pattern, start_time, end_time FROM time_slots")
        self.slots = [Slot(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]
        self.slot_by_id = {s.id: s for s in self.slots}

        conn.close()

    def solve(self):
        #model contains all the restrictions we need to create a schedule
        model = cp_model.CpModel()

        #store section-prof-slot options and group them for constraints
        vars_all = {}
        vars_per_section = defaultdict(list)
        vars_per_prof_slot = defaultdict(list)

        #each section is traversed
        for sec in self.sections:
            #try to match professor with section if prof can teach it and is available
            for prof in self.professors:
                if sec.course_id not in prof.can_teach:
                    continue
                #compare each time slot for a section
                for slot in self.slots:
                    if not prof.is_available(slot.days, slot.start, slot.end):
                        #not available - continue checking
                        continue
                    #store section-prof-slot table for all possible options
                    key = (sec.id, prof.name, slot.id)
                    #add each option to the model, all set to 0 by default
                    var = model.NewBoolVar(str(key))
                    vars_all[key] = var
                    vars_per_section[sec.id].append(var)
                    vars_per_prof_slot[(prof.name, slot.id)].append(var)

        #each section gets exactly one slot
        for sec in self.sections:
            model.Add(sum(vars_per_section[sec.id]) == 1)

        #professor cannot teach two classes at same time
        for prof in self.professors:
            for slot in self.slots:
                model.Add(sum(vars_per_prof_slot[(prof.name, slot.id)]) <= 1)

        #solve and store result, compare to optimal and feasible options
        solver = cp_model.CpSolver()
        if solver.Solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

        #extract the chosen assignments from the solution
        result = []
        for (sec_id, prof_name, slot_id), var in vars_all.items():
            if solver.Value(var) == 1:
                slot = self.slot_by_id[slot_id]
                result.append((sec_id, slot.days, slot.start + "-" + slot.end, prof_name))
        return result


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

    #solution output
    print("Schedule:")
    for r in result:
        print(r[0], r[1], r[2], r[3])


if __name__ == "__main__":
    main()
