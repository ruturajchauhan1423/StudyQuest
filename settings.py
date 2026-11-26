"""
settings.py - edit your details and delete your account (Stage 8).
app.py calls settings.show(user) once a student is logged in.
"""
import streamlit as st

import database as db


def show_profile_form(user):
    st.markdown("**Your details**")
    st.caption(
        f"Your ID **{user['student_code']}** never changes, even if you change class. "
        f"Your email ({user['email']}) was verified, so to change it ask your teacher."
    )

    classes = db.get_classes()
    ids = [c["class_id"] for c in classes]
    can_change_class = user["role"] == "student"

    with st.form("profile_form"):
        name = st.text_input("Full name", value=user["name"])
        phone = st.text_input("Phone number (10 digits)", value=user["phone"] or "")
        class_choice = st.selectbox(
            "Your class",
            classes,
            index=ids.index(user["class_id"]),
            format_func=lambda c: c["name"],
            disabled=not can_change_class,
        )
        saved = st.form_submit_button("Save changes")

    if can_change_class:
        st.caption(
            "If you change class, the timeline entries you added to your old class "
            "are removed. Your study blocks and progress stay with you."
        )
    else:
        st.caption("Teachers and monitors can't change class here. Ask the admin.")

    if saved:
        ok, result = db.update_profile(user, name, phone, class_choice["class_id"])
        if ok:
            st.session_state.user = result  # use the updated details everywhere
            st.session_state.settings_flash = "Your details were saved."
            st.rerun()
        else:
            st.error(result)


def show_delete_section(user):
    st.markdown("**Delete my account**")
    st.caption(
        "This permanently deletes your profile, study blocks, XP and streak, "
        "and the timeline entries you added. It can't be undone. "
        "You can sign up again later and get a new Student ID."
    )
    with st.form("delete_form"):
        confirm_pw = st.text_input("Your password", type="password")
        sure = st.checkbox("I understand this can't be undone")
        delete_clicked = st.form_submit_button("Delete my account permanently")

    if delete_clicked:
        if not sure:
            st.error("Tick the box to confirm.")
        else:
            ok, error = db.delete_account(user, confirm_pw)
            if ok:
                st.session_state.user = None
                st.session_state.goodbye = True
                st.rerun()
            else:
                st.error(error)


def show(user):
    st.subheader("⚙️ Settings")

    message = st.session_state.pop("settings_flash", None)
    if message:
        st.success(message)

    show_profile_form(user)
    st.divider()
    show_delete_section(user)
