import streamlit as st
st.title("Final Video")
if "video" not in st.session_state:
    st.error("No Video has been created.")
else:
    if st.session_state.video.final_video_path:
        st.video(data=st.session_state.video.final_video_path)
    else:
        st.error("The final video has not been created.")