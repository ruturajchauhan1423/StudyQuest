"""
timeline.py - the shared class timeline screen (Stage 4).
app.py calls timeline.show(user) once a student is logged in.
"""
from datetime import date

import streamlit as st

import database as db
import planner

CATEGORY_LABELS = {"exam": "📝 Exam", "assignment": "📚 Assignment", "event": "🎉 Event"}


def flash(message):
    """Save a message to show after the page reloads, then reload."""
    st.session_state["timeline_flash"] = message
    st.rerun()


def when_text(due, today):
    days = (due - today).days
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days > 1:
        return f"in {days} days"
    if days == -1:
        return "yesterday"
    return f"{-days} days ago"


def event_form(key, event=None):
    """
    Draws the add form (event=None) or the edit form (event given).
    Returns the typed values as a dict when the button is pressed, else None.
    """
    editing = event is not None
    categories = list(CATEGORY_LABELS)

    with st.form(key, clear_on_submit=not editing):
        title = st.text_input(
            "Title",
            value=event["title"] if editing else "",
            placeholder="Physics unit test",
            key=f"{key}_title",
        )
        col1, col2 = st.columns(2)
        category = col1.selectbox(
            "Type",
            categories,
            index=categories.index(event["category"]) if editing else 0,
            format_func=CATEGORY_LABELS.get,
            key=f"{key}_category",
        )
        due = col2.date_input(
            "Date",
            value=date.fromisoformat(event["due_date"]) if editing else planner.today_ist(),
            key=f"{key}_date",
        )
        details = st.text_area(
            "Details (optional)",
            value=event["details"] if editing else "",
            key=f"{key}_details",
        )
        personal = False
        if not editing:
            personal = st.checkbox("Only visible to me", key=f"{key}_personal")
        pressed = st.form_submit_button("Save changes" if editing else "Add to timeline")

    if not pressed:
        return None
    values = {
        "title": title,
        "category": category,
        "due_date": due.isoformat(),
        "details": details,
    }
    if not editing:
        values["personal"] = personal
    return values


def show_entry(user, e, today):
    due = date.fromisoformat(e["due_date"])

    with st.container(border=True):
        st.markdown(f"**{CATEGORY_LABELS[e['category']]}: {e['title']}**")
        st.write(f"{due:%a, %d %b %Y} ({when_text(due, today)})")
        if e["details"]:
            st.write(e["details"])

        notes = [f"Added by {e['creator_name']}"]
        if e["editor_name"]:
            notes.append(f"last edited by {e['editor_name']}")
        if e["is_personal"]:
            notes.append("only you can see this")
        elif not e["approved"]:
            notes.append("⏳ waiting for approval")
        st.caption(", ".join(notes))

        can_edit = db.may_change(user, e)
        waiting = not e["is_personal"] and not e["approved"]
        can_ok = waiting and db.can_approve(user["role"])

        if can_ok or can_edit:
            col_a, col_b, _ = st.columns([1, 1, 2])
            if can_ok and col_a.button("✅ Approve", key=f"ok_{e['event_id']}"):
                if db.approve_event(user, e["event_id"]):
                    flash("Approved. Your class can see it now.")
            if can_edit and col_b.button("🗑️ Delete", key=f"rm_{e['event_id']}"):
                if db.delete_event(user, e["event_id"]):
                    flash("Deleted.")

        if can_edit:
            with st.expander("✏️ Edit"):
                values = event_form(f"edit_{e['event_id']}", e)
                if values:
                    ok, message = db.update_event(user, e["event_id"], **values)
                    if ok:
                        flash(message)
                    else:
                        st.error(message)


def show(user):
    today = planner.today_ist()

    st.subheader(f"🗓️ {user['class_name']} timeline")
    caption = "Exams, assignments and events. New class entries show to classmates once a teacher or monitor approves them."
    if db.can_approve(user["role"]):
        caption += f" You are a {user['role']}, so you can approve, edit and delete any entry."
    st.caption(caption)

    message = st.session_state.pop("timeline_flash", None)
    if message:
        st.success(message)

    with st.expander("➕ Add to timeline"):
        values = event_form("add_event")
        if values:
            ok, message = db.add_event(user, **values)
            if ok:
                flash(message)
            else:
                st.error(message)

    events = db.get_events(user)

    if db.can_approve(user["role"]):
        waiting = [e for e in events if not e["is_personal"] and not e["approved"]]
        if waiting:
            st.warning(f"{len(waiting)} entries are waiting for your approval.")

    if not st.checkbox("Show past entries"):
        events = [e for e in events if e["due_date"] >= today.isoformat()]

    if not events:
        st.write("Nothing coming up. Open **Add to timeline** to add an exam or assignment.")
        return

    for e in events:
        show_entry(user, e, today)
