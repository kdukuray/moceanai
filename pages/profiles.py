import streamlit as st
from crud import *
from models import *
from db import init_db

init_db()

all_profiles = get_all_profiles()
all_profile_names_and_ids = {profile.name: profile.id for profile in all_profiles}

st.title("Profile Page")
st.divider()

# ------------------------------- Current Profile -------------------------------
st.subheader("Current Profile")
current_profile_name  = st.selectbox(label="Select Profile", options=all_profile_names_and_ids.keys()) # this returns the names of the profiles
if st.button("Select Profile"):
    st.session_state["current_profile_name"] = current_profile_name

if "current_profile_name" in st.session_state:
    st.success(f"The current profile is: {st.session_state['current_profile_name']} with id: {all_profile_names_and_ids[st.session_state['current_profile_name']]}")
else:
    st.error("There is no current profile yet.")

st.divider()
# ------------------------------- All Profiles -------------------------------
st.subheader("All Profiles")

col1, col2 = st.columns(2)
for index, profile in enumerate(all_profiles):
    if index % 2 == 0:
        with col1:
            if st.session_state.get("current_profile_name", None) and st.session_state["current_profile_name"] == profile.name:
                st.markdown(f"**_Current Profile: {profile.name}_**")
            else:
                st.markdown(f"Profile: {profile.name}")
    else:
        with col2:
            if st.session_state.get("current_profile_name", None) and st.session_state["current_profile_name"] == profile.name:
                st.markdown(f"**_Current Profile: {profile.name}_**")
            else:
                st.markdown(f"Profile: {profile.name}")

st.divider()

# ------------------------------- Create Profile -------------------------------
st.subheader("Create Profile")
new_profile_name = st.text_input(label = "Name")
new_profile_one_sentence_summary = st.text_input(label = "One Sentence")
new_profile_detailed_description = st.text_area(label = "Detailed Description")
new_profile_target_audience = st.text_input(label = "Target Audience")
new_profile_target_brand_color = st.text_input(label = "Target Brand Color")
new_profile_target_slogan = st.text_input(label = "Target Slogan")
if st.button("Create Profile"):
    new_profile = {
        "name": new_profile_name,
        "one_sentence_summary": new_profile_one_sentence_summary if new_profile_one_sentence_summary else None,
        "detailed_description": new_profile_detailed_description if new_profile_detailed_description else None,
        "target_audience": new_profile_target_audience if new_profile_target_audience else None,
        "brand_color": new_profile_target_brand_color if new_profile_target_brand_color else None,
        "slogan": new_profile_target_slogan if new_profile_target_slogan else None
    }
    with st.spinner("Creating Profile"):
        created_profile = create_profile(**new_profile)
        if created_profile:
            st.success(f"Profile {created_profile.name} created.")
        else:
            st.error(f"Profile {created_profile.name} could not be created.")
st.divider()


st.subheader("Modify Profile")

profile_to_modify = st.selectbox(label="Profile", options=all_profile_names_and_ids.keys())
if profile_to_modify is not None:
    profile_obj = get_profile(profile_id=all_profile_names_and_ids[profile_to_modify])
    updated_name = st.text_input(label="Name", key="updated_name", placeholder=profile_obj.name)
    updated_one_sentence_summary = st.text_input(label="One Sentence", key="updated_one_sentence_summary", placeholder=profile_obj.one_sentence_summary)
    updated_detailed_description = st.text_area(label="Detailed Description", key="updated_detailed_description", placeholder=profile_obj.detailed_description)
    updated_target_audience = st.text_input(label="Target Audience", key="updated_target_audience", placeholder=profile_obj.target_audience)
    updated_brand_color = st.text_input(label="Brand Color", key="updated_brand_color", placeholder=profile_obj.brand_color)
    updated_slogan = st.text_input(label="Slogan", key="updated_slogan", placeholder=profile_obj.slogan)

    if st.button("Update Profile"):
        updated_profile_info = {
            "name": updated_name if updated_name else profile_obj.name,
            "one_sentence_summary": updated_one_sentence_summary if updated_one_sentence_summary else None,
            "detailed_description": updated_detailed_description if updated_detailed_description else None,
            "target_audience": updated_target_audience if updated_target_audience else None,
            "brand_color": updated_brand_color if updated_brand_color else None,
            "slogan": updated_slogan if updated_slogan else None
        }
        updated_profile = update_profile(profile_id=profile_obj.id, **updated_profile_info)
        if updated_profile:
            st.success(f"Profile {updated_profile.name} updated.")
        else:
            st.error(f"Profile {updated_profile.name} could not be updated.")

st.divider()


st.subheader("Delete Profile")
all_profile_names_and_ids = {profile.name: profile.id for profile in all_profiles}
profile_to_delete = st.selectbox(label="Profile", options=all_profile_names_and_ids.keys(), key="delete_profile")
if st.button("Delete Profile"):
    if profile_to_delete is not None:
        profile_obj = get_profile(profile_id=all_profile_names_and_ids[profile_to_delete])
        result = delete_profile(profile_id=all_profile_names_and_ids[profile_to_delete])
        if result:
            st.success(f"Profile {profile_obj.name} deleted.")
        else:
            st.error(f"Profile {profile_obj.name} could not be deleted.")

st.divider()


