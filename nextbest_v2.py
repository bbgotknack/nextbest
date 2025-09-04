
import hashlib
import binascii
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional, Tuple
import pandas as pd
import streamlit as st

st.set_page_config(layout="wide")

# --------------------------
# Database
# --------------------------
DB_PATH = os.getenv("MEDIA_TRACKER_DB_V2", "media_tracker_v2.db") # sets up a database file (.db) called "media_tracker"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def create_db():
    conn = get_conn()
    cur = conn.cursor()

    # USERS
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            u_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'user'))
        )
        """
    )
    
    # FRIENDS
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS friends (
            f_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(u_id)
        );
        """
    )

    # MEDIA TYPES (ex. movie, tv show, song...)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS media_types (
            m_id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_name TEXT NOT NULL UNIQUE
        );
        """
    )
    # Preload media types
    cur.executemany("INSERT OR IGNORE INTO media_types (type_name) VALUES (?)", [
        ("Movie",), ("TV Show",), ("YouTube Video",),
        ("Song",), ("Album",), ("Artist",), ("Podcast",), ("Book",)
    ])

    # MEDIA ITEMS (Ex. Interstellar)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS media_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            media_type_id INTEGER NOT NULL,
            creator TEXT,
            link TEXT,
            notes TEXT,
            suggested_by INTEGER NOT NULL,
            date TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'Medium' CHECK (priority IN ('High', 'Medium', 'Low')),
            rating INTEGER DEFAULT 5 CHECK (rating BETWEEN 1 AND 10),
            user_id INTEGER NOT NULL,
            UNIQUE(title, media_type_id, user_id),
            FOREIGN KEY (media_type_id) REFERENCES media_types(m_id),
            FOREIGN KEY (suggested_by) REFERENCES friends(f_id),
            FOREIGN KEY (user_id) REFERENCES users(u_id)
        );
        """
    )

    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_db()

# --------------------------
# User Management Functions
# --------------------------

def generate_salt(length=16):
    """Generate a new random salt."""
    return os.urandom(length).hex()  # hex string so it's safe to store in DB

def hash_password(password: str, salt: str) -> str:
    """Hash a password with a given salt using SHA-256."""
    # Combine password and salt, encode to bytes
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()

def create_user(username, password):
    conn = get_conn()
    cur = conn.cursor()

    # Check if any users exist
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]

    # First user is admin, others are normal users
    role = "admin" if user_count == 0 else "user"

    # Generate a 16-byte random salt
    salt = os.urandom(16)
    salt_hex = binascii.hexlify(salt).decode('utf-8')

    # Hash the password using PBKDF2
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',                     # hash algorithm
        password.encode('utf-8'),     # password as bytes
        salt,                          # raw salt bytes
        100_000                        # iterations
    )
    password_hash_hex = binascii.hexlify(password_hash).decode('utf-8')

    # Insert into DB
    cur.execute("""
        INSERT INTO users (username, password_hash, salt, role)
        VALUES (?, ?, ?, ?)
    """, (username, password_hash_hex, salt_hex, role))

    conn.commit()
    conn.close()
    return role

def verify_user(username: str, password: str) -> Optional[Tuple[int, str, str]]:
    """
    Verify username and password.
    Returns a tuple (u_id, username, role) if valid, else None.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT u_id, password_hash, salt, role FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()

    if row:
        u_id, stored_hash, stored_salt, role = row

        # Convert hex salt back to bytes
        salt_bytes = binascii.unhexlify(stored_salt)

        # Compute hash with PBKDF2 using stored salt
        entered_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt_bytes,
            100_000
        )
        entered_hash_hex = binascii.hexlify(entered_hash).decode('utf-8')

        if entered_hash_hex == stored_hash:
            return u_id, username, role  # ✅ login successful

    return None  # ❌ login failed

def change_password(username, new_password):
    if not new_password:
        st.error("Password cannot be empty")
        return

    conn = get_conn()
    cur = conn.cursor()

    # Generate a new 16-byte random salt
    salt = os.urandom(16)
    salt_hex = binascii.hexlify(salt).decode('utf-8')

    # Hash the new password using PBKDF2
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',                 # hash algorithm
        new_password.encode('utf-8'),  # password as bytes
        salt,                     # raw salt bytes
        100_000                   # iterations
    )
    password_hash_hex = binascii.hexlify(password_hash).decode('utf-8')

    # Update password_hash and salt in the DB
    cur.execute(
        "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
        (password_hash_hex, salt_hex, username)
    )

    conn.commit()
    conn.close()
    st.success(f"Password for '{username}' has been updated")

# --------------------------
# Web App Functions
# --------------------------

def list_friends(user_id):
    # Return all friends belonging to the given user
    conn = get_conn()
    df = conn.execute("SELECT f_id, name FROM friends WHERE user_id = ? ORDER BY f_id", (user_id,)).fetchall()
    conn.close()
    return df

def add_friend(name, user_id):
    # Add a new friend and automatically include the user_id
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO friends (name, user_id) VALUES (?, ?)", (name, user_id),)
    conn.commit()
    conn.close()

def delete_friend(f_id, user_id):
    conn = get_conn()
    conn.execute(
        "DELETE FROM friends WHERE f_id = ? AND user_id = ?",
        (f_id, user_id),
    )
    conn.commit()
    conn.close()

def update_friend(f_id, newName, user_id):
    conn = get_conn()
    conn.execute(
        "UPDATE friends SET name = ? WHERE f_id = ? AND user_id = ?",
        (newName, f_id, user_id),
    )
    conn.commit()
    conn.close()
        
def get_friendName(f_id, user_id):
    conn = get_conn()
    cur = conn.execute(
        "SELECT name FROM friends WHERE f_id = ? AND user_id = ?",
        (f_id, user_id),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

# --------------------------

def list_mediaTypes():
    conn = get_conn()
    df = conn.execute(
        "SELECT m_id, type_name FROM media_types ORDER by m_id").fetchall()
    conn.close()
    return df

def get_mediaTypeName(m_id):
    conn = get_conn()
    cur = conn.execute(
        "SELECT type_name FROM media_types WHERE m_id = ?",
        (m_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

# --------------------------

def list_mediaItems(user_id):
    # Returns all media items for the given user with readable media type and friend name.
    conn = get_conn()
    rows = conn.execute("""
        SELECT 
            m.item_id,
            m.title,
            mt.type_name AS media_type,
            m.creator,
            m.link,
            m.notes,
            f.name AS suggested_by,
            m.date,
            m.priority,
            m.rating
        FROM media_items m
        LEFT JOIN media_types mt ON m.media_type_id = mt.m_id
        LEFT JOIN friends f ON m.suggested_by = f.f_id
        WHERE m.user_id = ?
        ORDER BY m.item_id
    """, (user_id,)).fetchall()
    conn.close()
    return rows

def add_mediaItem(title, media_type_id, suggested_by, user_id, creator=None, link=None, notes=None, priority="Medium", rating=None):
    conn = get_conn()
    iso_date = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO media_items
        (title, media_type_id, creator, link, notes, suggested_by, date, priority, rating, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (title, media_type_id, creator, link, notes, suggested_by, iso_date, priority, rating, user_id),
    )
    conn.commit()
    conn.close()

def delete_mediaItem(item_id, user_id):
    conn = get_conn()
    conn.execute("DELETE FROM media_items WHERE item_id = ? AND user_id = ?", (item_id,user_id))
    conn.commit()
    conn.close()

def update_mediaItem(item_id, user_id, title=None, media_type_id=None, creator=None, link=None, notes=None, suggested_by=None, date=None, priority=None, rating=None):
    conn = get_conn()
    cur = conn.cursor()

    fields = []
    values = []

    if title is not None:
        fields.append("title = ?")
        values.append(title)
    if media_type_id is not None:
        fields.append("media_type_id = ?")
        values.append(media_type_id)
    if creator is not None:
        fields.append("creator = ?")
        values.append(creator)
    if link is not None:
        fields.append("link = ?")
        values.append(link)
    if notes is not None:
        fields.append("notes = ?")
        values.append(notes)
    if suggested_by is not None:
        fields.append("suggested_by = ?")
        values.append(suggested_by)
    if date is not None:
        fields.append("date = ?")
        values.append(date)
    if priority is not None:
        fields.append("priority = ?")
        values.append(priority)
    if rating is not None:
        fields.append("rating = ?")
        values.append(rating)

    if fields:  # only update if there’s something to change
        values.extend([item_id, user_id])
        sql = f"UPDATE media_items SET {', '.join(fields)} WHERE item_id = ? AND user_id = ?"
        cur.execute(sql, values)

    conn.commit()
    conn.close()

def import_media_from_csv(file_path, user_id):
    df = pd.read_csv(file_path)

    # Optional: Validate required columns exist
    required_columns = ["title", "media_type_id", "creator", "link", "notes", "suggested_by", "date", "priority", "rating"]
    if not all(col in df.columns for col in required_columns):
        raise ValueError(f"CSV must contain these columns: {required_columns}")

    # Insert each row into the database
    conn = get_conn()
    cur = conn.cursor()
    for _, row in df.iterrows():
        cur.execute(
            """INSERT OR IGNORE INTO media_items
               (title, media_type_id, creator, link, notes, suggested_by, date, priority, rating, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["title"],
                row["media_type_id"],
                row["creator"],
                row["link"],
                row["notes"],
                row["suggested_by"],
                row["date"],
                row["priority"],
                row["rating"],
                user_id  # <-- add user_id here
            )
        )
    conn.commit()
    conn.close()

# --------------------------

def get_media_by_friend(f_id, user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM media_items WHERE suggested_by = ? AND user_id = ? ORDER BY item_id",
        (f_id, user_id)
    ).fetchall()
    conn.close()
    return rows

def get_media_by_type(m_id, user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM media_items WHERE media_type_id = ? AND user_id = ? ORDER BY item_id",
        (m_id, user_id)
    ).fetchall()
    conn.close()
    return rows

def search_media(keyword, user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM media_items WHERE (title LIKE ? OR creator LIKE ?) AND user_id = ? ORDER BY item_id",
        (f"%{keyword}%", f"%{keyword}%", user_id)
    ).fetchall()
    conn.close()
    return rows

def get_media_by_friend_and_type(f_id, m_id, user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM media_items WHERE suggested_by = ? AND media_type_id = ? AND user_id = ? ORDER BY item_id",
        (f_id, m_id, user_id)
    ).fetchall()
    conn.close()
    return rows

# --------------------------
# Pages
# --------------------------

def page_addSuggestion():
    current_user = st.session_state.current_user_id

    st.title("NEXT BEST")

    friends = list_friends(current_user)
    friendNames = ["-- Select a Friend --"] + [f[1] for f in friends]
    mediaTypes = list_mediaTypes()
    mediaNames = ["-- Select a Media Type --"] + [m[1] for m in mediaTypes]
    priorityLevels = ["High", "Medium", "Low"]

    # -----------------------
    # Manual entry form
    # -----------------------
    st.subheader("What's the next best?")
    # Define default session state values
    if "new_suggestion" not in st.session_state:
        st.session_state.new_suggestion = {
            "title": "",
            "type": mediaNames[0] if mediaNames else "",
            "suggested_by": friendNames[0] if friendNames else "",
            "creator": "",
            "link": "",
            "notes": "",
            "priority": "Medium"
        }

    with st.form("Add a New Media Suggestion", clear_on_submit=True):
        title = st.text_input("Title", value=st.session_state.new_suggestion["title"])

        type_index = mediaNames.index(st.session_state.new_suggestion["type"]) if st.session_state.new_suggestion["type"] in mediaNames else 0
        type = st.selectbox("Media Type:", mediaNames, index=type_index)

        friend_index = friendNames.index(st.session_state.new_suggestion["suggested_by"]) if st.session_state.new_suggestion["suggested_by"] in friendNames else 0
        suggested_by = st.selectbox("Suggested by:", friendNames, index=friend_index)

        creator = st.text_input("Creator", value=st.session_state.new_suggestion["creator"])
        link = st.text_input("Link", value=st.session_state.new_suggestion["link"])
        notes = st.text_area("Notes", value=st.session_state.new_suggestion["notes"])

        priority_index = priorityLevels.index(st.session_state.new_suggestion["priority"]) if st.session_state.new_suggestion["priority"] in priorityLevels else 1
        priority = st.selectbox("Priority:", priorityLevels, index=priority_index)

        submitted = st.form_submit_button("Save")
        if submitted:
            if type != "-- Select a Media Type --" and suggested_by != "-- Select a Friend --":
                m_id = next(m[0] for m in mediaTypes if m[1] == type)
                f_id = next(f[0] for f in friends if f[1] == suggested_by)
                add_mediaItem(title=title, media_type_id=m_id, suggested_by=f_id,
            creator=creator, link=link, notes=notes, priority=priority,
            user_id=current_user)

                # Reset the session state after saving
                st.session_state.new_suggestion = {
                    "title": "",
                    "type": mediaNames[0] if mediaNames else "",
                    "suggested_by": friendNames[0] if friendNames else "",
                    "creator": "",
                    "link": "",
                    "notes": "",
                    "priority": "Medium"
                }

                st.success(f"Added '{title}' suggested by {suggested_by} with priority {priority}")
            else:
                st.error("Select both a media type and who suggested it")

    st.divider()
    st.subheader("New Friend")

    if "new_friend" not in st.session_state:
        st.session_state.new_friend = {"name": ""}

    with st.form("Add a New Friend", clear_on_submit=True):
        name = st.text_input("Name", value=st.session_state.new_friend["name"])
        submitted = st.form_submit_button("Add")
        if submitted:
            add_friend(name, current_user)
            st.session_state.new_friend = {"name": ""}
            st.success(f"Added '{name}'")
            st.rerun()

    # -----------------------
    # Rate a Suggestion
    # -----------------------
    st.subheader("Rate")

    # Collect all media items using the list function
    allmedia = list_mediaItems(st.session_state.current_user_id)

    if allmedia:
        # Add placeholder
        alltitles = [("none", "-- Select a Media Item --")] + [
            (m[0], f"{m[1]} {m[2]}") for m in allmedia
        ]

        # Keep the whole tuple (id, display_name)
        selected = st.selectbox(
            "Choose One",
            options=alltitles,
            format_func=lambda x: x[1]  # show display text
        )

        # Unpack only if not placeholder
        if selected[0] != "none":
            selected_id = selected[0]

            # Safely find the row (avoid StopIteration)
            selected_row = next((m for m in allmedia if m[0] == selected_id), None)

            if selected_row:
                with st.container():
                    st.write(f"**Title:** {selected_row[1]}")
                    st.write(f"**Media Type:** {selected_row[2]}")
                    st.write(f"**Suggested By:** {selected_row[6]}")

                # Enter Rating and Save Button
                rating = st.slider("Rating", min_value=1, max_value=10, value=5)

                if st.button("Save Rating"):
                    update_mediaItem(
                        item_id=selected_id,
                        user_id=st.session_state.current_user_id,
                        rating=rating
                    )
                    st.success("Rating saved!")

def page_viewSuggestions():
    current_user = st.session_state.current_user_id

    st.title("All Suggestions")

    # Fetch media items
    items = list_mediaItems(current_user)

    df = pd.DataFrame(items, columns=[
        "ID", "Title", "Media Type", "Creator", "Link", "Notes", "Suggested By", "Date", "Priority", "Rating"
    ])
    df.set_index("ID", inplace=True)

    # Convert 'Date' to datetime and format as YYYY-MM-DD
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

    filtered_df = df.copy() # start with the full database

    # -----------------------
    # Unrated Filter
    # -----------------------
    show_unrated_only = st.checkbox("Show Unrated Only")
    if show_unrated_only:
        filtered_df = filtered_df[filtered_df["Rating"].isna()]

    col1, col2 = st.columns(2)

    with col1:
        # -----------------------
        # Friend Filter
        # -----------------------
        friends = ["All"] + sorted(df["Suggested By"].unique())
        selected_friend = st.selectbox("Filter by Friend:", friends)

        if selected_friend != "All":
            filtered_df = filtered_df[filtered_df["Suggested By"] == selected_friend]
        
    with col2:
        # -----------------------
        # Media Type Filter
        # -----------------------
        types = ["All"] + sorted(df["Media Type"].unique())
        selected_type = st.selectbox("Filter by Media Type:", types)

        if selected_type != "All":
            filtered_df = filtered_df[filtered_df["Media Type"] == selected_type]

    filtered_df
    csv_data = df.reset_index().to_csv(index=False)
    st.download_button(
        label="Export Suggestions to CSV",
        data=csv_data,
        file_name="media_suggestions.csv",
        mime="text/csv"
    )

    with st.container():
        st.divider()
        st.subheader("Delete a Suggestion")

        if not df.empty:
            delete_id = st.selectbox(
                "Select a suggestion to delete",
                options=df.index,
                format_func=lambda x: f"{df.loc[x, 'Title']} ({df.loc[x, 'Media Type']})"
            )
            if st.button("Delete Suggestion"):
                delete_mediaItem(delete_id, st.session_state.current_user_id)
                st.success(f"Deleted suggestion: {df.loc[delete_id, 'Title']}")
                st.rerun() # refresh page to reflect deletion
        else:
            st.info("No suggestions available to delete")

def page_admin():
    
    # Ensure only admins can access
    if st.session_state.current_role != "admin":
        st.error("Access denied: Admins only")
        return

    st.title("All Users")

    # ----------------------
    # Fetch all users
    # ----------------------
    conn = get_conn()
    users = conn.execute("SELECT username, role FROM users ORDER BY u_id").fetchall()
    conn.close()

    if users:
        # Convert to DataFrame for nice table display
        import pandas as pd
        df = pd.DataFrame(users, columns=["Username", "Role"])
        st.dataframe(df)
    else:
        st.info("No users found.")

    # ----------------------
    # Add user
    # ----------------------
    st.divider()
    st.subheader("Add User")
    new_username = st.text_input("Username", key="new_user_username")
    new_password = st.text_input("Password", type="password", key="new_user_password")
    role_option = st.selectbox("Role", ["user", "admin"], key="new_user_role")

    if st.button("Add User"):
        if new_username and new_password:
            conn = get_conn()
            exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (new_username,)).fetchall()
            conn.close()
            if exists:
                st.error("Username already exists")
            else:
                conn = get_conn()
                cur = conn.cursor()

                salt = os.urandom(16)
                salt_hex = binascii.hexlify(salt).decode('utf-8')
                password_hash = hashlib.pbkdf2_hmac('sha256', new_password.encode('utf-8'), salt, 100_000)
                password_hash_hex = binascii.hexlify(password_hash).decode('utf-8')

                cur.execute(
                    "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
                    (new_username, password_hash_hex, salt_hex, role_option)
                )
                conn.commit()
                conn.close()

                st.success(f"User '{new_username}' added as '{role_option}'")
                st.rerun()
        else:
            st.error("Enter both username and password")

    # ----------------------
    # Delete user
    # ----------------------    
    st.divider()
    st.subheader("Delete User")
    if users:
        user_to_delete = st.selectbox(
            "Select a user to delete",
            options=[(u[0], u[1]) for u in users],
            format_func=lambda x: x[0]  # display username
        )
        if st.button("Delete User"):
            u_id, username = user_to_delete
            if username == st.session_state.current_username:
                st.error("You cannot delete your own account while logged in")
            else:
                conn = get_conn()
                conn.execute("DELETE FROM users WHERE u_id = ?", (u_id,))
                conn.commit()
                conn.close()
                st.success(f"Deleted user '{username}'")
                st.rerun()

    # ----------------------
    # Reset User Password
    # ----------------------
    st.divider()
    st.subheader("Change User Password")
    username_input = st.text_input("Username")
    new_password_input = st.text_input("New Password", type="password")
    if st.button("Update Password"):
        change_password(username_input, new_password_input)

def page_Leaderboard():
    st.title("Leaderboard")

    user_id = st.session_state.current_user_id
    
    # -----------------------
    # Best Suggestions
    # -----------------------
    st.subheader("Best Suggestions 🎖️")
    
    conn = get_conn()
    query2 = """
        SELECT
            f.name AS friend_name,
            ROUND(AVG(m.rating), 2) AS avg_rating
        FROM media_items m
        JOIN friends f ON m.suggested_by = f.f_id
        WHERE m.user_id = ?
        GROUP BY f.f_id, f.name
        ORDER BY avg_rating DESC
        LIMIT 3;
    """
    rows2 = conn.execute(query2, (user_id,)).fetchall()
    conn.close()

    if rows2:
        df2 = pd.DataFrame(rows2,columns=["Friend", "Average Rating"])
        df2.insert(0, "Rank", range(1, len(df2) + 1))
        st.dataframe(df2, hide_index=True)
    else:
        st.info("No Suggestions Yet")

    # -----------------------
    # Most Suggestions
    # -----------------------
    st.subheader("Most Suggestions 🏋️‍♀️")

    conn = get_conn()
    query1 = """
        SELECT f.name AS friend_name, COUNT(m.item_id) AS total_suggestions
        FROM media_items m
        JOIN friends f ON m.suggested_by = f.f_id
        WHERE m.user_id = ?
        GROUP BY f.f_id, f.name
        ORDER BY total_suggestions DESC
        LIMIT 3;
    """
    rows1 = conn.execute(query1, (user_id,)).fetchall()
    conn.close()

    if rows1:
        df1 = pd.DataFrame(rows1,columns=["Friend", "Total Suggestions"])
        # Add Rank Column
        df1.insert(0, "Rank", range(1, len(df1) + 1))
        # Print table and convert to records so there is no auto index column
        st.dataframe(df1, hide_index=True)
    else:
        st.info("No Suggestions Yet")

    # -----------------------
    # Neglected Friend
    # -----------------------
    st.subheader("Don't forget about this friend... ⏳")

    conn = get_conn()
    query3 = """
        SELECT f.name AS friend_name, MAX(m.date) AS latest_suggestion_date
        FROM media_items m
        JOIN friends f ON m.suggested_by = f.f_id
        WHERE m.user_id = ? AND m.rating IS NULL
        GROUP BY f.f_id, f.name
        ORDER BY latest_suggestion_date ASC
        LIMIT 1;
    """
    sad_friend = conn.execute(query3, (user_id,)).fetchone()

    if sad_friend:
        friend_name, date_str = sad_friend
        # Convert ISO date to YYYY-MM-DD
        date_obj = datetime.fromisoformat(date_str)
        formatted_date = date_obj.strftime("%Y-%m-%d")

        # Fetch the latest unrated suggestion for that friend
        latest_suggestion = conn.execute("""
            SELECT title, media_type_id
            FROM media_items
            WHERE user_id = ? AND suggested_by = (
                SELECT f_id FROM friends WHERE name = ?
            ) AND rating IS NULL
            ORDER BY date DESC
            LIMIT 1
        """, (user_id, friend_name)).fetchone()
    conn.close()
    
    if sad_friend:
        title, media_type_id = latest_suggestion
        media_type_name = get_mediaTypeName(media_type_id)
        with st.container():
            st.markdown(f"You haven't rated {friend_name}'s suggestion since {formatted_date}")
            st.markdown(f"**Latest Suggestion:** {title} ({media_type_name})")
    else:
        st.info("No Suggestions Yet")


# --------------------------
# App shell
# --------------------------

def main():
    # ----------------------
    # Initialize session state
    # ----------------------
    if "loggedin" not in st.session_state:
        st.session_state.loggedin = False
        st.session_state.current_user_id = None
        st.session_state.current_username = None
        st.session_state.current_role = None

    # ----------------------
    # Check number of users in DB
    # ----------------------
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    conn.close()

    # ----------------------
    # No users exist → Create Admin
    # ----------------------
    if user_count == 0:
        st.title("Create Admin Account")
        admin_username = st.text_input("Admin Username")
        admin_password = st.text_input("Admin Password", type="password")
        if st.button("Create Admin"):
            if admin_username and admin_password:
                role = create_user(admin_username, admin_password)
                st.success(f"Admin account '{admin_username}' created with role '{role}'. Please log in.")
                st.rerun()
            else:
                st.error("Enter both username and password")
        return  # Stop execution until admin is created

    # ----------------------
    # Users exist → Show login if not logged in
    # ----------------------
    if not st.session_state.loggedin:
        st.title("Login")
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password")
        if st.button("Login"):
            if username_input and password_input:
                user_info = verify_user(username_input, password_input)
                if user_info:
                    st.session_state.loggedin = True
                    st.session_state.current_user_id = user_info[0]
                    st.session_state.current_username = user_info[1]
                    st.session_state.current_role = user_info[2]
                    st.rerun()  # ✅ Forces the page to reload with logged in state
                else:
                    st.error("Invalid username or password")
            else:
                st.error("Enter both username and password")

        st.subheader("Create a New Account")
        new_username = st.text_input("New Username", key="new_user")
        new_password = st.text_input("New Password", type="password", key="new_pass")

        if st.button("Create Account"):
            if new_username and new_password:
                # Check if username already exists
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT * FROM users WHERE username = ?", (new_username,))
                existing_user = cur.fetchone()
                conn.close()

                if existing_user:
                    st.error("This username is already taken. Please choose another.")
                else:
                    create_user(new_username, new_password) # add new user to the database
                    user_info = verify_user(new_username, new_password)
                    if user_info:
                        st.session_state.loggedin = True
                        st.session_state.current_user_id = user_info[0]
                        st.session_state.current_username = user_info[1]
                        st.session_state.current_role = user_info[2]
                        st.rerun()
            else:
                st.error("Please enter both username and password")
        
        return  # Stop execution until login or account creation    

    # ----------------------
    # Logged in → show sidebar & pages
    # ----------------------
    else:
        # Logout button
        if st.sidebar.button("Logout"):
            st.session_state.loggedin = False
            st.session_state.current_user_id = None
            st.session_state.current_username = None
            st.session_state.current_role = None
            st.rerun()
        # ---------------------------
        # Change password button
        # ---------------------------
        if "show_change_pw" not in st.session_state:
            st.session_state.show_change_pw = False # by default the password section is hidden
        if "pw_success" not in st.session_state:
            st.session_state.pw_success = False  # tracks if success message should show
        if "pw_success_time" not in st.session_state:
            st.session_state.pw_success_time = 0      # tracks when success occurred

        if st.sidebar.button("Change Password"):
            st.session_state.show_change_pw = not st.session_state.show_change_pw
            st.session_state.pw_success = False  # hide success message when opening section

        # ---------------------------
        # Password change section
        # ---------------------------
        if st.session_state.show_change_pw: # if the password section is revealed...
            st.sidebar.subheader("Update Password")
            new_password = st.sidebar.text_input("New Password", type="password")
            if st.sidebar.button("Save New Password"):
                if new_password:
                    # Call your change_password function
                    change_password(st.session_state.current_username, new_password)
                    st.session_state.show_change_pw = False  # hide section after saving
                    st.session_state.pw_success = True      # show success message
                    st.session_state.pw_success_time = time.time()  # mark current time
                    st.rerun()
                else:
                    st.sidebar.error("Enter a new password")
        # Display success message in sidebar and auto-hide after 5 seconds
        if st.session_state.pw_success:
            elapsed = time.time() - st.session_state.pw_success_time
            if elapsed < 5:  # 5 seconds
                st.sidebar.success("Password updated. Write it down this time.")
            else:
                st.session_state.pw_success = False
                st.session_state.pw_success_time = 0
                st.rerun()  # remove message after timeout

        # Show side bar menu
        st.sidebar.title(f"User: {st.session_state.current_username}")
        pages = ["Home", "All Suggestions", "Leaderboard"]
        if st.session_state.current_role == "admin":
            pages.append("Admin Panel")
        page = st.sidebar.radio("Go to", pages)
    
    if page == "Home":
        page_addSuggestion()
    elif page == "All Suggestions":
        page_viewSuggestions()
    elif page == "Leaderboard":
        page_Leaderboard()
    elif page == "Admin Panel":
        page_admin()


if __name__ == "__main__":
    main()

