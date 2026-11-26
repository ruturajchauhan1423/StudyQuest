"""
pomodoro.py - the focus timer (Stage 8). app.py calls pomodoro.show().

The timer stores the clock time it will finish at, so the countdown stays
correct even when you click other things. A "fragment" refreshes just the
big numbers every second while the timer is running.
"""
import time

import streamlit as st

MODES = {
    "focus": ("🍅 Focus", 25),
    "short": ("☕ Short break", 5),
    "long": ("🌴 Long break", 15),
}


def reset_timer():
    """Stop the timer and set it back to the full time for the chosen mode."""
    st.session_state.pomo_end = None
    st.session_state.pomo_left = MODES[st.session_state.pomo_mode][1] * 60


def finish():
    """Runs when the countdown reaches zero: line up the next mode and a message."""
    if st.session_state.pomo_mode == "focus":
        st.session_state.pomo_done += 1
        # Every 4th focus session earns a long break.
        st.session_state.pomo_next = "long" if st.session_state.pomo_done % 4 == 0 else "short"
        st.session_state.pomo_flash = ("Focus session complete! Time for a break.", True)
    else:
        st.session_state.pomo_next = "focus"
        st.session_state.pomo_flash = ("Break over. Ready for another focus session?", False)


def countdown():
    """The big numbers and bar. Re-runs by itself every second while running."""
    end = st.session_state.pomo_end
    if end is None:
        left = st.session_state.pomo_left
    else:
        left = end - time.time()
        if left <= 0:
            finish()
            st.rerun()  # refresh the whole page so the next mode starts cleanly

    left = max(0, int(left + 0.999))  # round up, so 00:00 only shows at the very end
    total = MODES[st.session_state.pomo_mode][1] * 60
    st.markdown(
        '<div style="text-align:center; font-size:4.5rem; font-weight:600; '
        f"font-family:Fredoka,sans-serif\">{left // 60:02d}:{left % 60:02d}</div>",
        unsafe_allow_html=True,
    )
    st.progress(min(1.0, max(0.0, 1 - left / total)))


def show():
    ss = st.session_state
    ss.setdefault("pomo_mode", "focus")
    ss.setdefault("pomo_end", None)
    ss.setdefault("pomo_left", MODES["focus"][1] * 60)
    ss.setdefault("pomo_done", 0)

    # Apply the mode lined up by finish(). This must happen before the radio is drawn.
    next_mode = ss.pop("pomo_next", None)
    if next_mode:
        ss.pomo_mode = next_mode
        reset_timer()
    flash = ss.pop("pomo_flash", None)
    if flash:
        st.toast(flash[0], icon="🍅")
        if flash[1]:
            st.balloons()

    st.subheader("⏱️ Focus timer")
    st.caption(
        "Study hard, then rest. Every 4th focus session earns a long break. "
        "Keep this page open while the timer runs."
    )

    st.radio(
        "Mode",
        list(MODES),
        format_func=lambda m: f"{MODES[m][0]} {MODES[m][1]} min",
        key="pomo_mode",
        horizontal=True,
        on_change=reset_timer,
        label_visibility="collapsed",
    )

    running = ss.pomo_end is not None
    # Only tick every second while the timer is actually running.
    st.fragment(run_every=1 if running else None)(countdown)()

    col1, col2 = st.columns(2)
    if running:
        if col1.button("⏸️ Pause", use_container_width=True):
            ss.pomo_left = max(0, ss.pomo_end - time.time())
            ss.pomo_end = None
            st.rerun()
    else:
        if col1.button("▶️ Start", use_container_width=True):
            ss.pomo_end = time.time() + ss.pomo_left
            st.rerun()
    if col2.button("🔄 Reset", use_container_width=True):
        reset_timer()
        st.rerun()

    st.caption(f"Focus sessions finished this visit: {ss.pomo_done}")
