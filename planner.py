"""
planner.py - the weekly study planner screen (Stage 3).
app.py calls planner.show(user) once a student is logged in.
"""
from datetime import datetime, time, timedelta, timezone

import streamlit as st

import database as db

# India time (UTC+5:30). Online servers often run on UTC, so we set this ourselves.
IST = timezone(timedelta(hours=5, minutes=30))
SHORT_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def today_ist():
    return datetime.now(IST).date()


def week_start_of(day):
    """The Monday of the week that contains `day`."""
    return day - timedelta(days=day.weekday())


def pretty(hhmm):
    """'17:00' -> '5:00 PM'"""
    return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")


def on_tick(user_id, block_id, week_start, key):
    """Runs the moment a checkbox is clicked: saves it and shows any XP earned."""
    today = today_ist()
    before = db.get_stats(user_id, today)["xp"]
    db.set_done(user_id, block_id, week_start, st.session_state[key], today.isoformat())
    after = db.get_stats(user_id, today)["xp"]
    if after > before:
        st.toast(f"+{after - before} XP ⭐")


def show_add_form(user_id, today_index):
    with st.expander("➕ Add a study block"):
        with st.form("add_block_form", clear_on_submit=True):
            subject = st.text_input("Subject", placeholder="Maths, Physics, Accountancy...")
            day_name = st.selectbox("Day", db.DAY_NAMES, index=today_index)
            col1, col2 = st.columns(2)
            start = col1.time_input("Starts", value=time(17, 0), step=900)
            end = col2.time_input("Ends", value=time(18, 0), step=900)
            added = st.form_submit_button("Add block")

        if added:
            ok, message = db.add_block(
                user_id,
                subject,
                db.DAY_NAMES.index(day_name),
                start.strftime("%H:%M"),
                end.strftime("%H:%M"),
            )
            if ok:
                st.success(f"Added {subject.strip()} on {day_name}.")
            else:
                st.error(message)


def show_day(user_id, day_index, blocks, week_start):
    day_blocks = [b for b in blocks if b["day_of_week"] == day_index]
    day_name = db.DAY_NAMES[day_index]

    if not day_blocks:
        st.write(f"Nothing planned for {day_name}. Open **Add a study block** above to plan something.")
        return

    done = sum(b["done"] for b in day_blocks)
    st.progress(done / len(day_blocks), text=f"{done} of {len(day_blocks)} done")

    for b in day_blocks:
        key = f"done_{b['block_id']}_{week_start}"
        left, right = st.columns([6, 1])
        left.checkbox(
            f"**{b['subject']}** ({pretty(b['start_time'])} to {pretty(b['end_time'])})",
            value=bool(b["done"]),
            key=key,
            on_change=on_tick,
            args=(user_id, b["block_id"], week_start, key),
        )
        if right.button("🗑️", key=f"del_{b['block_id']}", help="Delete this block"):
            db.delete_block(user_id, b["block_id"])
            st.rerun()


def show(user):
    user_id = user["user_id"]
    today = today_ist()
    week_start = week_start_of(today)
    week_end = week_start + timedelta(days=6)

    st.subheader("📅 Your week")
    st.caption(f"{week_start:%d %b} to {week_end:%d %b}. Blocks repeat every week; ticks reset each Monday.")

    show_add_form(user_id, today.weekday())

    # Read the blocks AFTER the form, so a new block shows up straight away.
    blocks = db.get_blocks(user_id, week_start.isoformat())
    total = len(blocks)
    done = sum(b["done"] for b in blocks)
    percent = round(100 * done / total) if total else 0

    st.progress(percent / 100, text=f"This week: {done} of {total} blocks done ({percent}%)")
    if total and done == total:
        st.success("Every block is done this week. Great work! 🎉")

    labels = []
    for i in range(7):
        label = f"{SHORT_DAYS[i]} {(week_start + timedelta(days=i)).day}"
        labels.append(f"📍 {label}" if i == today.weekday() else label)

    for i, tab in enumerate(st.tabs(labels)):
        with tab:
            show_day(user_id, i, blocks, week_start.isoformat())
