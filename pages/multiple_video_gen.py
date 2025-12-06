import asyncio
from pathlib import Path
import streamlit as st

from crud import get_all_profiles, get_profile
from short_form_content import video_creator
from utils import extract_topics_form_text
# ---- Config ----
st.set_page_config(page_title="Short-Form Video Creator", layout="centered")
st.title("🎬 Short-Form Video Creator")
st.markdown(
    "Fill in the details below, and click **Generate Video**."
)

# ---- Sidebar: Debug & defaults ----
st.sidebar.header("Settings")
debug_mode = st.sidebar.checkbox("Enable debug mode", value=True)
enhance_script = st.sidebar.checkbox(
    "Enhance script for audio generation", value=False
)
# Profile Selector
with st.form("Select Profile"):
    st.subheader("Profile Selector")
    profile = st.selectbox(
        "Profile",
        options=[profile.name for profile in get_all_profiles()],
        index=0,
        key="profile"
    )
    profile_select = st.form_submit_button("Select Profile")


# ---- Main form ----
with st.form("video_form"):
    st.subheader("Video Configuration")

    if "profile" in st.session_state:
        all_profile = get_all_profiles()
        current_profile = None
        for profile in all_profile:
            if profile.name == st.session_state.profile:
                current_profile = profile
        st.session_state["target_audience"] = current_profile.target_audience

    topics = st.text_area(
        "Topics",
        placeholder="Enter Topics",
        value="",
    )

    purpose = st.selectbox(
        "Purpose",
        options=["Educational"," Promotional", "Awareness", "Storytelling", "Motivational", "Tutorial", "News", "Entertainment"],
        index=0,
    )

    target_audience = st.text_input(
        "Target Audience",
        key="target_audience",
    )

    tone = st.selectbox(
        "Tone / Mood",
        options=["Informative", "Conversational", "Professional","Inspirational",
                 "Humorous", "Dramatic", "Empathetic", "Persuasive","Narrative",
                 "Neutral"],
        index=0,
    )
    platform = st.selectbox(
        "Platform",
        options=["Tiktok", "Instagram", "Youtube"],
        index=0,
    )
    duration_seconds = st.number_input(
        "Duration (seconds)",
        min_value=5,
        max_value=600,
        value=60,
        step=5,
    )
    orientation = st.selectbox(
        "Orientation",
        options=["Portrait", "Landscape"],
        index=0,
    )

    st.markdown("---")
    st.subheader("Models & Style")

    model_provider = st.selectbox(
        "Model Provider",
        options=["google", "openai", "claude", "xai", "deepseek"],
        index=0,
    )
    image_model = st.selectbox(
        "Image Model",
        options=["google", "openai"],
        index=0,
    )
    image_style = st.selectbox(
        "Image Style",
        options=[
            "Photo Realism",
            "Hyperrealism",
            "Cartoon / 2D Illustration",
            "Minimalist / Flat Illustration",
            "Comic / Manga",
            "Cinematic",
            "3D Render / CGI",
            "Fantasy / Surreal",
            "Vintage / Retro",
        ],
        index=1,  # Hyperrealism
    )
    voice_actor = st.selectbox(
        "Voice Actor",
        options=[
            "american_male_narrator",
            "american_male_conversationalist",
            "american_female_conversationalist",
            "british_male_narrator",
            "british_female_narrator",
            "american_male_story_teller",
            "american_female_narrator",
            "american_female_media_influencer",
            "american_female_media_influencer_2"
        ],
        index=2,  # american_female_conversationalist
    )

    additional_instructions = st.text_area(
        "Additional Instructions (optional)",
        value="",
        placeholder="Any extra requests or creative directions…",
    )
    additional_image_requests = st.text_area(
        "Additional Image Requests (optional)",
        value="",
        placeholder="Palettes, motifs, props, constraints…",
    )
    style_reference = st.text_input(
        "Style Reference (optional)",
        value="",
        placeholder="Creator / pacing / style to emulate…",
    )
    add_profile_info = st.toggle("Add Profile Information", False)

    submitted = st.form_submit_button("Generate Video 🚀")

# ---- Helper: run async workflow ----
async def _run_video_creator(payload: dict):
    return await video_creator.ainvoke(payload)

# ---- Handle form submission ----
if submitted:
    # Build payload matching AgentState fields
    if "profile" in st.session_state and add_profile_info:
        all_profile = get_all_profiles()
        current_profile = None
        for profile in all_profile:
            if profile.name == st.session_state.profile:
                current_profile = profile
        additional_instructions+=f"The script is for a page called {current_profile.name}."
    # topics is a list
    st.write("Extracting Topics from text...")
    topic_list = extract_topics_form_text(topics)
    st.write(f"Extracted Topics: {topic_list}")

    for topic in topic_list:
        st.write(f"Creating Video for Topic: {topic}")
        payload = {
            "topic": topic,
            "purpose": purpose,
            "target_audience": target_audience,
            "tone": tone,
            "platform": platform,
            "duration_seconds": int(duration_seconds),
            "orientation": orientation,
            "model_provider": model_provider,
            "image_model": image_model,
            "image_style": image_style,
            "voice_actor": voice_actor,
            "additional_instructions": additional_instructions or None,
            "additional_image_requests": additional_image_requests or None,
            "style_reference": style_reference or "",
            "debug_mode": debug_mode,
        }

        st.write("### Payload")
        st.json(payload)

        with st.spinner("Generating video... this may take a bit depending on the models."):
            try:
                end_state = asyncio.run(_run_video_creator(payload))
            except RuntimeError as e:
                # Fallback in case an event loop is already running
                # (can happen in some environments)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                end_state = loop.run_until_complete(_run_video_creator(payload))
                loop.close()

        final_video_path = end_state.get("final_video_path")

        st.markdown("---")
        st.subheader("Result")

        if not final_video_path:
            st.error("No `final_video_path` was returned from the agent state.")
        else:
            final_video_path = Path(final_video_path)

            st.write(f"**Final video path:** `{final_video_path}`")

            if final_video_path.exists():
                # Show video in Streamlit
                st.video(str(final_video_path))
            else:
                st.warning(
                    "The agent returned a `final_video_path`, but the file does not exist on disk. "
                    "Double-check where the video is being saved."
                )

        if debug_mode:
            st.markdown("### Raw Agent State")
            # end_state might be a dict-like LangGraph state; try to display it
            try:
                st.json(
                    {
                        k: str(v)
                        if isinstance(v, (Path, set))
                        else v
                        for k, v in end_state.items()
                    }
                )
            except Exception:
                st.write(end_state)
