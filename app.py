import streamlit as st
import sqlite3
import hashlib
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import pandas as pd
import os
import random


# ------------------ DB Setup ------------------
if not os.path.exists("data"):
    os.makedirs("data")

conn = sqlite3.connect("data/tennis.db", check_same_thread=False)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL,
    approved INTEGER DEFAULT 0,
    reason TEXT,
    color TEXT,
    activation_code TEXT,
    activated INTEGER DEFAULT 0
)
''')

c.execute('''CREATE TABLE IF NOT EXISTS bookings (
                date TEXT,
                hour INTEGER,
                court INTEGER,
                username TEXT,
                locked INTEGER
            )''')
conn.commit()

# ------------------ Utility Functions ------------------
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def assign_color(username):
    colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'yellow', 'cyan']
    return colors[hash(username) % len(colors)]

# ------------------ Registration ------------------

def generate_activation_code():
    return ''.join(random.choices("0123456789", k=6))

def register():
    st.subheader("Registrieren")
    username = st.text_input("Benutzername")
    password = st.text_input("Passwort", type="password")
    reason = st.text_area("Begründung (optional)")
    if st.button("Registrieren"):
        if not username or not password:
            st.error("Benutzername und Passwort erforderlich.")
            return

        hashed = hash_pw(password)
        code = generate_activation_code()
        color = assign_color(username)

        try:
            c.execute(
                "INSERT INTO users (username, password, approved, reason, color, activation_code, activated) VALUES (?, ?, 0, ?, ?, ?, 0)",
                (username, hashed, reason, color, code)
            )
            conn.commit()
            st.success("Registrierung gespeichert. Bitte fordere deinen Aktivierungscode beim Admin an.")
        except sqlite3.IntegrityError:
            st.error("Benutzername existiert bereits.")


def activate_user():
    st.subheader("🔑 Benutzer aktivieren")
    username = st.text_input("Benutzername")
    code = st.text_input("Aktivierungscode", max_chars=6)

    if st.button("Aktivieren"):
        c.execute("SELECT activation_code FROM users WHERE username = ?", (username,))
        result = c.fetchone()

        if result and result[0] == code:
            # Direkt aktivieren UND freischalten
            c.execute("UPDATE users SET activated = 1, approved = 1 WHERE username = ?", (username,))
            conn.commit()
            st.success("✅ Aktivierung erfolgreich! Du kannst dich jetzt einloggen.")
        else:
            st.error("❌ Benutzername oder Aktivierungscode ist falsch.")



# ------------------ Admin ------------------
def admin():
    st.subheader("Admin-Bereich")
    pw = st.text_input("Admin-Passwort", type="password")
    if pw != st.secrets.get("admin_password"):
        st.stop()

# Nur Benutzer zeigen, die noch nicht aktiviert sind
    c.execute("SELECT username, reason, activation_code, activated FROM users WHERE approved = 0 AND activated = 0")
    pending = c.fetchall()

    for u in pending:
        username, reason, code, activated = u
        st.markdown(f"**{username}** — `{reason or 'Keine Begründung'}`")
        st.text(f"Aktivierungscode: {code} — {'✅ aktiviert' if activated else '❌ nicht aktiviert'}")


# ------------------ Login ------------------
def login():
    st.subheader("Login")
    username = st.text_input("Benutzername")
    password = st.text_input("Passwort", type="password")

    if st.button("Einloggen"):
        hashed = hash_pw(password)
        c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, hashed))
        user = c.fetchone()

        if not user:
            st.error("Ungültige Zugangsdaten.")
        elif user[2] == 0:
            st.warning("Dein Konto wurde noch nicht vom Admin freigegeben.")
        elif user[6] == 0:
            st.warning("Du musst deinen Aktivierungscode eingeben.")
        else:
            st.session_state.user = user[0]
            st.session_state.color = user[4]
            st.rerun()


# ------------------ Booking GUI ------------------
from datetime import date, timedelta

def booking():
    st.subheader(f"Willkommen {st.session_state.user}")

    # 📅 Date input
    date_today = st.date_input("Datum wählen", value=datetime.today())

    # 📌 Get current calendar week range (Mon–Sun)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())        # Monday
    week_end = week_start + timedelta(days=6)                   # Sunday

    if not (week_start <= date_today <= week_end):
        st.warning(f"Buchungen sind nur für diese Woche möglich ({week_start.strftime('%d.%m.%Y')} – {week_end.strftime('%d.%m.%Y')}).")
        return
    
    st.title("🎾 Tennisplatzbuchung – Tägliche Übersicht")

    user = st.session_state.get("user", None)
    if not user:
        st.error("Nicht eingeloggt.")
        return

    conn = sqlite3.connect("data/tennis.db", check_same_thread=False)
    c = conn.cursor()

    # Zeitbereich wählbar
    col1, col2 = st.columns(2)
    with col1:
        start_str = st.selectbox("Startzeit", [f"{h:02d}:00" for h in range(9, 21)], index=0)
    with col2:
        end_times = [f"{h:02d}:30" for h in range(10, 22)]
        end_str = st.selectbox("Endzeit", end_times, index=len(end_times) - 1)


    start_time = datetime.strptime(start_str, "%H:%M")
    end_time = datetime.strptime(end_str, "%H:%M")
    all_slots = [start_time + timedelta(minutes=30 * i) for i in range(48) if start_time + timedelta(minutes=30 * i) <= end_time]
    times = [t.strftime("%H:%M") for t in all_slots]
    courts = list(range(1, 10))

    tabs = st.tabs([f"Platz {i}" for i in courts])

    for i, tab in enumerate(tabs):
        court = i + 1
        with tab:
            st.markdown(f"### 📋 Platz {court}")
            for time in times:
                c.execute("SELECT username, locked FROM bookings WHERE date = ? AND hour = ? AND court = ?", (str(date_today), time, court))
                bookings = c.fetchall()
                usernames = [b[0] for b in bookings]
                locked = any(b[1] == 1 for b in bookings)
                first_user = usernames[0] if usernames else None

                col1, col2, col3 = st.columns([1.5, 2, 2.5])
                with col1:
                    st.write(f"🕒 {time}")
                with col2:
                    if usernames:
                        st.markdown("👥 " + ", ".join(usernames))
                    else:
                        st.markdown("👥 *(frei)*")

                with col3:
                    if user in usernames:
                        st.markdown("✅ Du bist gebucht")
                        if first_user == user:
                            if not locked:
                                if st.button("🔒", key=f"{time}-{court}-lock"):
                                    c.execute("UPDATE bookings SET locked = 1 WHERE date = ? AND hour = ? AND court = ?", (str(date_today), time, court))
                                    conn.commit()
                                    st.rerun()
                            else:
                                if st.button("🔓", key=f"{time}-{court}-unlock"):
                                    c.execute("UPDATE bookings SET locked = 0 WHERE date = ? AND hour = ? AND court = ?", (str(date_today), time, court))
                                    conn.commit()
                                    st.rerun()
                    elif locked:
                        st.markdown("🔒 Gesperrt")
                    elif len(usernames) >= 6:
                        st.markdown("❌ Voll")
                    else:
                        if st.button("Buchen", key=f"{time}-{court}-book"):
                            c.execute("INSERT INTO bookings (date, hour, court, username, locked) VALUES (?, ?, ?, ?, ?)",
                                      (str(date_today), time, court, user, 0))
                            conn.commit()
                            st.rerun()

    conn.close()

# ------------------ Overview page ------------------
def overview():
    import sqlite3
    from datetime import datetime, timedelta
    import streamlit as st

    st.markdown("## 📊 Platzübersicht")

    # 📅 Datumsauswahl
    selected_date = st.date_input("Datum auswählen", value=datetime.today().date())

    # Verbindung zur DB
    conn = sqlite3.connect("data/tennis.db", check_same_thread=False)
    c = conn.cursor()

    # Parameter
    courts = list(range(1, 10))
    start_time = datetime.strptime("07:00", "%H:%M")
    end_time = datetime.strptime("21:00", "%H:%M")
    time_slots = [start_time + timedelta(minutes=30 * i)
                  for i in range(int((end_time - start_time).seconds / 1800) + 1)]
    times = [t.strftime("%H:%M") for t in time_slots]

    # Buchungen abrufen
    bookings_map = {(t, court): [] for t in times for court in courts}
    locked_map = {}

    for time in times:
        for court in courts:
            c.execute("SELECT username, locked FROM bookings WHERE date = ? AND hour = ? AND court = ?",
                      (str(selected_date), time, court))
            entries = c.fetchall()
            bookings_map[(time, court)] = [u for u, _ in entries]
            locked_map[(time, court)] = any(l == 1 for _, l in entries)

    conn.close()

    # HTML-Tabelle aufbauen
    html = """
    <style>
        .schedule-table {
            border-collapse: collapse;
            width: 100%;
            table-layout: fixed;
            font-size: 12px;
        }
        .schedule-table th, .schedule-table td {
            border: 1px solid #888;
            text-align: center;
            padding: 3px;
            height: 30px;
            overflow: hidden;
        }
        .time-col {
            background-color: #004080;
            color: white;
            font-weight: bold;
        }
        .court-header {
            background-color: #002040;
            color: white;
            font-weight: bold;
        }
        .booked {
            background-color: red;
            color: white;
            font-weight: bold;
        }
        .locked {
            background-color: black;
            color: white;
        }
    </style>
    <table class="schedule-table">
        <tr>
            <th class="time-col">Zeit</th>
    """

    # Kopfzeile mit Platznummern
    for court in courts:
        html += f'<th class="court-header">{court}</th>'
    html += "</tr>"

    # Zeilen pro Zeit
    for t in times:
        html += f'<tr><td class="time-col">{t}</td>'
        for court in courts:
            users = bookings_map[(t, court)]
            locked = locked_map[(t, court)]
            if users:
                classes = "booked"
                if locked:
                    classes += " locked"
                label = "<br>".join(users[:2])  # max. 2 Namen anzeigen
            else:
                classes = ""
                label = ""
            html += f'<td class="{classes}">{label}</td>'
        html += "</tr>"

    html += "</table>"

    # HTML anzeigen
    st.markdown(html, unsafe_allow_html=True)


# ------------------ Main App ------------------
st.title("🎾 Tennisplatz-Buchung")
menu = ["Login", "Übersicht", "Registrieren", "Aktivieren", "Admin"]
choice = st.sidebar.selectbox("Navigation", menu)

if "user" in st.session_state:
    booking()
elif choice == "Registrieren":
    register()
elif choice == "Aktivieren":
    activate_user()
elif choice == "Admin":
    admin()
elif choice == "Übersicht":
    overview()
else:
    login()
