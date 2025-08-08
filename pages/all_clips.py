from uuid import uuid4
import streamlit as st


st.title("All Clips")
st.divider()

if "video" not in st.session_state:
    st.error("No video found in session state.")
else:
    st.title("Video Clips Summary")
    valid_clips, invalid_clips = st.session_state.video.clips_summary()
    col1, col2 = st.columns(2)
    with col1:
        st.text(f"Clip Count: {st.session_state.video.clip_count}")
        st.text(f"Valid Clips Count: {len(valid_clips)}")
        st.text(f"Invalid Clips Count: {len(invalid_clips)}")

    with col2:
        st.text(f"All Clips Valid: {'✅' if st.session_state.video.all_clips_valid else '❌'}")
        st.text(f"Valid Clip Ids: {valid_clips}")
        st.text(f"Invalid Clip Ids: {invalid_clips}")
    st.divider()


    st.title("Individual Clips Info")
    st.divider()
    for clip in st.session_state.video.clips:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader(f"Clip {clip.clip_id} Info")
            st.markdown(f"**ID:** {clip.clip_id}")
            st.markdown(f"**Clip Valid:** {'✅' if clip.is_valid() else '❌'}")
            # Animated (merged) video info
            if clip.is_valid():
                st.markdown(f"**Animated Video path:** {clip.animated_video_path}")
            else:
                st.markdown(f"**Animated Video path:** ❌")


        with col2:
            st.subheader("Actions")
            if st.button("ReGenerate Base Image", key=uuid4().hex):
                with st.spinner(f"Regenerating Base Image for clip {clip.clip_id}..."):
                    st.session_state.video.re_do_clip_action(clip_id=clip.clip_id, action="base_image")
                print("st base image ran")

            if st.button("Regenerate Audio", key=uuid4().hex):
                with st.spinner(f"Regenerating Audio for clip {clip.clip_id}..."):
                    st.session_state.video.re_do_clip_action(clip_id=clip.clip_id, action="audio")
                print("st audio ran")
            if st.button("Merge Audio and Visuals", key=uuid4().hex):
                with st.spinner(f"Regenerating(merging) Animated Video for clip {clip.clip_id}..."):
                    st.session_state.video.re_do_clip_action(clip_id=clip.clip_id, action="animate")
                print("st animated video ran")


        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Base Image Path:** {clip.base_image_path if clip.base_image_path else '❌'}")
        with col2:
            st.markdown(f"**Base image Description:** {clip.base_image_description[0:int(len(clip.base_image_description) / 4)] + '...' if clip.base_image_description else '❌'}")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**Voice Over Path:** {clip.voice_over_audio_path if clip.voice_over_audio_path else '❌'}")
        with col2:
            st.markdown(f"**Voice Script**: {clip.voice_script if clip.voice_script else '❌'}")

        st.divider()
        st.divider()
