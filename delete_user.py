"""
delete_user.py - remove a student's account and all their data.
Use it when a student can't log in (for example, a forgotten password).

    python delete_user.py S12A-0003
"""
import sys

import database as db

if len(sys.argv) != 2:
    print("Usage: python delete_user.py STUDENT_ID")
    sys.exit(1)

code = sys.argv[1].upper()
rows = db.query("SELECT user_id, name FROM users WHERE student_code = ?", (code,))

if not rows:
    print(f"No user with the ID {code}.")
else:
    name = rows[0]["name"]
    answer = input(f"Delete {name} ({code}) and all their data? Type YES to confirm: ")
    if answer == "YES":
        db.remove_user(rows[0]["user_id"])
        print(f"{name} ({code}) has been deleted.")
    else:
        print("Cancelled. Nothing was deleted.")
