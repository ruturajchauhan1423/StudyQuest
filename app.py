"""
app.py - the screens students see. Run with:  streamlit run app.py
"""
import streamlit as st

import database as db
import mailer
import planner
import pomodoro
import rewards
import settings
import theme
import timeline

st.set_page_config(page_title="StudyQuest", page_icon="🎓")

db.init_db()  # makes sure the tables exist
theme.apply()  # colours, fonts and background

# st.session_state remembers who is logged in while the tab stays open.
if "user" not in st.session_state:
    st.session_state.user = None


def show_login_and_signup():
    theme.hero()

    if st.session_state.pop("goodbye", False):
        st.success("Your account and its data have been deleted.")

    tab_login, tab_signup = st.tabs(["🔑 Log in", "✨ Sign up"])

    # ----- Log in -----
    with tab_login:
        with st.form("login_form"):
            who = st.text_input("ID, email or phone")
            pw = st.text_input("Password", type="password")
            login_clicked = st.form_submit_button("Log in")

        if login_clicked:
            user = db.login(who, pw)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("ID, email, phone or password is wrong. Check and try again.")

    # ----- Sign up -----
    with tab_signup:
        show_signup()


def show_signup():
    """Sign up in two steps: fill in the form, then type the code sent by email."""
    done = st.session_state.get("signup_done")
    if done:
        if st.session_state.pop("celebrate", False):
            st.balloons()
        st.success(
            f"Email verified and account created! Your ID is **{done}**. "
            "Write it down, then open the Log in tab."
        )
        if st.button("Sign up another account"):
            del st.session_state["signup_done"]
            st.rerun()
        return

    pending = st.session_state.get("pending_signup")
    if pending:
        show_verify_step(pending)
        return

    kind = st.radio(
        "I am a", ["🎒 Student", "🧑‍🏫 Teacher"], horizontal=True, key="signup_role"
    )
    is_teacher = kind.endswith("Teacher")
    if is_teacher and not db.teacher_signup_enabled():
        st.info("Teacher sign-up isn't switched on yet. The admin needs to set a teacher access code.")
        return

    classes = db.get_classes()
    with st.form("signup_form"):
        name = st.text_input("Full name")
        class_choice = st.selectbox(
            "Class you teach" if is_teacher else "Your class",
            classes,
            format_func=lambda c: c["name"],
        )
        email = st.text_input("Email (we will send a code to verify it)")
        phone = st.text_input("Phone number (10 digits)")
        pw1 = st.text_input("Choose a password (8+ characters)", type="password")
        pw2 = st.text_input("Repeat the password", type="password")
        teacher_code = ""
        if is_teacher:
            teacher_code = st.text_input("Teacher access code", type="password")
        clicked = st.form_submit_button("Send verification code")

    if not clicked:
        return
    if pw1 != pw2:
        st.error("The two passwords don't match. Type them again.")
        return
    if is_teacher:
        ok, error = db.check_teacher_code(teacher_code)
        if not ok:
            st.error(error)
            return

    clean, error = db.check_signup(
        name, email, phone, pw1, class_choice["class_id"],
        role="teacher" if is_teacher else "student",
    )
    if error:
        st.error(error)
        return

    ok, result = db.create_otp(clean["email"])
    if not ok:
        st.error(result)
        return
    sent, note = mailer.send_otp(clean["email"], result)
    if not sent:
        st.error(note)
        return

    st.session_state.pending_signup = clean
    st.session_state.signup_note = note
    st.rerun()


def show_verify_step(pending):
    st.success(
        f"We sent a 6-digit code to **{pending['email']}**. "
        f"It works for {db.OTP_MINUTES} minutes. Check your spam folder too."
    )
    if st.session_state.get("signup_note"):
        st.info(st.session_state.signup_note)

    with st.form("verify_form"):
        code = st.text_input("Verification code", max_chars=6)
        verify_clicked = st.form_submit_button("Verify and create my account")

    if verify_clicked:
        ok, error = db.check_otp(pending["email"], code)
        if not ok:
            st.error(error)
        else:
            created, result = db.create_student(pending)
            if created:
                del st.session_state["pending_signup"]
                st.session_state.signup_done = result
                st.session_state.celebrate = True
                st.rerun()
            else:
                st.error(result)

    col1, col2 = st.columns(2)
    if col1.button("Send a new code"):
        ok, result = db.create_otp(pending["email"])
        if not ok:
            st.error(result)
        else:
            sent, note = mailer.send_otp(pending["email"], result)
            if sent:
                st.session_state.signup_note = note
                st.success("A new code is on its way.")
            else:
                st.error(note)
    if col2.button("Start over"):
        del st.session_state["pending_signup"]
        st.rerun()


def show_home():
    user = st.session_state.user
    first_name = user["name"].split()[0]

    st.title(f"Hey {first_name} 👋")

    col1, col2 = st.columns(2)
    col1.metric("Class", user["class_name"])
    col2.metric("Teacher ID" if user["role"] == "teacher" else "Student ID", user["student_code"])

    tab_plan, tab_time, tab_focus, tab_rewards, tab_settings = st.tabs(
        ["📅 Week", "🗓️ Timeline", "⏱️ Focus", "🏆 Progress", "⚙️ Settings"]
    )
    with tab_plan:
        planner.show(user)
    with tab_time:
        timeline.show(user)
    with tab_focus:
        pomodoro.show()
    with tab_rewards:
        rewards.show(user)
    with tab_settings:
        settings.show(user)

    if st.button("Log out"):
        st.session_state.user = None
        st.rerun()


if st.session_state.user:
    show_home()
else:
    show_login_and_signup()
