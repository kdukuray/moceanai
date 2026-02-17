"""
Profile Management Page
Create, view, edit, and delete brand profiles.
"""

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st

from v2.core.database import (
    init_db,
    get_all_profiles,
    create_profile,
    update_profile,
    delete_profile,
)

init_db()

st.title("Profile Manager")
st.markdown("Manage brand profiles to auto-fill video generation settings.")

# ---------------------------------------------------------------------------
# Current profiles
# ---------------------------------------------------------------------------
profiles = get_all_profiles()

if profiles:
    st.subheader("Existing Profiles")

    cols = st.columns(min(3, len(profiles)))
    for i, profile in enumerate(profiles):
        with cols[i % len(cols)]:
            with st.container(border=True):
                st.markdown(f"**{profile.name}**")
                if profile.one_sentence_summary:
                    st.caption(profile.one_sentence_summary)
                if profile.target_audience:
                    st.markdown(f"*Audience:* {profile.target_audience}")
                if profile.brand_color:
                    st.markdown(f"*Color:* {profile.brand_color}")
                if profile.slogan:
                    st.markdown(f"*Slogan:* {profile.slogan}")
else:
    st.info("No profiles yet. Create one below.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Create profile
# ---------------------------------------------------------------------------
st.subheader("Create New Profile")

with st.form("create_profile", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1:
        new_name = st.text_input("Name *", placeholder="e.g., TechPulse")
    with c2:
        new_color = st.text_input("Brand Color", placeholder="e.g., #3B82F6")

    new_summary = st.text_input("One-Sentence Summary", placeholder="What this brand is about in one line")
    new_description = st.text_area("Detailed Description", placeholder="Full brand description...", height=100)
    new_audience = st.text_input("Target Audience", placeholder="Who this brand speaks to")
    new_slogan = st.text_input("Slogan", placeholder="Brand tagline or slogan")

    submitted = st.form_submit_button("Create Profile", use_container_width=True)

    if submitted:
        if not new_name:
            st.error("Profile name is required.")
        else:
            try:
                create_profile(
                    name=new_name,
                    one_sentence_summary=new_summary or None,
                    detailed_description=new_description or None,
                    target_audience=new_audience or None,
                    brand_color=new_color or None,
                    slogan=new_slogan or None,
                )
                st.success(f"Profile '{new_name}' created!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to create profile: {e}")

# ---------------------------------------------------------------------------
# Edit / Delete
# ---------------------------------------------------------------------------
if profiles:
    st.markdown("---")
    st.subheader("Edit or Delete")

    tab_edit, tab_delete = st.tabs(["Edit", "Delete"])

    with tab_edit:
        profile_to_edit = st.selectbox(
            "Select profile to edit",
            options=[(p.id, p.name) for p in profiles],
            format_func=lambda x: x[1],
            key="edit_select",
        )

        if profile_to_edit:
            pid = profile_to_edit[0]
            current = next((p for p in profiles if p.id == pid), None)

            if current:
                with st.form("edit_profile"):
                    edit_summary = st.text_input("One-Sentence Summary", value=current.one_sentence_summary or "")
                    edit_desc = st.text_area("Description", value=current.detailed_description or "")
                    edit_audience = st.text_input("Target Audience", value=current.target_audience or "")
                    edit_color = st.text_input("Brand Color", value=current.brand_color or "")
                    edit_slogan = st.text_input("Slogan", value=current.slogan or "")

                    if st.form_submit_button("Save Changes", use_container_width=True):
                        update_profile(
                            pid,
                            one_sentence_summary=edit_summary,
                            detailed_description=edit_desc,
                            target_audience=edit_audience,
                            brand_color=edit_color,
                            slogan=edit_slogan,
                        )
                        st.success("Profile updated!")
                        st.rerun()

    with tab_delete:
        profile_to_delete = st.selectbox(
            "Select profile to delete",
            options=[(p.id, p.name) for p in profiles],
            format_func=lambda x: x[1],
            key="delete_select",
        )

        if profile_to_delete:
            st.warning(f"This will permanently delete **{profile_to_delete[1]}**.")
            if st.button("Delete Profile", type="primary"):
                delete_profile(profile_to_delete[0])
                st.success("Profile deleted.")
                st.rerun()
