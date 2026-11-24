"""
mailer.py - sends the 6-digit verification code by email.

It reads your Gmail address and app password from Streamlit "secrets":
  - on your computer: the file .streamlit/secrets.toml
  - when published:   the app's Secrets settings
If no secrets are found, it runs in TEST MODE and prints the code in the
terminal instead of emailing it, so you can try everything before setting up Gmail.
"""
import smtplib
import ssl
from email.message import EmailMessage

import streamlit as st


def _gmail_settings():
    """Returns (address, app_password), or None if email isn't set up."""
    try:
        address = st.secrets["email"]["address"]
        password = st.secrets["email"]["app_password"].replace(" ", "")
        return address, password
    except Exception as error:
        # Shows WHY in the terminal (for example a typo in secrets.toml).
        print(f"(mailer) Could not read the email settings: {error!r}")
        return None


def send_otp(to_email, code):
    """
    Email the code. Returns (True, note) or (False, error_message).
    `note` is empty normally, or explains test mode.
    """
    settings = _gmail_settings()

    if settings is None:
        print(f"\n*** TEST MODE: email is not set up. The code for {to_email} is {code} ***\n")
        return True, "Test mode: email isn't set up yet, so the code was printed in the terminal."

    address, password = settings
    message = EmailMessage()
    message["Subject"] = "Your StudyQuest verification code"
    message["From"] = f"StudyQuest <{address}>"
    message["To"] = to_email
    message.set_content(
        f"Your StudyQuest code is {code}\n\n"
        "It works for 10 minutes. If you didn't try to sign up, ignore this email."
    )

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(address, password)
            server.send_message(message)
    except Exception as error:
        print("Email could not be sent:", error)  # shows in the terminal / app logs
        return False, "We couldn't send the email. Check the address and try again in a moment."

    return True, ""
