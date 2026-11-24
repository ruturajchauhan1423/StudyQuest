"""
rewards.py - XP, streaks, badges and the class leaderboard (Stage 5).
app.py calls rewards.show(user) once a student is logged in.
"""
import streamlit as st

import database as db
import planner

XP_PER_LEVEL = 100

# (icon, name, how to earn it, test that decides whether it is earned)
BADGES = [
    ("🌱", "First step", "Tick your first block", lambda s: s["ticks"] >= 1),
    ("🔥", "3-day streak", "Study 3 days in a row", lambda s: s["best"] >= 3),
    ("🚀", "7-day streak", "Study 7 days in a row", lambda s: s["best"] >= 7),
    ("⭐", "100 XP", "Earn 100 XP", lambda s: s["xp"] >= 100),
    ("🏅", "500 XP", "Earn 500 XP", lambda s: s["xp"] >= 500),
]


def short_name(full_name):
    """'Ruturaj Patel' -> 'Ruturaj P.' so classmates don't see full names."""
    parts = full_name.split()
    if len(parts) < 2:
        return full_name
    return f"{parts[0]} {parts[-1][0]}."


def show(user):
    today = planner.today_ist()
    stats = db.get_stats(user["user_id"], today)

    st.subheader("🏆 Your progress")

    level = stats["xp"] // XP_PER_LEVEL + 1
    into_level = stats["xp"] % XP_PER_LEVEL
    st.progress(
        into_level / XP_PER_LEVEL,
        text=f"Level {level}: {stats['xp']} XP ({XP_PER_LEVEL - into_level} XP to level {level + 1})",
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("🔥 Streak", f"{stats['streak']} days")
    col2.metric("Best streak", f"{stats['best']} days")
    col3.metric("Days this week", f"{stats['active_week']} / 7")

    if not stats["done_today"]:
        if stats["streak"] > 0:
            st.caption(f"Tick a block today to keep your {stats['streak']}-day streak alive.")
        else:
            st.caption("Tick a block today to start a streak.")

    st.markdown("**Badges**")
    for icon, name, how, earned in BADGES:
        if earned(stats):
            st.write(f"{icon} **{name}**")
        else:
            st.write(f"🔒 {name}: {how}")

    st.subheader("Class leaderboard")
    st.caption(
        "Ranked by streak, then by days studied this week. "
        "It rewards showing up, not marks."
    )

    board = db.get_leaderboard(user["class_id"], today)
    rows = []
    for rank, p in enumerate(board[:10], start=1):
        label = short_name(p["name"])
        if p["user_id"] == user["user_id"]:
            label += " (you)"
        rows.append(
            {
                "Rank": rank,
                "Name": label,
                "Streak": f"{p['streak']} days",
                "Days this week": f"{p['active_week']} / 7",
                "XP": p["xp"],
            }
        )
    st.dataframe(rows, hide_index=True)

    my_rank = next((i for i, p in enumerate(board, 1) if p["user_id"] == user["user_id"]), None)
    if my_rank:
        st.caption(f"You are #{my_rank} of {len(board)} in {user['class_name']}.")
