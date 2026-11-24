"""
database.py - everything that talks to the database lives in this file.

Stage 1: tables for classes and users.
Stage 2: sign-up and login logic.
"""
import hashlib
import hmac
import os
import re
import secrets
import threading
from datetime import date, timedelta

import bcrypt
import psycopg2
import streamlit as st
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool


# Which sections each class has. Edit this to match your school.
SECTIONS_BY_LEVEL = {
    10: ["A", "B", "C"],
    11: ["A", "B"],
    12: ["A", "B"],
}


# ---------------------------------------------------------------------------
# Small helpers that open the database, run one command, and close it again
# ---------------------------------------------------------------------------
def _database_url():
    """The address of your Neon database: from DATABASE_URL, or from secrets.toml."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            url = st.secrets["database"]["url"]
        except Exception:
            url = None
    if not url:
        raise RuntimeError(
            "No database set up. Add [database] url = \"...\" to .streamlit/secrets.toml"
        )
    return url


_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    """One shared set of open connections, so we don't reconnect for every query."""
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadedConnectionPool(1, 8, _database_url())
        return _pool


def _run(sql, params, fetch):
    sql = sql.replace("?", "%s")  # we write SQLite-style ?, Postgres wants %s
    for attempt in range(6):
        conn = _get_pool().getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or None)
                rows = cur.fetchall() if fetch else None
            conn.commit()
            _get_pool().putconn(conn)
            return rows
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            # The free database "sleeps" when idle and drops old connections.
            # Throw this one away and try again with a fresh one.
            _get_pool().putconn(conn, close=True)
            if attempt == 5:
                raise
        except Exception:
            conn.rollback()
            _get_pool().putconn(conn)
            raise


def query(sql, params=()):
    """Run a SELECT and return all matching rows."""
    return _run(sql, params, True)


def execute(sql, params=()):
    """Run an INSERT / UPDATE / DELETE and save the change."""
    _run(sql, params, False)


# ---------------------------------------------------------------------------
# Stage 1: create the tables
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS classes (
    class_id SERIAL PRIMARY KEY,
    level    INTEGER NOT NULL CHECK (level BETWEEN 10 AND 12),
    section  TEXT    NOT NULL,
    name     TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    user_id       SERIAL PRIMARY KEY,
    student_code  TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    email         TEXT UNIQUE,
    phone         TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    class_id      INTEGER NOT NULL REFERENCES classes(class_id),
    role          TEXT NOT NULL DEFAULT 'student'
                  CHECK (role IN ('student', 'monitor', 'teacher')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (email IS NOT NULL OR phone IS NOT NULL)
);

-- A study block repeats every week (e.g. Maths, Monday 5-6 PM)
CREATE TABLE IF NOT EXISTS study_blocks (
    block_id    SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(user_id),
    subject     TEXT    NOT NULL,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time  TEXT    NOT NULL,
    end_time    TEXT    NOT NULL,
    CHECK (end_time > start_time)
);

-- One row = "this block was completed in the week starting on this Monday"
CREATE TABLE IF NOT EXISTS block_done (
    block_id   INTEGER NOT NULL REFERENCES study_blocks(block_id) ON DELETE CASCADE,
    week_start TEXT    NOT NULL,
    done_on    TEXT,
    PRIMARY KEY (block_id, week_start)
);

-- Shared class timeline (is_personal = 1: only the creator sees it)
CREATE TABLE IF NOT EXISTS timeline_events (
    event_id    SERIAL PRIMARY KEY,
    class_id    INTEGER NOT NULL REFERENCES classes(class_id),
    created_by  INTEGER NOT NULL REFERENCES users(user_id),
    edited_by   INTEGER REFERENCES users(user_id),
    title       TEXT NOT NULL,
    category    TEXT NOT NULL CHECK (category IN ('exam', 'assignment', 'event')),
    due_date    TEXT NOT NULL,
    details     TEXT NOT NULL DEFAULT '',
    is_personal INTEGER NOT NULL DEFAULT 0 CHECK (is_personal IN (0, 1)),
    approved    INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1)),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ
);

-- Email verification codes (the code itself is never stored)
CREATE TABLE IF NOT EXISTS email_otps (
    otp_id     SERIAL PRIMARY KEY,
    email      TEXT        NOT NULL,
    code_hash  TEXT        NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts   INTEGER     NOT NULL DEFAULT 0,
    used       INTEGER     NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_ready = False
_init_lock = threading.Lock()


def init_db():
    """Create the tables and classes. Only does real work once per app start."""
    global _ready
    with _init_lock:
        if _ready:
            return
        execute(SCHEMA)

        names = []
        for level, sections in SECTIONS_BY_LEVEL.items():
            for section in sections:
                name = f"{level}-{section}"
                names.append(name)
                execute(
                    "INSERT INTO classes (level, section, name) VALUES (?, ?, ?) "
                    "ON CONFLICT (name) DO NOTHING",
                    (level, section, name),
                )

        # Remove classes that are no longer wanted, but only if nobody uses them.
        marks = ",".join("?" * len(names))  # one ? per class name
        execute(
            f"""DELETE FROM classes
                WHERE name NOT IN ({marks})
                  AND class_id NOT IN (SELECT class_id FROM users)
                  AND class_id NOT IN (SELECT class_id FROM timeline_events)""",
            names,
        )
        _ready = True


def get_classes():
    rows = query("SELECT class_id, name FROM classes ORDER BY level, section")
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Checking what the student typed
# ---------------------------------------------------------------------------
def clean_phone(raw):
    """Return a 10-digit Indian mobile number, or None if it isn't valid."""
    digits = re.sub(r"\D", "", raw or "")  # keep digits only
    if len(digits) == 12 and digits.startswith("91"):  # +91 98765 43210
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):  # 098765 43210
        digits = digits[1:]
    return digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def clean_email(raw):
    """Return the email in lowercase, or None if it doesn't look like an email."""
    email = (raw or "").strip().lower()
    return email if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) else None


# ---------------------------------------------------------------------------
# Stage 2: sign-up
# ---------------------------------------------------------------------------
def check_signup(name, email, phone, password, class_id):
    """
    Check everything a new student typed. Nothing is saved yet.
    Email AND phone are both required.
    Returns (clean_values, None) or (None, error_message).
    """
    name = (name or "").strip()
    if len(name) < 2:
        return None, "Enter your full name."

    if not (email or "").strip():
        return None, "Email is required."
    email_clean = clean_email(email)
    if email_clean is None:
        return None, "That email doesn't look right. Check it and try again."

    if not (phone or "").strip():
        return None, "Phone number is required."
    phone_clean = clean_phone(phone)
    if phone_clean is None:
        return None, "Enter a valid 10-digit mobile number."

    if len(password) < 8 or len(password.encode("utf-8")) > 72:
        return None, "Choose a password with at least 8 characters."

    if query("SELECT 1 FROM users WHERE email = ?", (email_clean,)):
        return None, "This email is already registered. Log in instead."
    if query("SELECT 1 FROM users WHERE phone = ?", (phone_clean,)):
        return None, "This phone number is already registered. Log in instead."
    if not query("SELECT 1 FROM classes WHERE class_id = ?", (class_id,)):
        return None, "Choose your class from the list."

    # Never keep the real password. Keep a scrambled version (a "hash").
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return {
        "name": name,
        "email": email_clean,
        "phone": phone_clean,
        "password_hash": password_hash,
        "class_id": class_id,
    }, None


def create_student(clean):
    """
    Save a student whose sign-up was checked (and whose email was verified).
    Returns (True, student_code) or (False, error_message).
    """
    class_rows = query(
        "SELECT level, section FROM classes WHERE class_id = ?", (clean["class_id"],)
    )
    if not class_rows:
        return False, "Choose your class from the list."
    level, section = class_rows[0]["level"], class_rows[0]["section"]

    # Build a unique ID such as S10A-0001 (S + class + section + running number).
    number = query(
        "SELECT COUNT(*) AS n FROM users WHERE class_id = ?", (clean["class_id"],)
    )[0]["n"] + 1
    student_code = f"S{level}{section}-{number:04d}"
    while query("SELECT 1 FROM users WHERE student_code = ?", (student_code,)):
        number += 1
        student_code = f"S{level}{section}-{number:04d}"

    try:
        execute(
            """INSERT INTO users
               (student_code, name, email, phone, password_hash, class_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (student_code, clean["name"], clean["email"], clean["phone"],
             clean["password_hash"], clean["class_id"]),
        )
    except psycopg2.IntegrityError:
        return False, "Could not create the account. If you already signed up, try logging in."

    return True, student_code


# ---------------------------------------------------------------------------
# Email verification codes (OTP = one-time password)
# ---------------------------------------------------------------------------
OTP_MINUTES = 10          # how long a code works
OTP_MAX_TRIES = 5         # wrong guesses allowed per code
OTP_MAX_PER_HOUR = 5      # codes that can be requested for one email per hour


def _hash_code(email, code):
    return hashlib.sha256(f"{email}:{code}".encode("utf-8")).hexdigest()


def create_otp(email):
    """Make a new 6-digit code for this email. Returns (True, code) or (False, error)."""
    execute("DELETE FROM email_otps WHERE created_at < now() - interval '1 day'")

    recent = query(
        "SELECT COUNT(*) AS n FROM email_otps "
        "WHERE email = ? AND created_at > now() - interval '1 hour'",
        (email,),
    )[0]["n"]
    if recent >= OTP_MAX_PER_HOUR:
        return False, "Too many codes were requested for this email. Try again in an hour."

    code = f"{secrets.randbelow(1_000_000):06d}"

    # Only the newest code should work.
    execute("UPDATE email_otps SET used = 1 WHERE email = ?", (email,))
    execute(
        "INSERT INTO email_otps (email, code_hash, expires_at) "
        "VALUES (?, ?, now() + make_interval(mins => ?))",
        (email, _hash_code(email, code), OTP_MINUTES),
    )
    return True, code


def check_otp(email, code):
    """Returns (True, "") if the code is right, else (False, error_message)."""
    rows = query(
        """SELECT otp_id, code_hash, attempts FROM email_otps
           WHERE email = ? AND used = 0 AND expires_at > now()
           ORDER BY otp_id DESC LIMIT 1""",
        (email,),
    )
    if not rows:
        return False, "That code has expired. Ask for a new one."
    row = rows[0]
    if row["attempts"] >= OTP_MAX_TRIES:
        return False, "Too many wrong tries. Ask for a new code."

    if not hmac.compare_digest(row["code_hash"], _hash_code(email, (code or "").strip())):
        execute("UPDATE email_otps SET attempts = attempts + 1 WHERE otp_id = ?", (row["otp_id"],))
        return False, "That code is wrong. Check your email and try again."

    execute("UPDATE email_otps SET used = 1 WHERE otp_id = ?", (row["otp_id"],))
    return True, ""


# ---------------------------------------------------------------------------
# Stage 2: login (Student ID, email or phone)
# ---------------------------------------------------------------------------
def login(identifier, password):
    """Return the user's details as a dict if the login is correct, else None."""
    ident = (identifier or "").strip()
    if not ident or not password:
        return None

    rows = query(
        """SELECT u.user_id, u.student_code, u.name, u.email, u.phone, u.role,
                  u.class_id, u.password_hash, c.name AS class_name
           FROM users u
           JOIN classes c ON c.class_id = u.class_id
           WHERE u.student_code = ? OR u.email = ? OR u.phone = ?""",
        (ident.upper(), ident.lower(), clean_phone(ident)),
    )
    if not rows:
        return None

    row = rows[0]
    try:
        correct = bcrypt.checkpw(
            password.encode("utf-8"), row["password_hash"].encode("utf-8")
        )
    except ValueError:
        correct = False
    if not correct:
        return None

    user = dict(row)
    del user["password_hash"]  # never pass the hash around
    return user


# ---------------------------------------------------------------------------
# Stage 3: weekly planner
# ---------------------------------------------------------------------------
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def add_block(user_id, subject, day_of_week, start_time, end_time):
    """
    Add a study block. Times are text like "17:00".
    Returns (True, "") on success, or (False, error_message).
    """
    subject = (subject or "").strip()
    if not subject:
        return False, "Enter a subject, like Maths or Physics."
    if len(subject) > 40:
        return False, "Keep the subject under 40 characters."
    if not 0 <= day_of_week <= 6:
        return False, "Choose a day of the week."
    if end_time <= start_time:
        return False, "The end time must be after the start time."

    execute(
        """INSERT INTO study_blocks (user_id, subject, day_of_week, start_time, end_time)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, subject, day_of_week, start_time, end_time),
    )
    return True, ""


def get_blocks(user_id, week_start):
    """All of a student's blocks, each with done = 1 or 0 for the given week."""
    rows = query(
        """SELECT b.block_id, b.subject, b.day_of_week, b.start_time, b.end_time,
                  CASE WHEN d.block_id IS NULL THEN 0 ELSE 1 END AS done
           FROM study_blocks b
           LEFT JOIN block_done d
                  ON d.block_id = b.block_id AND d.week_start = ?
           WHERE b.user_id = ?
           ORDER BY b.day_of_week, b.start_time""",
        (week_start, user_id),
    )
    return [dict(r) for r in rows]


def set_done(user_id, block_id, week_start, done, done_on):
    """Tick or untick a block for one week (only the block's owner can do this)."""
    owner = query(
        "SELECT 1 FROM study_blocks WHERE block_id = ? AND user_id = ?",
        (block_id, user_id),
    )
    if not owner:
        return
    if done:
        execute(
            "INSERT INTO block_done (block_id, week_start, done_on) "
            "VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (block_id, week_start, done_on),
        )
    else:
        execute(
            "DELETE FROM block_done WHERE block_id = ? AND week_start = ?",
            (block_id, week_start),
        )


def delete_block(user_id, block_id):
    """Delete a block (only its owner can). Its ticks are removed automatically."""
    execute(
        "DELETE FROM study_blocks WHERE block_id = ? AND user_id = ?",
        (block_id, user_id),
    )


# ---------------------------------------------------------------------------
# Stage 4: class timeline
# ---------------------------------------------------------------------------
CATEGORIES = ("exam", "assignment", "event")


def can_approve(role):
    """Teachers and class monitors can approve and edit any class entry."""
    return role in ("teacher", "monitor")


def may_change(user, event):
    """Can this user edit or delete this entry?"""
    if event["is_personal"]:
        return event["created_by"] == user["user_id"]
    in_my_class = event["class_id"] == user["class_id"]
    return in_my_class and (
        event["created_by"] == user["user_id"] or can_approve(user["role"])
    )


def _check_event_fields(title, category, due_date, details):
    """Returns ((title, category, due_date, details), None) or (None, error)."""
    title = (title or "").strip()
    details = (details or "").strip()
    if not title:
        return None, "Enter a title, like Physics unit test."
    if len(title) > 80:
        return None, "Keep the title under 80 characters."
    if category not in CATEGORIES:
        return None, "Choose a type: exam, assignment or event."
    if len(details) > 500:
        return None, "Keep the details under 500 characters."
    try:
        date.fromisoformat(due_date)
    except (TypeError, ValueError):
        return None, "Choose a valid date."
    return (title, category, due_date, details), None


def _get_event(event_id):
    rows = query("SELECT * FROM timeline_events WHERE event_id = ?", (event_id,))
    return dict(rows[0]) if rows else None


def add_event(user, title, category, due_date, details, personal):
    """Returns (True, message) on success or (False, error_message)."""
    clean, error = _check_event_fields(title, category, due_date, details)
    if error:
        return False, error
    title, category, due_date, details = clean

    # Personal entries, and entries from teachers/monitors, go live straight away.
    approved = 1 if (personal or can_approve(user["role"])) else 0
    execute(
        """INSERT INTO timeline_events
           (class_id, created_by, title, category, due_date, details,
            is_personal, approved)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user["class_id"], user["user_id"], title, category, due_date, details,
         1 if personal else 0, approved),
    )
    if personal:
        return True, "Added to your personal timeline."
    if approved:
        return True, "Added to the class timeline."
    return True, "Added. Your class will see it once a teacher or monitor approves it."


def get_events(user):
    """
    Everything this user is allowed to see:
    - class entries that are approved, or that they wrote, or (for teachers
      and monitors) any class entry, even if it is still waiting
    - their own personal entries
    """
    rows = query(
        """SELECT e.*, c.name AS creator_name, ed.name AS editor_name
           FROM timeline_events e
           JOIN users c ON c.user_id = e.created_by
           LEFT JOIN users ed ON ed.user_id = e.edited_by
           WHERE (e.is_personal = 0 AND e.class_id = %(class_id)s
                  AND (e.approved = 1 OR e.created_by = %(user_id)s OR %(approver)s = 1))
              OR (e.is_personal = 1 AND e.created_by = %(user_id)s)
           ORDER BY e.due_date, e.event_id""",
        {
            "class_id": user["class_id"],
            "user_id": user["user_id"],
            "approver": 1 if can_approve(user["role"]) else 0,
        },
    )
    return [dict(r) for r in rows]


def update_event(user, event_id, title, category, due_date, details):
    """Returns (True, message) on success or (False, error_message)."""
    event = _get_event(event_id)
    if event is None:
        return False, "That entry no longer exists."
    if not may_change(user, event):
        return False, "You can only edit your own entries."

    clean, error = _check_event_fields(title, category, due_date, details)
    if error:
        return False, error
    title, category, due_date, details = clean

    # A student's edit sends a class entry back to "waiting for approval".
    if event["is_personal"] or can_approve(user["role"]):
        approved = event["approved"]
    else:
        approved = 0

    execute(
        """UPDATE timeline_events
           SET title = ?, category = ?, due_date = ?, details = ?,
               edited_by = ?, updated_at = CURRENT_TIMESTAMP, approved = ?
           WHERE event_id = ?""",
        (title, category, due_date, details, user["user_id"], approved, event_id),
    )
    if approved:
        return True, "Saved."
    return True, "Saved. It will show to your class again once a teacher or monitor approves it."


def delete_event(user, event_id):
    event = _get_event(event_id)
    if event is None or not may_change(user, event):
        return False
    execute("DELETE FROM timeline_events WHERE event_id = ?", (event_id,))
    return True


def approve_event(user, event_id):
    event = _get_event(event_id)
    if (
        event is None
        or event["is_personal"]
        or event["class_id"] != user["class_id"]
        or not can_approve(user["role"])
    ):
        return False
    execute("UPDATE timeline_events SET approved = 1 WHERE event_id = ?", (event_id,))
    return True


# ---------------------------------------------------------------------------
# Stage 5: XP, streaks and the class leaderboard
# ---------------------------------------------------------------------------
XP_PER_BLOCK = 10
XP_BLOCKS_PER_DAY = 5  # only the first 5 blocks ticked each day earn XP


def compute_stats(day_counts, today):
    """
    day_counts: how many blocks were ticked on each day, e.g. {"2026-11-23": 3}
    today: a date. Returns XP, current streak, best streak and more.
    """
    day_set = {date.fromisoformat(d) for d in day_counts}

    xp = sum(min(n, XP_BLOCKS_PER_DAY) * XP_PER_BLOCK for n in day_counts.values())

    # Best streak: the longest run of days in a row.
    best = run = 0
    previous = None
    for day in sorted(day_set):
        run = run + 1 if previous and (day - previous).days == 1 else 1
        best = max(best, run)
        previous = day

    # Current streak: count back from today (or yesterday if nothing ticked yet today).
    cursor = today if today in day_set else today - timedelta(days=1)
    streak = 0
    while cursor in day_set:
        streak += 1
        cursor -= timedelta(days=1)

    week_start = today - timedelta(days=today.weekday())
    return {
        "xp": xp,
        "streak": streak,
        "best": best,
        "active_week": sum(1 for d in day_set if d >= week_start),
        "done_today": today in day_set,
        "ticks": sum(day_counts.values()),
    }


def get_stats(user_id, today):
    rows = query(
        """SELECT COALESCE(d.done_on, d.week_start) AS day, COUNT(*) AS n
           FROM block_done d
           JOIN study_blocks b ON b.block_id = d.block_id
           WHERE b.user_id = ?
           GROUP BY day""",
        (user_id,),
    )
    return compute_stats({r["day"]: r["n"] for r in rows}, today)


def get_leaderboard(class_id, today):
    """Everyone in the class (except teachers), best streak first."""
    rows = query(
        """SELECT u.user_id, u.name,
                  COALESCE(d.done_on, d.week_start) AS day,
                  COUNT(d.block_id) AS n
           FROM users u
           LEFT JOIN study_blocks b ON b.user_id = u.user_id
           LEFT JOIN block_done d ON d.block_id = b.block_id
           WHERE u.class_id = ? AND u.role != 'teacher'
           GROUP BY u.user_id, day""",
        (class_id,),
    )
    people = {}
    for r in rows:
        person = people.setdefault(
            r["user_id"], {"user_id": r["user_id"], "name": r["name"], "days": {}}
        )
        if r["day"] is not None:
            person["days"][r["day"]] = r["n"]

    board = []
    for person in people.values():
        stats = compute_stats(person["days"], today)
        stats["user_id"] = person["user_id"]
        stats["name"] = person["name"]
        board.append(stats)
    board.sort(key=lambda s: (s["streak"], s["active_week"], s["xp"]), reverse=True)
    return board
