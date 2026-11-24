"""
set_role.py - change a person's role. Run it in the terminal, for example:

    python set_role.py S12A-0001 teacher

Roles: student, monitor, teacher
"""
import sys

import database as db

if len(sys.argv) != 3 or sys.argv[2] not in ("student", "monitor", "teacher"):
    print("Usage: python set_role.py STUDENT_ID ROLE   (ROLE: student, monitor or teacher)")
    sys.exit(1)

code, role = sys.argv[1].upper(), sys.argv[2]
rows = db.query("SELECT name FROM users WHERE student_code = ?", (code,))

if not rows:
    print(f"No user with the ID {code}.")
else:
    db.execute("UPDATE users SET role = ? WHERE student_code = ?", (role, code))
    print(f"{rows[0]['name']} ({code}) is now a {role}. Log out and back in to see the change.")
