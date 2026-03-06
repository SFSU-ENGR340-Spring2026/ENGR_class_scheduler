import sqlite3

def connect_db_classes(db_name="classes.db"):
    return sqlite3.connect(db_name)

