import streamlit as st
import os

st.title("Final Videos")
st.divider()
final_videos_directory = os.path.join(os.getcwd(), "final_videos").replace(os.path.join("pages", ""), "")
all_final_videos = os.listdir(final_videos_directory)

for video_path in all_final_videos:
    st.video(data=os.path.join(final_videos_directory, video_path))
    st.divider()