"""
Long-Form Video Creator Page.

Fully working long-form pipeline with section-by-section generation,
real image generation (not mock/pseudo), and per-step error recovery.

On failure, displays all sections that completed before the error,
including their scripts, audio, and section videos.
"""

import sys
import asyncio
from pathlib import Path

# Ensure the project root is importable
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
from v2.core.models import LongFormState

init_db()

st.title("Long-Form Video Creator")
st.markdown("Generate full-length videos (3-15 minutes) with structured sections, narration, and visuals.")

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
col_config, col_output = st.columns([1, 1], gap="large")

with col_config:
    # Profile selector
    profiles = get_all_profiles()
    profile_names = ["(None)"] + [p.name for p in profiles]
    selected_profile_name = st.selectbox(
        "Profile", options=profile_names, index=0, key="lf_profile"
    )

    selected_profile = None
    if selected_profile_name != "(None)":
        selected_profile = next(
            (p for p in profiles if p.name == selected_profile_name), None
        )

    st.markdown("---")
    st.subheader("Video Configuration")

    topic = st.text_input(
        "Topic",
        placeholder="e.g., The complete guide to building credit in your 20s",
        key="lf_topic",
    )

    c1, c2 = st.columns(2)
    with c1:
        purpose = st.selectbox("Purpose", options=PURPOSES, index=0, key="lf_purpose")
    with c2:
        tone = st.selectbox("Tone", options=TONES, index=0, key="lf_tone")

    target_audience = st.text_input(
        "Target Audience",
        value=(selected_profile.target_audience
               if selected_profile and selected_profile.target_audience else ""),
        placeholder="e.g., First-time homebuyers aged 25-40",
        key="lf_audience",
    )

    c3, c4 = st.columns(2)
    with c3:
        platform = st.selectbox("Platform", options=PLATFORMS, index=2, key="lf_platform")
    with c4:
        duration = st.number_input(
            "Target Duration (seconds)",
            min_value=120, max_value=1200, value=480, step=60,
            key="lf_duration",
        )

    orientation = st.selectbox(
        "Orientation", options=["Landscape", "Portrait"], index=0, key="lf_orient"
    )

    st.markdown("---")
    st.subheader("Models & Style")

    c5, c6 = st.columns(2)
    with c5:
        model_provider = st.selectbox(
            "LLM Provider", options=["google", "openai", "anthropic", "xai"],
            index=0, key="lf_llm",
        )
    with c6:
        image_provider = st.selectbox(
            "Image Provider", options=["google", "openai", "flux"],
            index=0, key="lf_img",
        )

    image_style = st.selectbox(
        "Image Style", options=IMAGE_STYLES, index=7, key="lf_style"  # Cinematic
    )
    voice_actor = st.selectbox(
        "Voice Actor", options=VOICE_ACTOR_NAMES, index=2, key="lf_voice"
    )

    st.markdown("---")
    st.subheader("Visual Mode")

    visual_mode = st.radio(
        "How to create video clips",
        options=VISUAL_MODES,
        index=0,
        format_func=lambda x: {
            "zoompan": "Zoompan (image + camera motion)",
            "video_gen": "AI Video Generation (Runway/Luma/Kling)",
        }.get(x, x),
        horizontal=True,
        key="lf_vis_mode",
    )

    video_provider = "runway"
    if visual_mode == "video_gen":
        video_provider = st.selectbox(
            "Video Provider", options=VIDEO_PROVIDERS, index=0, key="lf_vid_prov",
        )

    st.markdown("---")
    st.subheader("Options")

    c_opt1, c_opt2 = st.columns(2)
    with c_opt1:
        allow_faces = st.toggle("Allow faces in images", value=False, key="lf_faces")
    with c_opt2:
        single_image = st.toggle(
            "One image per clip",
            value=False,
            key="lf_single_img",
            help="Use a single image for each clip instead of splitting into multiple images every ~3 seconds",
        )

    additional_instructions = st.text_area(
        "Additional Instructions", placeholder="Brand voice, CTAs, things to avoid...",
        height=80, key="lf_instructions",
    )
    additional_image_requests = st.text_area(
        "Image Requests", placeholder="Color palettes, visual motifs...",
        height=80, key="lf_img_req",
    )
    style_reference = st.text_input(
        "Style Reference", placeholder="Creator or pacing to emulate...",
        key="lf_ref",
    )

    if selected_profile:
        add_profile_info = st.toggle(
            "Include profile info", value=True, key="lf_profile_info"
        )
    else:
        add_profile_info = False

    generate = st.button(
        "Generate Long-Form Video", type="primary",
        use_container_width=True, key="lf_gen",
    )


# ---------------------------------------------------------------------------
# Helper: display partial long-form results on failure
# ---------------------------------------------------------------------------
def _display_partial_long_form(state: LongFormState) -> None:
    """Show whatever sections completed before the pipeline failed."""
    if state.goal:
        st.markdown(f"**Goal:** {state.goal}")

    if not state.sections:
        st.info("No sections were generated before the error.")
        return

    for i, section in enumerate(state.sections):
        label = section.section_structure.section_name if section.section_structure else f"Section {i+1}"
        with st.expander(f"Section {i+1}: {label}", expanded=False):
            if section.section_structure:
                st.caption(section.section_structure.section_purpose)
            if section.section_script:
                st.text_area(
                    "Script", value=section.section_script[:1000],
                    height=150, disabled=True, label_visibility="collapsed",
                    key=f"lf_partial_script_{i}",
                )
            if section.audio_path and section.audio_path.exists():
                st.audio(str(section.audio_path))
            if section.section_video_path and section.section_video_path.exists():
                st.video(str(section.section_video_path))


# ---------------------------------------------------------------------------
# Output column
# ---------------------------------------------------------------------------
with col_output:
    if generate:
        if not topic:
            st.error("Please enter a topic.")
            st.stop()

        final_instructions = additional_instructions or ""
        if add_profile_info and selected_profile:
            final_instructions += f"\nThe script is for: {selected_profile.name}."

        state = LongFormState(
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
            additional_instructions=final_instructions or None,
            additional_image_requests=additional_image_requests or None,
            style_reference=style_reference or "",
            visual_mode=visual_mode,
            video_provider=video_provider,
            allow_faces=allow_faces,
            single_image_per_segment=single_image,
        )

        progress_bar = st.progress(0.0, text="Starting long-form pipeline...")
        status_container = st.status("Generating long-form video...", expanded=True)

        def on_progress(message: str, percent: float):
            progress_bar.progress(percent, text=message)
            status_container.write(message)

        from v2.pipeline.pipeline_runner import PipelineRunner, PipelineError

        pipeline_failed = False

        try:
            runner = PipelineRunner(model_provider=model_provider)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                state = loop.run_until_complete(
                    runner.run_long_form(state=state, on_progress=on_progress)
                )
            finally:
                loop.close()

            status_container.update(label="Generation complete!", state="complete")

        except PipelineError as pe:
            pipeline_failed = True
            state = pe.partial_state
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
            import traceback
            st.code(traceback.format_exc())

        # --- Display results ---
        st.markdown("---")

        if pipeline_failed:
            st.subheader("Partial Results")
            _display_partial_long_form(state)
        else:
            # Structure overview
            with st.expander("Video Structure", expanded=False):
                st.markdown(f"**Goal:** {state.goal}")
                for i, section in enumerate(state.sections):
                    st.markdown(
                        f"**Section {i + 1}: {section.section_structure.section_name}**"
                    )
                    st.caption(section.section_structure.section_purpose)

            # Full script
            with st.expander("Full Script", expanded=False):
                st.text_area(
                    "Combined script", value=state.full_script or "", height=400,
                    disabled=True, label_visibility="collapsed",
                )

            # Per-section details
            with st.expander("Section Details", expanded=False):
                for i, section in enumerate(state.sections):
                    st.markdown(
                        f"### Section {i + 1}: {section.section_structure.section_name}"
                    )
                    if section.section_script:
                        st.text(
                            section.section_script[:500]
                            + ("..." if len(section.section_script) > 500 else "")
                        )
                    if section.audio_path and section.audio_path.exists():
                        st.audio(str(section.audio_path))
                    if section.section_video_path and section.section_video_path.exists():
                        st.video(str(section.section_video_path))
                    st.markdown("---")

            # Final video
            st.subheader("Final Video")
            if state.final_video_path and Path(state.final_video_path).exists():
                st.video(str(state.final_video_path))

                with open(state.final_video_path, "rb") as f:
                    st.download_button(
                        "Download Video",
                        data=f,
                        file_name=f"moceanai_long_{topic[:30].replace(' ', '_')}.mp4",
                        mime="video/mp4",
                        use_container_width=True,
                    )
            else:
                st.warning("No video file was produced.")

    else:
        st.info(
            "Configure your long-form video on the left and click "
            "**Generate Long-Form Video** to begin."
        )
        st.markdown("""
        **What to expect:**
        - The pipeline generates 5-8 structured sections
        - Each section gets its own script, audio, and visuals
        - Sections are assembled with continuity between them
        - Typical generation time: 10-30 minutes depending on length
        - If a step fails, all previous work is preserved and shown
        """)
