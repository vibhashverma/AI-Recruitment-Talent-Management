"""
auth.py
Milestone 4 — Authentication & role-based access.

Three roles share this platform:
- candidate: applies to jobs, tracks their own applications, takes AI interviews.
- recruiter: posts jobs, matches/shortlists candidates, manages the pipeline.
- admin: manages user accounts and views platform-wide stats.

Passwords are hashed with bcrypt before ever touching the database.
"""

import os

import bcrypt
import streamlit as st

import db as db_module

VALID_SIGNUP_ROLES = ["candidate", "recruiter"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def signup(name: str, email: str, password: str, role: str) -> dict:
    if role not in VALID_SIGNUP_ROLES:
        raise ValueError("Signup role must be 'candidate' or 'recruiter'.")
    if db_module.get_user_by_email(email):
        raise ValueError("An account with this email already exists. Try logging in instead.")
    password_hash = hash_password(password)
    return db_module.create_user(name, email, password_hash, role)


def login(email: str, password: str):
    user = db_module.get_user_by_email(email)
    if not user or not user.get("is_active", True):
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    user.pop("password_hash", None)
    return user


def ensure_admin_bootstrapped():
    """Create the admin account from .env on first run, if it doesn't exist yet."""
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        return
    if not db_module.get_user_by_email(admin_email):
        db_module.create_user("Administrator", admin_email, hash_password(admin_password), "admin")


def current_user():
    return st.session_state.get("user")


def logout():
    st.session_state.pop("user", None)
    st.rerun()


def render_auth_gate() -> bool:
    """Renders login/signup UI when no one is logged in. Returns True once authenticated."""
    if st.session_state.get("user"):
        return True

    st.title("🔐 Recruitment Copilot")
    st.caption("Sign in to continue, as a candidate or a recruiter.")

    tab_login, tab_signup = st.tabs(["Log In", "Sign Up"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In", type="primary", use_container_width=True)
        if submitted:
            if not email or not password:
                st.error("Enter both email and password.")
            else:
                user = login(email, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Invalid email or password, or this account has been deactivated.")

    with tab_signup:
        with st.form("signup_form"):
            name = st.text_input("Full Name")
            email_su = st.text_input("Email", key="signup_email")
            password_su = st.text_input("Password", type="password", key="signup_password")
            role = st.selectbox("I am a...", ["Candidate", "Recruiter"])
            submitted_su = st.form_submit_button("Create Account", type="primary", use_container_width=True)
        if submitted_su:
            if not name or not email_su or not password_su:
                st.error("All fields are required.")
            elif len(password_su) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                try:
                    user = signup(name, email_su, password_su, role.lower())
                    st.session_state.user = user
                    st.success("Account created — you're in.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Signup failed: {e}")

    return False
