"""
Short-Form Video Creator Page.

Layout: two-column split — configuration on the left, results on the right.
Real-time progress tracking via st.progress() and st.status().

Error handling: catches PipelineError and displays the partial state
(script, audio, images) that was generated before the failure, so you
never lose work that already hit paid APIs.
"""

import sys
import asyncio
from pathlib import Path

# Ensure the project root is importable (needed when Streamlit runs pages in isolation)
_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st

from v2.core.config import (
    IMAGE_STYLES,
    PURPOSES,
    TONES,
    PLATFORMS,
    VOICE_ACTOR_NAMES,
    VISUAL_MODES,
    VIDEO_PROVIDERS,
)
from v2.core.database import get_all_profiles, init_db
from v2.core.models import ShortFormState

# Make sure DB tables exist on first page load
init_db()

st.title("Short-Form Video Creator")
st.markdown("Generate engaging short-form videos with AI-powered scripts, images, and voice-over.")

# ---------------------------------------------------------------------------
# Layout: Config (left column) | Output (right column)
# ---------------------------------------------------------------------------
col_config, col_output = st.columns([1, 1], gap="large")

with col_config:
    # --- Profile selector ---
    profiles = get_all_profiles()
    profile_names = ["(None)"] + [p.name for p in profiles]
    selected_profile_name = st.selectbox("Profile", options=profile_names, index=0)

    selected_profile = None
    if selected_profile_name != "(None)":
        selected_profile = next((p for p in profiles if p.name == selected_profile_name), None)

    st.markdown("---")

    # --- Video configuration ---
    st.subheader("Video Configuration")

    topic = st.text_input(
        "Topic",
        placeholder="e.g., 5 credit score myths that are costing you money",
    )

    c1, c2 = st.columns(2)
    with c1:
        purpose = st.selectbox("Purpose", options=PURPOSES, index=0)
    with c2:
        tone = st.selectbox("Tone", options=TONES, index=0)

    target_audience = st.text_input(
        "Target Audience",
        value=(selected_profile.target_audience
               if selected_profile and selected_profile.target_audience else ""),
        placeholder="e.g., Young adults 18-30 interested in personal finance",
    )

    c3, c4 = st.columns(2)
    with c3:
        platform = st.selectbox("Platform", options=PLATFORMS, index=0)
    with c4:
        duration = st.number_input(
            "Duration (seconds)", min_value=15, max_value=300, value=60, step=5
        )

    orientation = st.selectbox("Orientation", options=["Portrait", "Landscape"], index=0)

    st.markdown("---")

    # --- Models & Style ---
    st.subheader("Models & Style")

    c5, c6 = st.columns(2)
    with c5:
        model_provider = st.selectbox(
            "LLM Provider", options=["google", "openai", "anthropic", "xai"], index=0
        )
    with c6:
        image_provider = st.selectbox(
            "Image Provider", options=["google", "openai", "flux"], index=0
        )

    image_style = st.selectbox("Image Style", options=IMAGE_STYLES, index=1)
    voice_actor = st.selectbox("Voice Actor", options=VOICE_ACTOR_NAMES, index=2)

    st.markdown("---")

    # --- Visual mode (zoompan vs AI video generation) ---
    st.subheader("Visual Mode")

    visual_mode = st.radio(
        "How to create video clips",
        options=VISUAL_MODES,
        index=0,
        format_func=lambda x: {
            "zoompan": "Zoompan (image + camera motion) -- fast & cheap",
            "video_gen": "AI Video Generation (Runway/Luma/Kling) -- higher quality, slower",
        }.get(x, x),
        horizontal=True,
    )

    video_provider = "runway"
    if visual_mode == "video_gen":
        video_provider = st.selectbox(
            "Video Provider",
            options=VIDEO_PROVIDERS,
            index=0,
            help="Requires the corresponding API key in your .env file",
        )

    st.markdown("---")

    # --- Options ---
    st.subheader("Options")

    c7, c8, c9, c10 = st.columns(4)
    with c7:
        enhance_tts = st.toggle("Enhance script for TTS", value=True)
    with c8:
        add_subtitles = st.toggle("Burn-in subtitles", value=False)
    with c9:
        allow_faces = st.toggle("Allow faces in images", value=False)
    with c10:
        single_image = st.toggle(
            "One image per clip",
            value=False,
            help="Use a single image for each clip instead of splitting into multiple images every ~3 seconds",
        )

    additional_instructions = st.text_area(
        "Additional Instructions",
        placeholder="Brand voice, specific CTAs, things to avoid...",
        height=80,
    )
    additional_image_requests = st.text_area(
        "Image Requests",
        placeholder="Color palettes, visual motifs, specific props...",
        height=80,
    )
    style_reference = st.text_input(
        "Style Reference",
        placeholder="Creator or pacing to emulate...",
    )

    if selected_profile:
        add_profile_info = st.toggle("Include profile info in instructions", value=True)
    else:
        add_profile_info = False

    # --- Generate button ---
    generate = st.button("Generate Video", type="primary", use_container_width=True)


# ---------------------------------------------------------------------------
# Helper: display whatever partial results exist in the state
# ---------------------------------------------------------------------------
def _display_partial_results(state: ShortFormState) -> None:
    """
    Show any results that were generated before a failure.
    This ensures you never lose work from paid API calls.
    """
    has_content = False

    # Script
    if state.script:
        has_content = True
        with st.expander("Script (generated before error)", expanded=True):
            if state.goal:
                st.markdown(f"**Goal:** {state.goal}")
            if state.hook:
                st.markdown(f"**Hook:** {state.hook}")
            st.text_area(
                "Script", value=state.script, height=200,
                disabled=True, label_visibility="collapsed",
            )

    # Audio
    if state.audio_path and state.audio_path.exists():
        has_content = True
        with st.expander("Audio (generated before error)", expanded=False):
            st.audio(str(state.audio_path))

    # Images
    image_paths = []
    for plan in state.segment_visual_plans:
        image_paths.extend(p for p in plan.image_paths if p.exists())
    if image_paths:
        has_content = True
        with st.expander(f"Generated Images ({len(image_paths)})", expanded=False):
            cols = st.columns(min(4, len(image_paths)))
            for i, img in enumerate(image_paths):
                cols[i % len(cols)].image(str(img), use_container_width=True)

    # Clip videos
    clip_paths = [p for p in state.clip_paths if p and p.exists()]
    if clip_paths:
        has_content = True
        with st.expander(f"Animated Clips ({len(clip_paths)})", expanded=False):
            for clip in clip_paths:
                st.video(str(clip))

    if not has_content:
        st.info("No partial results were generated before the error.")


# ---------------------------------------------------------------------------
# Output column — runs pipeline on generate, shows results or partial state
# ---------------------------------------------------------------------------
with col_output:
    if generate:
        if not topic:
            st.error("Please enter a topic.")
            st.stop()

        # Build additional instructions (optionally including profile info)
        final_instructions = additional_instructions or ""
        if add_profile_info and selected_profile:
            final_instructions += f"\nThe script is for a page called {selected_profile.name}."
            if selected_profile.one_sentence_summary:
                final_instructions += f" {selected_profile.one_sentence_summary}"

        # Build the initial pipeline state from UI inputs
        state = ShortFormState(
            topic=topic,
            purpose=purpose,
            target_audience=target_audience,
            tone=tone,
            platform=platform,
            duration_seconds=int(duration),
            orientation=orientation,
            model_provider=model_provider,
            image_provider=image_provider,
            image_style=image_style,
            voice_actor=voice_actor,
            enhance_for_tts=enhance_tts,
            add_subtitles=add_subtitles,
            additional_instructions=final_instructions or None,
            additional_image_requests=additional_image_requests or None,
            style_reference=style_reference or "",
            visual_mode=visual_mode,
            video_provider=video_provider,
            allow_faces=allow_faces,
            single_image_per_segment=single_image,
        )

        # Progress widgets
        progress_bar = st.progress(0.0, text="Starting pipeline...")
        status_container = st.status("Generating video...", expanded=True)

        def on_progress(message: str, percent: float):
            progress_bar.progress(percent, text=message)
            status_container.write(message)

        # Import here to avoid circular imports at module level
        from v2.pipeline.pipeline_runner import PipelineRunner, PipelineError

        pipeline_failed = False

        try:
            runner = PipelineRunner(model_provider=model_provider)

            # Create a fresh event loop (Streamlit's loop isn't compatible)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                state = loop.run_until_complete(
                    runner.run_short_form(state=state, on_progress=on_progress)
                )
            finally:
                loop.close()

            status_container.update(label="Generation complete!", state="complete")

        except PipelineError as pe:
            # Pipeline failed but we have partial state — display it
            pipeline_failed = True
            state = pe.partial_state  # Use the state from when the error occurred
            status_container.update(
                label=f"Failed at: {pe.failed_step}", state="error"
            )
            st.error(
                f"Pipeline failed at **{pe.failed_step}**: {pe.original_error}\n\n"
                f"Partial results are shown below. A checkpoint was saved to disk."
            )

        except Exception as e:
            pipeline_failed = True
            status_container.update(label="Generation failed", state="error")
            st.error(f"Unexpected error: {e}")

        # --- Display results ---
        st.markdown("---")

        if pipeline_failed:
            st.subheader("Partial Results")
            _display_partial_results(state)
        else:
            # Script preview
            with st.expander("Script", expanded=False):
                st.markdown(f"**Goal:** {state.goal}")
                st.markdown(f"**Hook:** {state.hook}")
                st.markdown("**Full Script:**")
                st.text_area(
                    "Script text", value=state.script, height=200,
                    disabled=True, label_visibility="collapsed",
                )

            # Audio player
            if state.audio_path and state.audio_path.exists():
                with st.expander("Audio", expanded=False):
                    st.audio(str(state.audio_path))

            # Image gallery
            image_paths = []
            for plan in state.segment_visual_plans:
                image_paths.extend(plan.image_paths)
            if image_paths:
                with st.expander("Generated Images", expanded=False):
                    img_cols = st.columns(min(4, len(image_paths)))
                    for i, img_path in enumerate(image_paths):
                        if img_path.exists():
                            img_cols[i % len(img_cols)].image(
                                str(img_path), use_container_width=True
                            )

            # Final video
            st.subheader("Final Video")
            if state.final_video_path and Path(state.final_video_path).exists():
                st.video(str(state.final_video_path))

                with open(state.final_video_path, "rb") as f:
                    st.download_button(
                        "Download Video",
                        data=f,
                        file_name=f"moceanai_{topic[:30].replace(' ', '_')}.mp4",
                        mime="video/mp4",
                        use_container_width=True,
                    )
            else:
                st.warning("No video file was produced. Check the logs for errors.")

    else:
        st.info("Configure your video on the left and click **Generate Video** to begin.")
