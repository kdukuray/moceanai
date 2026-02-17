"""
Video History Page
Browse, play, and manage previously generated videos.
"""

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st

from v2.core.database import init_db, get_all_videos, delete_video_record

init_db()

st.title("Video History")
st.markdown("Browse all previously generated videos.")

# Fetch all videos
videos = get_all_videos()

if not videos:
    st.info("No videos generated yet. Head to the Short Form or Long Form page to create your first video.")
    st.stop()

# Summary stats
col_stat1, col_stat2, col_stat3 = st.columns(3)
with col_stat1:
    st.metric("Total Videos", len(videos))
with col_stat2:
    short_count = sum(1 for v in videos if v.video_type == "short_form")
    st.metric("Short Form", short_count)
with col_stat3:
    long_count = sum(1 for v in videos if v.video_type == "long_form")
    st.metric("Long Form", long_count)

st.markdown("---")

# Filter
filter_type = st.selectbox(
    "Filter by type",
    options=["All", "Short Form", "Long Form"],
    index=0,
)

filtered = videos
if filter_type == "Short Form":
    filtered = [v for v in videos if v.video_type == "short_form"]
elif filter_type == "Long Form":
    filtered = [v for v in videos if v.video_type == "long_form"]

# Display videos
for video in filtered:
    video_path = Path(video.video_path) if video.video_path else None
    exists = video_path.exists() if video_path else False

    with st.container(border=True):
        c_info, c_action = st.columns([3, 1])

        with c_info:
            badge = "Short" if video.video_type == "short_form" else "Long"
            st.markdown(f"**{video.topic}** `{badge}` `{video.orientation}` `{video.duration_seconds}s`")
            st.caption(
                f"Created: {video.created_at.strftime('%Y-%m-%d %H:%M') if video.created_at else 'Unknown'} | "
                f"LLM: {video.model_provider} | Images: {video.image_provider} | Voice: {video.voice_actor}"
            )

            if video.goal:
                st.markdown(f"*Goal: {video.goal}*")

        with c_action:
            if exists:
                if st.button("Play", key=f"play_{video.id}"):
                    st.session_state[f"show_video_{video.id}"] = True
            else:
                st.caption("File not found")

            if st.button("Delete", key=f"del_{video.id}"):
                delete_video_record(video.id)
                st.rerun()

        # Expandable video player and script
        if st.session_state.get(f"show_video_{video.id}"):
            if exists:
                st.video(str(video_path))

                with open(video_path, "rb") as f:
                    st.download_button(
                        "Download",
                        data=f,
                        file_name=video_path.name,
                        mime="video/mp4",
                        key=f"dl_{video.id}",
                    )

            if video.script:
                with st.expander("Script"):
                    st.text(video.script[:2000])
