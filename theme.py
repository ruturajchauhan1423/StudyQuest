"""
theme.py - colours, fonts and the background. app.py calls theme.apply() once.

The look comes from a block of CSS kept inside this Python file.
To use your own photo as the background, put a file named background.jpg
(or .png / .webp, ideally under 500 KB) in the same folder as app.py,
then restart the app.
"""
import base64
import functools
import pathlib

import streamlit as st

FOLDER = pathlib.Path(__file__).parent

# Used when there is no photo: a night sky with a glow of sunrise.
GRADIENT = (
    "radial-gradient(70% 55% at 85% 105%, rgba(255, 122, 69, 0.55), transparent 70%),"
    "radial-gradient(55% 45% at 8% -5%, rgba(110, 86, 255, 0.50), transparent 70%),"
    "linear-gradient(165deg, #14123a 0%, #1f1c63 60%, #2b1f6e 100%)"
)

MIME_TYPES = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp"}


@functools.lru_cache(maxsize=1)
def background_image():
    """Your photo (darkened so text stays readable) if you added one, else the gradient."""
    for suffix, mime in MIME_TYPES.items():
        path = FOLDER / f"background{suffix}"
        if path.exists():
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            return (
                "linear-gradient(rgba(20, 18, 58, 0.72), rgba(20, 18, 58, 0.72)), "
                f'url("data:image/{mime};base64,{data}")'
            )
    return GRADIENT


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&display=swap');

.stApp {
    background-image: __BACKGROUND__;
    background-color: #14123a;
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
}
[data-testid="stHeader"] { background: transparent; }
.block-container, [data-testid="stMainBlockContainer"] { max-width: 860px; }

h1, h2, h3, button[data-baseweb="tab"] {
    font-family: 'Fredoka', 'Trebuchet MS', sans-serif;
}

/* Glass cards */
[data-testid="stForm"], [data-testid="stMetric"], [data-testid="stExpander"] {
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 18px;
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
}
[data-testid="stForm"] { padding: 1.4rem; }
[data-testid="stMetric"] { padding: 0.9rem 1.1rem; }

/* Rounded inputs */
[data-baseweb="input"] > div, [data-baseweb="textarea"], [data-baseweb="select"] > div {
    border-radius: 12px;
}

/* Everyday buttons: soft glass pills */
div.stButton > button {
    font-family: 'Fredoka', sans-serif;
    font-weight: 500;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.25);
}
div.stButton > button:hover { border-color: #ffc94d; color: #ffc94d; }

/* Main action buttons (log in, sign up, add): sunrise pills */
[data-testid="stFormSubmitButton"] > button {
    font-family: 'Fredoka', sans-serif;
    font-weight: 600;
    font-size: 1.05rem;
    border: 0;
    border-radius: 999px;
    padding: 0.55rem 1.8rem;
    background: linear-gradient(135deg, #ffc94d, #ff7a45);
    box-shadow: 0 6px 18px rgba(255, 122, 69, 0.35);
    transition: transform 0.12s ease, box-shadow 0.12s ease;
}
[data-testid="stFormSubmitButton"] > button p { color: #1a1440; }
[data-testid="stFormSubmitButton"] > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 24px rgba(255, 122, 69, 0.5);
}
</style>
"""

LOGIN_HEADER = """
<style>
.block-container, [data-testid="stMainBlockContainer"] { max-width: 520px; padding-top: 5vh; }
.hero { text-align: center; margin: 1vh 0 1.2rem; }
.hero .logo { font-size: 3.4rem; line-height: 1.1; }
.hero h1 { font-size: 3.1rem; font-weight: 700; margin: 0.2rem 0 0.4rem; padding: 0; color: #ffffff; }
.hero p { margin: 0; font-size: 1.12rem; color: rgba(244, 241, 255, 0.85); }
.hero p.small { margin-top: 0.3rem; font-size: 0.95rem; color: #ffc94d; }
</style>
<div class="hero">
  <div class="logo">🎓</div>
  <h1>StudyQuest</h1>
  <p>Plan your week. Build your streak. Climb your class.</p>
  <p class="small">For classes 10 to 12</p>
</div>
"""


def apply():
    """Paint the colours, fonts and background. Call once near the top of app.py."""
    st.markdown(CSS.replace("__BACKGROUND__", background_image()), unsafe_allow_html=True)


def hero():
    """The big StudyQuest header, with a narrower layout, for the login screen."""
    st.markdown(LOGIN_HEADER, unsafe_allow_html=True)
