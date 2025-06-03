import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
import sqlite3


DB_NAME = "time_entries.db"
ADMIN_PASSWORD = st.secrets["admin_password"]
total_quota = 25.0

# DB Setup
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_date TEXT,
                    description TEXT,
                    hours REAL
                )''')
    conn.commit()
    conn.close()

def insert_entry(entry_date, description, hours):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO entries (entry_date, description, hours) VALUES (?, ?, ?)",
              (entry_date, description, hours))
    conn.commit()
    conn.close()

def load_entries():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM entries ORDER BY entry_date DESC", conn)
    conn.close()
    return df

def delete_entry(entry_id):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()

def update_entry(entry_id, date, description, hours):
    conn = sqlite3.connect(DB_NAME)
    conn.execute(
        "UPDATE entries SET entry_date = ?, description = ?, hours = ? WHERE id = ?",
        (date, description, hours, entry_id)
    )
    conn.commit()
    conn.close()


init_db()
st.set_page_config(page_title="Stundenübersicht Dashboard", layout="wide")

# load entries
df = load_entries()
hours_used = df["hours"].sum() if not df.empty else 0
hours_remaining = max(0, total_quota - hours_used)
percent_used = (hours_used / total_quota) * 100 if total_quota else 0

# dashboard metrics
col1, col2, col3 = st.columns(3)
col1.metric("Stunden (insgesamt)", f"{total_quota:.1f}")
col2.metric("Genutzte Stunden", f"{hours_used:.1f}")
col3.metric("Verbleibende Stunden", f"{hours_remaining:.1f}")
st.progress(percent_used / 100.0)


# plots
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    # Pie chart
    fig = go.Figure(data=[go.Pie(
        labels=["genutzt", "verbleib."],
        values=[hours_used, hours_remaining],
        hole=0.5,  # makes it a donut
        textinfo='label+percent',
        marker=dict(colors=['#EF553B', '#00CC96'])
    )])
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with chart_col2:
    # ensure date time
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["date_formatted"] = df["entry_date"].dt.date
    # Compute start of each week
    if not df.empty:
        df["week"] = pd.to_datetime(df["entry_date"]).dt.to_period("W").apply(lambda r: r.start_time)
        weekly_usage = df.groupby("week")["hours"].sum().reset_index()

        start = df["week"].min()
        end = pd.Timestamp.today().normalize()
        full_weeks = pd.date_range(start=start, end=end, freq="W-MON")

        full_df = pd.DataFrame({"week": full_weeks})
        weekly_usage_full = full_df.merge(weekly_usage, on="week", how="left").fillna(0)
        weekly_usage_full["hours"] = weekly_usage_full["hours"].astype(float)

        st.subheader("Übersicht pro Woche")
        st.line_chart(weekly_usage_full.set_index("week"))
    else:
        st.subheader("Übersicht pro Woche)")
        st.info("No data yet. Add time entries to see usage trends.")

# display entries
st.subheader("Gebuchte Einträge")
st.data_editor(
    df[["date_formatted", "description", "hours"]],
    column_config={
        "date_formatted": st.column_config.Column(width="small", label="Datum"),
        "description": st.column_config.Column(width="large", label="Beschreibung"),
        "hours": st.column_config.Column(width="small", label="Stunden"),
    },
    use_container_width=True,
    disabled=True
)

auth_pw = st.text_input("🔒 Admin Password", type="password")
is_authorized = auth_pw == ADMIN_PASSWORD


# add new entry
if is_authorized:
    with st.expander("➕ Add Time Entry"):
        with st.form("entry_form"):
            entry_date = st.date_input("Date", value=date.today())
            description = st.text_input("Description")
            hours = st.number_input("Hours", min_value=0.25, step=0.25)
            submit = st.form_submit_button("Add Entry")
            if submit:
                insert_entry(str(entry_date), description, hours)
                st.success("Entry added.")
                st.rerun()

# edit/delete entries (admin only)
if is_authorized:
    st.subheader("📝 Edit or Delete Entries")
    editable_df = st.data_editor(
        df.copy(),
        use_container_width=True,
        num_rows="dynamic",
        key="editable_table"
    )

    df["id"] = df["id"].astype(str)
    editable_df["id"] = editable_df["id"].astype(str)

    deleted_ids = set(df["id"]) - set(editable_df["id"])
    added_rows = editable_df[editable_df["id"].isna()] if "id" in editable_df else pd.DataFrame()

    updated_rows = editable_df.merge(df, on="id", suffixes=("_new", "_old"))
    updated_rows = updated_rows[
        (updated_rows["entry_date_new"] != updated_rows["entry_date_old"]) |
        (updated_rows["description_new"] != updated_rows["description_old"]) |
        (updated_rows["hours_new"] != updated_rows["hours_old"])
    ]

    if st.button("💾 Save Changes"):
        for row in updated_rows.itertuples():
            update_entry(row.id, row.entry_date_new, row.description_new, row.hours_new)
        for row in added_rows.itertuples():
            insert_entry(row.entry_date, row.description, row.hours)
        for entry_id in deleted_ids:
            delete_entry(entry_id)
        st.success("Changes saved.")
        st.rerun()
