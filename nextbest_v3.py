
import hashlib
import binascii
import os
import io
from datetime import datetime, timezone
from supabase import create_client, Client
import pandas as pd
import streamlit as st

# st.set_page_config(layout="wide")

# --------------------------
# Database
# --------------------------
SUPABASE_URL = "https://cjxxnpdnetklvycpkgja.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNqeHhucGRuZXRrbHZ5Y3BrZ2phIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTcwNjc4NjcsImV4cCI6MjA3MjY0Mzg2N30.vrhRpdaTM78pzH4pQrjIssYK0jPfrQMF5j0O35Zfzzo"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------------------------
# User Management Functions
# --------------------------

def generate_salt(length: int = 16) -> str:
    """Generate a random salt and return as hex string."""
    return binascii.hexlify(os.urandom(length)).decode("utf-8")

def hash_password(password: str, salt_hex: str, iterations: int = 100_000) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with given salt (hex)."""
    salt_bytes = binascii.unhexlify(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
    return binascii.hexlify(dk).decode("utf-8")

def create_user(username: str, password: str):

    try:
        # First user is admin, others are normal users
        res = supabase.table("users").select("u_id").execute()
        count = len(res.data)
        role = "admin" if count == 0 else "user"

        # Generate salt and hash password
        salt_hex = generate_salt()
        password_hash_hex = hash_password(password, salt_hex)

        # Insert into DB
        insert_res = supabase.table("users").insert({
            "username": username,
            "password_hash": password_hash_hex,
            "salt": salt_hex,
            "role": role
        }).execute()

        # Retrieve the newly inserted user's ID
        user_id = insert_res.data[0]["u_id"]
        return user_id, username, role

    except Exception as e:
        print(f"Exception creating user: {e}")
        return None

def verify_user(username: str, password: str):
    try:
        res = supabase.table("users").select("u_id", "username", "password_hash", "salt", "role").eq("username", username).execute()
        if res.data and len(res.data) > 0:
            row = res.data[0]
            if hash_password(password, row["salt"]) == row["password_hash"]:
                return row["u_id"], row["username"], row["role"]
        return None
    except Exception as e:
        print(f"Error verifying user: {e}")
        return None

def change_password(username: str, new_password: str):
    if not new_password:
        st.error("Password cannot be empty")
        return

    # Generate new salt and hashed password
    salt_hex = generate_salt()
    password_hash_hex = hash_password(new_password, salt_hex)

    # Update the database
    res = supabase.table("users").update({
        "password_hash": password_hash_hex, "salt": salt_hex
    }).eq("username", username).execute()

    # Return True if successful, False if error
    success = res.data is not None
    return success

# --------------------------
# Web App Functions
# --------------------------

def list_friends(user_id: int) -> list[dict]:
    """Return a list of dicts with friend info for a given user."""
    try:
        res = supabase.table("friends").select("f_id, name").eq("user_id", user_id).execute()
        if res.data:
            return res.data  # [{'f_id': 1, 'name': 'Alice'}, ...]
        return []
    except Exception as e:
        print(f"Error fetching friends: {e}")
        return []

def add_friend(name, user_id) -> bool:
    # Check if friend already exists for this user
    if not name or not name.strip():
        return False
    
    existing = supabase.table("friends").select("f_id").eq("user_id", user_id).eq("name", name).execute()
    if existing.data:
        return False
    
    # Add a new friend and automatically include the user_id
    res = supabase.table("friends").insert({
        "name": name,
        "user_id": user_id
    }).execute()

    # Return True if successful, False if error
    return res.data is not None

def delete_friend(name, user_id):
    try:
        res_delete = (
            supabase.table("friends")
            .delete()
            .eq("name", name)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(res_delete.data)
    except Exception as e:
        print(f"Error deleting friend: {e}")
        return False
            
# --------------------------

def list_mediaTypes() -> list[dict]:
    """Return a list of dicts with media types."""
    try:
        res = supabase.table("media_types").select("m_id, type_name").execute()
        if res.data:
            return res.data  # [{'m_id': 1, 'type_name': 'Movie'}, ...]
        return []
    except Exception as e:
        print(f"Error fetching media types: {e}")
        return []

def get_mediaTypeName(m_id):
    
    res = supabase.table("media_types").select("type_name").eq("m_id", m_id).execute()
    
    if res.data and len(res.data) > 0:
        return res.data[0]["type_name"]
    return None

# --------------------------

def list_mediaItems(user_id):
    res = supabase.table("media_items")\
        .select("item_id, title, media_type_id, creator, link, notes, suggested_by, date, priority, rating, user_id, media_types(type_name)")\
        .eq("user_id", user_id)\
        .execute()

    if res.data:
        # Flatten the nested dictionary for 'media_types'
        for row in res.data:
            if "media_types" in row and row["media_types"]:
                row["media_type"] = row["media_types"]["type_name"]
            else:
                row["media_type"] = None
            row.pop("media_types", None)
    return res.data if res.data else []
    
def add_mediaItem(title, m_id, suggested_by, user_id, creator=None, link=None, notes=None, priority="Medium", rating=None):
    
    iso_date = datetime.now(timezone.utc).isoformat()

    res = supabase.table("media_items").insert({
    "title": title,
    "media_type_id": m_id,
    "creator": creator,
    "link": link,
    "notes": notes,
    "suggested_by": suggested_by,
    "date": iso_date,
    "priority": priority,
    "rating": rating,
    "user_id": user_id
    }).execute()

    success = res.data is not None
    return success

def delete_mediaItem(item_id, user_id):
    try:
        item_id = int(item_id)
        res_delete = supabase.table("media_items").delete().eq("item_id", item_id).eq("user_id", user_id).execute()
        return bool(res_delete.data)
    except Exception as e:
        print(f"Error deleting media item: {e}")
        return False

def update_mediaItem(item_id, user_id, title=None, media_type_id=None, creator=None, link=None, notes=None, suggested_by=None, priority=None, rating=None):

    # Build dict of only the fields that are not None
    update_data = {}
    if title is not None:
        update_data["title"] = title
    if media_type_id is not None:
        update_data["media_type_id"] = media_type_id
    if creator is not None:
        update_data["creator"] = creator
    if link is not None:
        update_data["link"] = link
    if notes is not None:
        update_data["notes"] = notes
    if suggested_by is not None:
        update_data["suggested_by"] = suggested_by
    if priority is not None:
        update_data["priority"] = priority
    if rating is not None:
        update_data["rating"] = rating

    # Always update the date to now
    update_data["date"] = datetime.now(timezone.utc).isoformat()

    if not update_data:
        return False  # nothing to update
    
    res = supabase.table("media_items").update(update_data).eq("item_id", item_id).eq("user_id", user_id).execute()

    # Return True if successful, False if error
    success = res.data is not None
    return success

# --------------------------
# Pages
# --------------------------

def page_addSuggestion():
    current_user = st.session_state.current_user_id
    st.title("NEXT BEST")

    # -----------------------
    # Fetch friends and media types
    # -----------------------
    friends = list_friends(current_user) or []
    friendNames = ["-- Select a Friend --"] + [f["name"] for f in friends]

    mediaTypes = list_mediaTypes() or []
    mediaNames = ["-- Select a Media Type --"] + [m["type_name"] for m in mediaTypes]

    priorityLevels = ["High", "Medium", "Low"]

    # -----------------------
    # Initialize session state defaults
    # -----------------------
    if "new_suggestion" not in st.session_state:
        st.session_state.new_suggestion = {
            "title": "",
            "type": mediaNames[0],
            "suggested_by": friendNames[0],
            "creator": "",
            "link": "",
            "notes": "",
            "priority": "Medium"
        }

    # -----------------------
    # Form for adding a new media suggestion
    # -----------------------
    st.subheader("What's the next best?")
    with st.form("Add a New Media Suggestion", clear_on_submit=True):
        # Title input
        title = st.text_input("Title", value=st.session_state.new_suggestion.get("title", ""))

        # Media type selectbox
        type_default = st.session_state.new_suggestion.get("type", mediaNames[0] if mediaNames else "-- Select a Media Type --")
        type_index = mediaNames.index(type_default) if type_default in mediaNames else 0
        type_selected = st.selectbox("Media Type:", mediaNames, index=type_index)

        # Friend selectbox
        friend_default = st.session_state.new_suggestion.get("suggested_by", friendNames[0] if friendNames else "-- Select a Friend --")
        friend_index = friendNames.index(friend_default) if friend_default in friendNames else 0
        suggested_by_selected = st.selectbox("Suggested by:", friendNames, index=friend_index)

        # Optional fields
        creator = st.text_input("Creator", value=st.session_state.new_suggestion.get("creator", ""))
        link = st.text_input("Link", value=st.session_state.new_suggestion.get("link", ""))
        notes = st.text_area("Notes", value=st.session_state.new_suggestion.get("notes", ""))

        # Priority selectbox
        priority_default = st.session_state.new_suggestion.get("priority", "Medium")
        priority_index = priorityLevels.index(priority_default) if priority_default in priorityLevels else 1
        priority_selected = st.selectbox("Priority:", priorityLevels, index=priority_index)

        # Submit button
        submitted = st.form_submit_button("Save")

        if submitted:
            # Validation
            if type_selected == "-- Select a Media Type --" or suggested_by_selected == "-- Select a Friend --":
                st.error("Select both a media type and who suggested it")
            elif not title.strip():
                st.error("Title cannot be empty")
            else:
                try:
                    # Map selections to IDs
                    m_id = next((m["m_id"] for m in mediaTypes if m["type_name"] == type_selected), None)
                    f_id = next((f["f_id"] for f in friends if f["name"] == suggested_by_selected), None)

                    if m_id is None or f_id is None:
                        st.error("Could not resolve IDs for selected friend or media type")
                    else:
                        # Add the media item
                        success = add_mediaItem(
                            title=title,
                            m_id=m_id,  # Use correct parameter name
                            suggested_by=f_id,
                            user_id=current_user,
                            creator=creator,
                            link=link,
                            notes=notes,
                            priority=priority_selected
                        )

                        if success:
                            # Reset session state
                            st.session_state.new_suggestion = {
                                "title": "",
                                "type": mediaNames[0] if mediaNames else "-- Select a Media Type --",
                                "suggested_by": friendNames[0] if friendNames else "-- Select a Friend --",
                                "creator": "",
                                "link": "",
                                "notes": "",
                                "priority": "Medium"
                            }
                            st.success(f"Added '{title}' suggested by {suggested_by_selected} with priority {priority_selected}")
                        else:
                            st.error("Failed to add suggestion. Please try again.")

                except Exception as e:
                    st.error(f"Error adding suggestion: {e}")

    # -----------------------
    # Add a new Friend
    # -----------------------
    st.divider()
    st.subheader("New Friend")

    if "new_friend" not in st.session_state:
        st.session_state.new_friend = {"name": ""}

    with st.form("Add a New Friend", clear_on_submit=True):
        name = st.text_input("Name", value=st.session_state.new_friend["name"])
        submitted = st.form_submit_button("Add")
        if submitted:
            success = add_friend(name, current_user)
            if success:
                friendNames = ["-- Select a Friend --"] + [f["name"] for f in friends]
                st.session_state.new_friend = {"name": ""}
                st.success(f"Added '{name}'")
                st.rerun()
            else:
                st.error(f"Failed to add new friend. Name may already exist in the database.")

    # -----------------------
    # Rate a Suggestion
    # -----------------------
    st.divider()
    st.subheader("Give a Rating")
    
    # OPTIONAL: Filter by media type
    type_res = supabase.table("media_types").select("m_id","type_name").execute()
    type_names = [t["type_name"] for t in type_res.data] if type_res.data else []
    selected_type = st.selectbox("Optional: Filter by Media Type", ["All"] + type_names)

    if selected_type != "All":
        matching_type = next((t for t in type_res.data if t["type_name"] == selected_type), None)
        if matching_type:
            selected_type_id = matching_type["m_id"]
            # Filter options list by selected media type
            item_res = supabase.table("media_items").select("*").eq("media_type_id", selected_type_id).eq("user_id", current_user).execute()
            media_list = item_res.data if item_res.data else []
        else:
            st.warning("Selected media type not found")
    else:
        item_res = supabase.table("media_items").select("*").eq("user_id",current_user).execute()
        media_list = item_res.data if item_res.data else []
        # media_list is a list of dictionaries, each dictionary is for a unique media item #

    options_list = [m["title"] for m in media_list] if media_list else []
    # options_list is a list of titles taken from the list of dictionaries which was media_list

    if not options_list:
        st.info("No media items found for the selected type.")

    else:
        # Slider for Rating & Save Button
        with st.form("Rate Viewed Media"):
            selected_title = st.selectbox("Select an Item to Rate", options_list)

            media_data = next((m for m in media_list if m["title"] == selected_title), None)
            # media_data selects the dictionary for one media title
            if media_data:
                # Display key info
                st.markdown(f"**Title:** {media_data['title']}")
                friend_res = supabase.table("friends").select("f_id, name").execute()
                friend_map = {f["f_id"]: f["name"] for f in friend_res.data or []}
                st.markdown(f"**Suggested By:** {friend_map.get(media_data.get('suggested_by'), 'Unknown')}")
                st.markdown(f"**Creator:** {media_data.get('creator', 'N/A')}")
                type_map = {t["m_id"]: t["type_name"] for t in type_res.data or []}
                st.markdown(f"**Type:** {type_map.get(media_data.get('media_type_id'), 'Unknown')}")
                st.markdown(f"**Notes:** {media_data.get('notes', 'None')}")
                st.markdown(f"**Current Rating:** {media_data.get('rating', 'Not Rated')}")
                rate = st.slider(
                    "Select Rating:",
                    min_value=1,
                    max_value=10,
                    value=media_data.get("rating") if media_data.get("rating") is not None else 5
                )
                submitted = st.form_submit_button("Save Rating")
                if submitted:
                    update_res = supabase.table("media_items").update({"rating": rate}).eq("item_id", media_data["item_id"]).execute()
                    if update_res.data is not None:
                        st.success(f"Rating for '{media_data['title']}' updated to {rate}")
                    else:
                        st.error("Failed to update rating")

    # st.subheader("Change your Priorities")
    # item_res = supabase.table("media_items").select("*").eq("user_id", current_user).execute()
    # item_list = ["--- Pick One ---"] + item_res.data if item_res.data else []
    # selected_item = st.selectbox("To be deleted", item_list)
    # new_priority = st.selectbox("Priority", "High, "Medium", "Low")

def page_viewSuggestions():
    current_user = st.session_state.current_user_id

    st.title("All Suggestions")

    # Fetch media items & map to friend names and media type names for filtering
    all_user_items = list_mediaItems(current_user) # items is a list of dictionaries for each media item relating to the current user
    filtered_items = all_user_items

    # -----------------------
    # List Filters
    # -----------------------

    col1, col2 = st.columns(2)

    with col1:
        # ----- Friend Filter ------
        friend_res = supabase.table("friends").select("f_id, name").eq("user_id", current_user).execute()
        friend_map = {f["f_id"]: f["name"] for f in friend_res.data or []}

        friend_names = ["All"] + [friend_map[fid] for fid in sorted({item["suggested_by"] for item in filtered_items if item["suggested_by"]})] # filter by f_id, then map to name
        selected_f_name = st.selectbox("Filter by Friend:", friend_names)  

        if selected_f_name != "All":
            # Convert back to ID for filtering
            selected_friend_id = next((fid for fid, name in friend_map.items() if name == selected_f_name), None) # convert name to id to filter media items table
            filtered_items = [item for item in filtered_items if item["suggested_by"] == selected_friend_id]

        # ----- Media Type Filter -----

        media_type_res = supabase.table("media_types").select("m_id, type_name").execute()
        media_type_map = {m["m_id"]: m["type_name"] for m in media_type_res.data or []}

        media_type_names = ["All"] + sorted(
            {media_type_map[item["media_type_id"]] for item in filtered_items if item.get("media_type_id")},
            key=str.lower
        )
        selected_type_name = st.selectbox("Filter by Type:", media_type_names)

        if selected_type_name != "All":
            selected_type_id = next((mid for mid, name in media_type_map.items() if name == selected_type_name), None)
            filtered_items = [item for item in filtered_items if item["media_type_id"] == selected_type_id]
    
    with col2:
        # ----- Unrated Filter -----
        show_unrated_only = st.checkbox("Show Unrated Only")
        if show_unrated_only:
            filtered_items = [item for item in filtered_items if item["rating"] is None]

        # ----- Order by Priority -----
        sort = st.checkbox("Sort by High Proirity")
        if sort:
            priority_order = {"High": 0, "Medium": 1, "Low": 2}
            filtered_items = sorted(filtered_items, key=lambda x: priority_order.get(x.get("priority", "Medium"),99))
        # ----- Clear all Filters -----
        clear = st.button("Clear all Filters")
        if clear:
            filtered_items = all_user_items
    
    # -----------------------
    # Display List
    # -----------------------
    for item in filtered_items:
        with st.container():
            st.subheader(item["title"])
            col1, col2 = st.columns(2)

            # Format the date as YYYY-MM-DD
            raw_date = item.get('date', None)
            if raw_date:
                try:
                    formatted_date = datetime.fromisoformat(raw_date).date()
                except ValueError:
                    formatted_date = raw_date
            else:
                formatted_date = "Unknown"

            # Display information
            friend_name = friend_map.get(item["suggested_by"], "Unknown")
            media_type_name = media_type_map.get(item["media_type_id"], "Unknown")

            with col1:
                st.markdown(f"**Suggested by:** {friend_name} on {formatted_date}")
                st.markdown(f"**Priority:** {item.get('priority', 'N/A')}")
                st.markdown(f"**Rating:** {item.get('rating', 'Not Rated')}")

            with col2:
                st.markdown(f"**Media Type:** {media_type_name}")
                st.markdown(f"**Creator:** {item.get('creator', 'N/A')}")
                st.markdown(f"**Notes:** {item.get('notes', 'None')}")

            # -----------------------------
            # Edit button and popup form
            # -----------------------------
            if st.button("Edit", key=f"edit_{item['item_id']}"):
                st.session_state["editing_item"] = item["item_id"]

            # Show form if this item is being edited
            if st.session_state.get("editing_item") == item["item_id"]:
                with st.form(f"edit_form_{item['item_id']}"):
                    new_title = st.text_input("Title", value=item.get("title", ""))
                    new_creator = st.text_input("Creator", value=item.get("creator", ""))
                    new_notes = st.text_area("Notes", value=item.get("notes", ""))
                    new_priority = st.selectbox(
                        "Priority",
                        ["High", "Medium", "Low"],
                        index=["High", "Medium", "Low"].index(item.get("priority", "Medium"))
                    )
                    current_friend_id = item.get("suggested_by")
                    current_friend_name = friend_map.get(current_friend_id, "-- Select Friend --")
                    friend_options = list(friend_map.values())
                    default_index = friend_options.index(current_friend_name) if current_friend_name in friend_options else 0
                    new_friend_name = st.selectbox(
                        "Suggested by",
                        friend_options,
                        index=default_index
                    )
                    
                    submitted = st.form_submit_button("Save Changes")

                    if submitted:
                        # Map friend name back to f_id
                        # Map friend name back to f_id
                        new_friend_id = next((fid for fid, name in friend_map.items() if name == new_friend_name), None)
                        new_media_type_id = None

                        # Call your existing update function
                        success = update_mediaItem(
                            item_id=item["item_id"],
                            user_id=current_user,
                            title=new_title,
                            creator=new_creator,
                            notes=new_notes,
                            priority=new_priority,
                            suggested_by=new_friend_id,
                            media_type_id=new_media_type_id
                        )

                        if success:
                            st.success("Media item updated successfully!")
                            del st.session_state["editing_item"]  # close form
                            st.rerun()  # refresh to show updated data
                        else:
                            st.error("Failed to update media item.")
                            del st.session_state["editing_item"]  # close form
                    
                    # Delete button
                    if st.form_submit_button("Delete Item"):
                        res = supabase.table("media_items").delete().eq("item_id", item["item_id"]).eq("user_id", current_user).execute()
                        if res.data is not None:
                            st.success("Media item deleted successfully!")
                            del st.session_state["editing_item"]  # close form
                            st.rerun()  # refresh the page to remove item
                        else:
                            st.error("Failed to delete media item.")



# -----------------------------
# CSV Export
# -----------------------------

    if filtered_items:
        df_export = pd.DataFrame(filtered_items)

        # Map friend names and media type names for readability
        df_export["Friend"] = df_export["suggested_by"].map(friend_map)
        df_export["Media Type"] = df_export["media_type_id"].map(media_type_map)

        # Optional: reorder / select columns you want
        cols_order = ["title", "Friend", "Media Type", "creator", "priority", "rating", "notes", "date"]
        df_export = df_export[[c for c in cols_order if c in df_export.columns]]

        csv_data = df_export.to_csv(index=False)

        st.download_button(
            label="Export Suggestions to CSV",
            data=csv_data,
            file_name="media_suggestions.csv",
            mime="text/csv"
        )
    else:
        st.info("No suggestions to export.")

def page_admin():
    
    # Ensure only admins can access
    if st.session_state.current_role != "admin":
        st.error("Access denied: Admins only")

    st.title("All Users")

    # ----------------------
    # Display list of all users
    # ----------------------
    users = supabase.table("users").select("u_id, username, role").execute()
      
    if not users.data:
        st.info("No users found")
    else:
        df = pd.DataFrame(users.data)
        df.rename(columns={
            "u_id": "ID",
            "username": "Username",
            "role": "Role"
        }, inplace=True)
        df.set_index("ID", inplace=True)
        st.dataframe(df)
        
    # ----------------------
    # Add user form
    # ----------------------
    st.divider()
    st.subheader("Add User")
    new_username = st.text_input("Username", key="new_user_username")
    new_password = st.text_input("Password", type="password", key="new_user_password")

    if st.button("Add User"):
        if new_username and new_password:
            # Check if the username already exists
            exists = supabase.table("users").select("username").eq("username", new_username).execute()
            
            if exists.data: # if there is data that exists matching the entered username
                st.error("Username already exists")
                return
            
            # If the username is not taken, add the username to the users table
            else:
                res = create_user(new_username, new_password)

                if res:
                    st.success(f"User '{new_username}' added.")
                    st.rerun()
                else:
                    st.error(f"Error adding user")
        else:
            st.error("Enter both username and password")


    # ----------------------
    # Delete user
    # ----------------------    
    st.divider()
    st.subheader("Delete User")
    if users and users.data:
        user_options=[(u["username"], u["u_id"]) for u in users.data]
        user_to_delete = st.selectbox(
            "Select a user to delete",
            options=user_options,
            format_func=lambda x: x[0]  # display username in dropdown
        )
        if st.button("Delete User"):
            username, u_id = user_to_delete

            if username == st.session_state.current_username:
                st.error("You cannot delete your own account while logged in")
            else:
                confirm = st.checkbox(f"Confirm deletion of '{username}' and all associated data?")
                if confirm:
                    res = supabase.table("users").delete().eq("u_id", u_id).execute()
                    
                    success = res.data is not None
                    if success:
                        st.success(f"Deleted user '{username}' and all their friends/media items")
                        st.rerun()
                    else:
                        st.error("Error deleting user")
                else:
                    st.warning("Check the confirmation box to delete user")
    else:
        st.info("No users available to delete")

    # ----------------------
    # Reset User Password
    # ----------------------
    st.divider()
    st.subheader("Change User Password")

    username_input = None

    if users and users.data:
        user_options=[(u["username"], u["u_id"]) for u in users.data]

        with st.form("Update Password"):
            # Select User
            username_input = st.selectbox(
                "Select User",
                options=user_options,
                format_func=lambda x: x[0]  # display username in dropdown
            )
            # Select new password
            new_password_input = st.text_input("New Password", type="password")

            # Submit button
            submitted = st.form_submit_button("Update Password")

            if submitted:
                selected_username = username_input[0]
                success = change_password(selected_username, new_password_input)
                if success:
                    st.success(f"Password for '{username_input}' has been updated")
                    st.rerun()
                else:
                    st.error("Failed to update password")
    # -----------------------
    # Export Database (Join to "users" table on "username")
    # -----------------------
    st.divider()
    st.subheader("Export All Tables")

    try:
        # 1) Fetch all tables
        users_res = supabase.table("users").select("*").execute()
        friends_res = supabase.table("friends").select("*").execute()
        media_types_res = supabase.table("media_types").select("*").execute()
        media_items_res = supabase.table("media_items").select("*").execute()

        # 2) Convert to DataFrames
        df_users = pd.DataFrame(users_res.data or [])
        df_friends = pd.DataFrame(friends_res.data or [])
        df_media_types = pd.DataFrame(media_types_res.data or [])
        df_media_items = pd.DataFrame(media_items_res.data or [])

        # 3) Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_users.to_excel(writer, sheet_name="Users", index=False)
            df_friends.to_excel(writer, sheet_name="Friends", index=False)
            df_media_types.to_excel(writer, sheet_name="Media_Types", index=False)
            df_media_items.to_excel(writer, sheet_name="Media_Items", index=False)
        # Move pointer to the start
        output.seek(0)
        processed_data = output.getvalue()

        # 4) Download button
        st.download_button(
            label="Download All Tables as Excel",
            data=processed_data,
            file_name="supabase_full_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"Error exporting database: {e}")        

def page_Leaderboard():
    st.title("Friend Leaderboard")

    user_id = st.session_state.current_user_id
    
    # -----------------------
    # Best Suggestions
    # -----------------------
    st.subheader("🎖️ Best Ratings")

    # Call the Supabase RPC function
    res1 = supabase.rpc(
        "top_friends_avg_rating",
        {"user_id_param": st.session_state.current_user_id}
    ).execute()

    if res1.data:
        df1 = pd.DataFrame(res1.data)
        df1.rename(columns={
            "friend_name": "Friend",
            "avg_rating": "Average Rating"
        }, inplace=True)

        # Sort by Average Rating descending
        df1.sort_values(by="Average Rating", ascending=False, inplace=True)

        # Reset index so Rank goes 1..N in sorted order
        df1.insert(0, "Rank", range(1, len(df1) + 1))

        st.dataframe(df1, hide_index=True)
    else:
        st.info("No Suggestions Yet")


    # -----------------------
    # Most Suggestions
    # -----------------------
    st.subheader("🏋️‍♀️ Most Suggestions")

    # Call Supabase RPC function
    res2 = supabase.rpc(
        "top_friends_total_suggestions",
        {"user_id_param": st.session_state.current_user_id}
    ).execute()

    if res2.data is not None:
        df2 = pd.DataFrame(res2.data)
        df2.rename(columns={
            "friend_name": "Friend",
            "total_suggestions": "Total Suggestions"
        }, inplace=True)

        # Sort by Total Suggestions descending
        df2.sort_values(by="Total Suggestions", ascending=False, inplace=True)
        df2.reset_index(drop=True, inplace=True)

        df2.insert(0, "Rank", range(1, len(df2) + 1))
        st.dataframe(df2, hide_index=True)
    else:
        st.info("No Suggestions Yet")

    # -----------------------
    # Neglected Friend
    # -----------------------
    st.subheader("⏳ Don't forget about this friend...")

    res3 = supabase.rpc(
        "top_neglected_friend",
        {"user_id_param": st.session_state.current_user_id}
    ).execute()

    if res3.data and len(res3.data) > 0:
        # Only 1 row expected
        row = res3.data[0]
        friend_name = row["friend_name"]
        date_str = row["latest_suggestion_date"]
        try:
            date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))                                              
            formatted_date = date_obj.strftime("%Y-%m-%d")
        except Exception:
            formatted_date = str(date_str)

        title = row["title"]
        media_type_id = row["media_type_id"]
        media_type_name = get_mediaTypeName(media_type_id)

        with st.container():
            st.markdown(f"You haven't rated a suggestion from **{friend_name}** since **{formatted_date}**")
            st.markdown(f"**Latest Suggestion:** {title} ({media_type_name})")
    else:
        st.info("No Suggestions Yet")

    st.title("Media Leaderboard")
    # -----------------------
    # Hall of Fame
    # -----------------------
    st.subheader("🏆 Hall of Fame")
    st.markdown("Most highly rated suggestions of all time")

    type_names_res = supabase.table("media_types").select("type_name").execute()
    type_names_selector = ["--- Select a Media Type ---"] + [t["type_name"] for t in type_names_res.data]

    friends_res = supabase.table("friends").select("f_id, name").execute()
    friend_map = {f["f_id"]: f["name"] for f in (friends_res.data or [])}

    with st.form("Hall of Fame"):
        selected_media_type = st.selectbox("Select Media Type:", type_names_selector)
        refresh = st.form_submit_button("Refresh List")

        if refresh:
            if selected_media_type == "--- Select a Media Type ---":
                st.warning("Please select a media type")
            else:
                # fetch media type ID's to match to selected media type name
                selected_media_ID_res = supabase.table("media_types").select("m_id").eq("type_name", selected_media_type).execute()
                if selected_media_ID_res.data and len(selected_media_ID_res.data) > 0:
                    selected_media_ID = selected_media_ID_res.data[0]["m_id"]
                else:
                    st.warning("Selected media type not found")
                    selected_media_ID = None
                # fetch media items relating to the media type ID
                topmedia_res = supabase.table("media_items").select("*").eq("media_type_id", selected_media_ID).execute()

                if topmedia_res.data:
                    # Sort by rating descending
                    topmedia_sorted = sorted(topmedia_res.data, key=lambda x: x.get("rating") or 0, reverse=True)

                    # Display results
                    for i, item in enumerate(topmedia_sorted[:5], start=1):
                        suggested_by_name = friend_map.get(item.get("suggested_by"), "Unknown")
                        st.markdown(
                            f"**{i}. {item['title']}**  \n"
                            f"Rating: {item.get('rating', 'N/A')}  \n"
                            f"Suggested by: {suggested_by_name}  \n"
                        )

def page_user_options():
    current_user = st.session_state.current_user_id
    st.title("User Options")

    # ---------------------------
    # Change Password
    # ---------------------------
    st.subheader("Update Password")
    new_password = st.text_input("New Password", type="password")
    if st.button("Save New Password"):
        if new_password:
            # Call your change_password function
            change_password(st.session_state.current_username, new_password)
            st.rerun()
        else:
            st.error("Enter a new password")
            
    # ---------------------------
    # Remove a Friend
    # ---------------------------
    st.subheader("Remove Friend")
    friends = list_friends(current_user) or []
    friendNames = ["-- Select a Friend --"] + [f["name"] for f in friends]

    selected_friend = st.selectbox("Select Friend", friendNames)

    if selected_friend != "-- Select a Friend --":
        if st.button("Remove"):
            success = delete_friend(selected_friend, current_user)
            if success:
                st.success(f"Removed '{selected_friend}")
                st.rerun()
            else:
                st.error(f"Failed to remove '{selected_friend}")
    
    # ---------------------------
    # Rename Friend
    # ---------------------------
    st.subheader("Rename Friend")

    rename_friend = st.selectbox("Rename Friend", friendNames)
    new_name = st.text_input("New Name:")

    if rename_friend != "-- Select a Friend --":
        if st.button("Save", key=f"rename_{rename_friend}"):
            success = supabase.table("friends").update({"name": new_name}).eq("user_id", current_user).eq("name", rename_friend).execute()
            if success:
                st.success(f"Renamed '{new_name}'")
                st.rerun()
            else:
                st.error(f"Failed to rename '{rename_friend}'")

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
    res = supabase.table("users").select("u_id", count="exact").execute()

    user_count = res.count or 0  # 'count' gives the number of rows

    # ----------------------
    # No users exist → Create Admin
    # ----------------------
    if user_count == 0:
        st.title("Create Admin Account")
        admin_username = st.text_input("Admin Username")
        admin_password = st.text_input("Admin Password", type="password")
        if st.button("Create Admin"):
            if admin_username and admin_password:
                success = create_user(admin_username, admin_password)
                if success:
                    st.success(f"Admin account '{admin_username}' created. Please log in.")
                    st.rerun()
                else:
                    st.error("Failed to create admin account.")
            else:
                st.error("Enter both username and password")

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
            if not (new_username and new_password):
                st.error("Please enter both username and password")
            else:
                # Check if the username already exists
                exists = supabase.table("users").select("username").eq("username", new_username).execute()
                
                if exists.data:
                    st.error("This username is already taken. Please choose another.")
                else:
                    # Create user
                    user_info = create_user(new_username, new_password)
                    if user_info:
                        st.session_state.loggedin = True
                        st.session_state.current_user_id = user_info[0]
                        st.session_state.current_username = user_info[1]
                        st.session_state.current_role = user_info[2]
                        st.rerun()
                    else:
                        st.error("Failed to create user.")

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

        # Show side bar menu
        st.sidebar.title(f"User: {st.session_state.current_username}")
        pages = ["Home", "All Suggestions", "Leaderboard", "User Options"]
        if st.session_state.current_role == "admin":
            pages.append("Admin Panel")
        page = st.sidebar.radio("Go to", pages)
    
    if page == "Home":
        page_addSuggestion()
    elif page == "All Suggestions":
        page_viewSuggestions()
    elif page == "Leaderboard":
        page_Leaderboard()
    elif page == "User Options":
        page_user_options()
    elif page == "Admin Panel":
        page_admin()


if __name__ == "__main__":
    main()

