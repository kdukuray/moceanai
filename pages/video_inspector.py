import streamlit as st
import asyncio
from shortformvideo import ShortFormVideo

st.title("🎬 Video Info")
st.divider()

if "video" not in st.session_state:
    st.error("No video found in session state.")
else:
    if "video" not in st.session_state:
        st.error("No video found in session state.")
        st.stop()



    # Section 1: Core Metadata
    st.subheader("📌 Core Metadata")
    st.text(f"Central Theme: {st.session_state.video.topic}")
    st.text(f"Purpose: {st.session_state.video.purpose.value}")
    st.text(f"Target Audience: {st.session_state.video.target_audience}")
    st.text(f"Tone: {st.session_state.video.tone.value}")
    st.text(f"Platform: {st.session_state.video.platform.value}")
    st.text(f"Length: {st.session_state.video.duration_seconds} seconds")
    st.text(f"Aspect Ratio: {st.session_state.video.aspect_ratio.value}")
    st.text(f"Image Model: {st.session_state.video.image_model.value}")
    st.text(f"Voice Model: {st.session_state.video.voice_model.value}")
    if st.session_state.video.style_reference:
        st.text(f"Style Reference: {st.session_state.video.style_reference}")
    if st.session_state.video.auxiliary_requests:
        st.text(f"Auxiliary Requests: {st.session_state.video.auxiliary_requests}")

    # Section 2: Script + State
    st.subheader("📄 Cumulative Script")
    if st.session_state.video.cumulative_script:
        st.code(st.session_state.video.cumulative_script, language="markdown")
    else:
        st.info("Cumulative script is empty.")

    st.text(f"Clip Count: {st.session_state.video.clip_count}")
    st.text(f"All Clips Valid: {'✅' if st.session_state.video.all_clips_valid else '❌'}")
    st.text(f"Final Video Path: {st.session_state.video.final_video_path or 'Not generated yet'}")

    # Section 3: Generated Topics
    st.subheader("🧠 Generated Topics")
    if st.session_state.video.generated_topics:
        for i, topic in enumerate(st.session_state.video.generated_topics, 1):
            st.json(topic, expanded=False)
    else:
        st.info("No topics generated yet.")

    # Section 4: Actions
    st.subheader("⚙️ Actions")

    if st.button("1️⃣ Generate Topics"):
        try:
            st.session_state.video.generate_talking_points()
            st.success("Topics generated.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if st.button("2️⃣ Generate Clips"):
        try:
            st.session_state.video.generate_clips()
            st.success("Clips generated.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if st.button("3️⃣ Generate Clip Visuals"):
        try:
            asyncio.run(st.session_state.video.generate_clips_visuals())
            st.success("Visuals generated.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if st.button("4️⃣ Generate Clip Audios"):
        try:
            asyncio.run(st.session_state.video.generate_clips_audios())
            st.success("Audios generated.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if st.button("5️⃣ Animate Clips"):
        try:
            st.session_state.video.animate_clips_visuals()
            st.success("Animations completed.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if st.button("6️⃣ Merge Audios and Visuals"):
        try:
            st.session_state.video.merge_clips_audios_and_visuals()
            st.success("Audio and visuals merged.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if st.button("7️⃣ Validate Clips"):
        try:
            st.session_state.video.validate_clips()
            st.success("Clips validated.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if st.button("8️⃣ Merge All Clips (Final Video)"):
        try:
            st.session_state.video.merge_all_clips()
            st.success(f"Final video created: {st.session_state.video.final_video_path}")
            st.rerun()
        except Exception as e:
            st.error(str(e))
