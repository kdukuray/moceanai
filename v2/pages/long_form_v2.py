"""
Long-Form Video Creator V2 Page.

Enhanced pipeline with:
  - Optional web research (Tavily)
  - Retention-aware outline with section types and energy targets
  - Quality gates (outline + per-section script)
  - Parallel or sequential script writing strategy
  - Global style guide + storyboard-based visual planning
  - Aggressive parallelization (audio, images, clips across sections)

Layout: two-column — config left, results right.
"""

import sys
import asyncio
from pathlib import Path

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
from v2.core.v2_models import LongFormV2State

init_db()

st.title("Long-Form Video Creator V2")
st.markdown(
    "Enhanced pipeline with research, retention-aware outlines, "
    "quality gates, and parallel section processing."
)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
col_config, col_output = st.columns([1, 1], gap="large")

with col_config:
    # --- Profile selector ---
    profiles = get_all_profiles()
    profile_names = ["(None)"] + [p.name for p in profiles]
    selected_profile_name = st.selectbox("Profile", options=profile_names, index=0)

    selected_profile = None
    if selected_profile_name != "(None)":
        selected_profile = next(
            (p for p in profiles if p.name == selected_profile_name), None
        )

    st.markdown("---")

    # --- Video configuration ---
    st.subheader("Video Configuration")

    topic = st.text_input(
        "Topic",
        placeholder="e.g., The complete guide to building wealth in your 20s",
    )

    c1, c2 = st.columns(2)
    with c1:
        purpose = st.selectbox("Purpose", options=PURPOSES, index=0)
    with c2:
        tone = st.selectbox("Tone", options=TONES, index=0)

    target_audience = st.text_input(
        "Target Audience",
        value=(
            selected_profile.target_audience
            if selected_profile and selected_profile.target_audience
            else ""
        ),
        placeholder="e.g., Professionals 25-40 interested in financial independence",
    )

    c3, c4 = st.columns(2)
    with c3:
        platform = st.selectbox("Platform", options=PLATFORMS, index=2)
    with c4:
        duration = st.number_input(
            "Target Duration (seconds)",
            min_value=120,
            max_value=1200,
            value=480,
            step=60,
        )

    orientation = st.selectbox(
        "Orientation", options=["Landscape", "Portrait"], index=0
    )

    st.markdown("---")

    # --- Research (V2 feature) ---
    st.subheader("Research")

    enable_research = st.toggle(
        "Enable web research",
        value=True,
        help="Uses Tavily to research the topic before writing. "
        "Requires TAVILY_API_KEY in your .env file.",
    )

    reference_urls = st.text_area(
        "Reference URLs (optional)",
        placeholder="Paste URLs for reference material, one per line...",
        height=60,
    )

    brand_guidelines = st.text_area(
        "Brand Guidelines (optional)",
        placeholder="Brand voice, visual identity, key messages...",
        height=60,
    )

    st.markdown("---")

    # --- Script Strategy (V2 feature) ---
    st.subheader("Script Strategy")

    script_strategy = st.radio(
        "Section writing approach",
        options=["parallel", "sequential"],
        index=0,
        format_func=lambda x: {
            "parallel": "Parallel (faster) -- writes all sections at once, then smooths transitions",
            "sequential": "Sequential (safer) -- each section reads previous ones for continuity",
        }.get(x, x),
        horizontal=False,
    )

    st.markdown("---")

    # --- Models & Style ---
    st.subheader("Models & Style")

    c5, c6 = st.columns(2)
    with c5:
        model_provider = st.selectbox(
            "LLM Provider",
            options=["google", "openai", "anthropic", "xai"],
            index=0,
        )
    with c6:
        image_provider = st.selectbox(
            "Image Provider", options=["google", "openai", "flux"], index=0
        )

    image_style = st.selectbox(
        "Image Style", options=IMAGE_STYLES, index=IMAGE_STYLES.index("Cinematic")
    )
    voice_actor = st.selectbox("Voice Actor", options=VOICE_ACTOR_NAMES, index=2)

    st.markdown("---")

    # --- Visual mode ---
    st.subheader("Visual Mode")

    visual_mode = st.radio(
        "How to create video clips",
        options=VISUAL_MODES,
        index=0,
        format_func=lambda x: {
            "zoompan": "Zoompan (image + camera motion) -- fast & cheap",
            "video_gen": "AI Video Generation (Runway/Luma/Kling) -- higher quality",
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

    c7, c8 = st.columns(2)
    with c7:
        allow_faces = st.toggle("Allow faces in images", value=False)
    with c8:
        single_image = st.toggle(
            "One image per clip",
            value=False,
            help="Use a single image per clip instead of multiple per ~3s",
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
        add_profile_info = st.toggle(
            "Include profile info in instructions", value=True
        )
    else:
        add_profile_info = False

    generate = st.button(
        "Generate Long-Form Video",
        type="primary",
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Partial results display
# ---------------------------------------------------------------------------
def _display_partial_results(state: LongFormV2State) -> None:
    """Show whatever was generated before a failure."""
    has_content = False

    if state.research_brief:
        has_content = True
        with st.expander("Research Brief (before error)", expanded=False):
            brief = state.research_brief
            if brief.key_facts:
                st.markdown("**Key Facts:**")
                for f in brief.key_facts:
                    st.markdown(f"- {f}")
            if brief.angle_recommendation:
                st.markdown(
                    f"**Recommended Angle:** {brief.angle_recommendation}"
                )

    if state.outline:
        has_content = True
        with st.expander("Outline (before error)", expanded=True):
            st.markdown(f"**Thesis:** {state.outline.thesis}")
            for i, sec in enumerate(state.outline.sections):
                st.markdown(
                    f"**{i+1}. {sec.section_name}** "
                    f"`{sec.section_type}` "
                    f"({sec.energy_target})"
                )
                st.caption(sec.section_purpose)

    for i, sec in enumerate(state.sections):
        if sec.section_script or sec.audio_path or sec.section_video_path:
            has_content = True
            with st.expander(
                f"Section {i+1}: {sec.section_plan.section_name}",
                expanded=False,
            ):
                if sec.section_script:
                    st.text_area(
                        "Script",
                        value=sec.section_script[:1000],
                        height=120,
                        disabled=True,
                        label_visibility="collapsed",
                    )
                if sec.audio_path and sec.audio_path.exists():
                    st.audio(str(sec.audio_path))
                if sec.section_video_path and sec.section_video_path.exists():
                    st.video(str(sec.section_video_path))

    if not has_content:
        st.info("No partial results were generated before the error.")


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
            final_instructions += (
                f"\nThe script is for a page called {selected_profile.name}."
            )
            if selected_profile.one_sentence_summary:
                final_instructions += f" {selected_profile.one_sentence_summary}"

        state = LongFormV2State(
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
            enable_research=enable_research,
            reference_urls=reference_urls or None,
            brand_guidelines=brand_guidelines or None,
            script_strategy=script_strategy,
        )

        progress_bar = st.progress(0.0, text="Starting V2 pipeline...")
        status_container = st.status(
            "Generating long-form video...", expanded=True
        )

        def on_progress(message: str, percent: float):
            progress_bar.progress(percent, text=message)
            status_container.write(message)

        from v2.pipeline.pipeline_runner_v2 import (
            PipelineRunnerV2,
            PipelineV2Error,
        )

        pipeline_failed = False

        try:
            runner = PipelineRunnerV2(model_provider=model_provider)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                state = loop.run_until_complete(
                    runner.run_long_form_v2(
                        state=state, on_progress=on_progress
                    )
                )
            finally:
                loop.close()

            status_container.update(
                label="Generation complete!", state="complete"
            )

        except PipelineV2Error as pe:
            pipeline_failed = True
            state = pe.partial_state
            status_container.update(
                label=f"Failed at: {pe.failed_phase}", state="error"
            )
            st.error(
                f"Pipeline failed at **{pe.failed_phase}**: "
                f"{pe.original_error}\n\n"
                f"Partial results shown below. Checkpoint saved to disk."
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
            # Research Brief
            if state.research_brief:
                with st.expander("Research Brief", expanded=False):
                    brief = state.research_brief
                    if brief.key_facts:
                        st.markdown("**Key Facts:**")
                        for f in brief.key_facts:
                            st.markdown(f"- {f}")
                    if brief.statistics:
                        st.markdown("**Statistics:**")
                        for s in brief.statistics:
                            st.markdown(f"- {s}")
                    if brief.counterarguments:
                        st.markdown("**Counterarguments:**")
                        for c in brief.counterarguments:
                            st.markdown(f"- {c}")
                    if brief.angle_recommendation:
                        st.markdown(
                            f"**Recommended Angle:** {brief.angle_recommendation}"
                        )

            # Outline
            if state.outline:
                with st.expander("Video Outline", expanded=False):
                    st.markdown(f"**Thesis:** {state.outline.thesis}")
                    if state.outline.emotional_arc:
                        st.markdown(
                            f"**Emotional Arc:** {state.outline.emotional_arc}"
                        )
                    st.markdown("---")
                    for i, sec in enumerate(state.outline.sections):
                        energy_bar = {"calm": "░░░", "building": "▒▒▒", "peak": "███", "resolving": "▓▓▓"}.get(sec.energy_target, "▒▒▒")
                        st.markdown(
                            f"**{i+1}. {sec.section_name}** "
                            f"`{sec.section_type}` "
                            f"{energy_bar} "
                            f"({sec.target_duration_seconds}s)"
                        )
                        st.caption(sec.section_purpose)
                        if sec.retention_device:
                            st.caption(
                                f"Retention: {sec.retention_device}"
                            )

            # Outline Review
            if state.outline_review:
                with st.expander("Outline Review", expanded=False):
                    orv = state.outline_review
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Structure", f"{orv.structure_score}/10")
                    c2.metric("Variety", f"{orv.variety_score}/10")
                    c3.metric("Retention", f"{orv.retention_score}/10")
                    c4.metric("Depth", f"{orv.depth_score}/10")
                    c5.metric("Pacing", f"{orv.pacing_score}/10")
                    if orv.passed:
                        st.success("Outline passed quality gate.")
                    else:
                        st.warning(
                            f"Outline did not pass "
                            f"(revised {state.outline_revision_count} time(s))."
                        )
                    if orv.revision_notes:
                        st.markdown("**Revision Notes:**")
                        for n in orv.revision_notes:
                            st.markdown(f"- {n}")

            # Full Script
            if state.full_script:
                with st.expander("Full Script", expanded=False):
                    st.text_area(
                        "Combined script",
                        value=state.full_script,
                        height=300,
                        disabled=True,
                        label_visibility="collapsed",
                    )

            # Per-section details
            if state.sections:
                with st.expander(
                    f"Section Details ({len(state.sections)} sections)",
                    expanded=False,
                ):
                    for i, sec in enumerate(state.sections):
                        st.markdown(
                            f"### Section {i+1}: "
                            f"{sec.section_plan.section_name}"
                        )
                        st.caption(
                            f"Type: {sec.section_plan.section_type} | "
                            f"Energy: {sec.section_plan.energy_target}"
                        )

                        if sec.section_script:
                            st.text_area(
                                f"Script {i+1}",
                                value=sec.section_script[:800]
                                + ("..." if len(sec.section_script or "") > 800 else ""),
                                height=100,
                                disabled=True,
                                label_visibility="collapsed",
                            )
                        if sec.audio_path and sec.audio_path.exists():
                            st.audio(str(sec.audio_path))

                        # Section images
                        sec_images = []
                        for plan in sec.segment_visual_plans:
                            sec_images.extend(
                                p for p in plan.image_paths if p.exists()
                            )
                        if sec_images:
                            img_cols = st.columns(min(4, len(sec_images)))
                            for j, img in enumerate(sec_images):
                                img_cols[j % len(img_cols)].image(
                                    str(img), use_container_width=True
                                )

                        if (
                            sec.section_video_path
                            and sec.section_video_path.exists()
                        ):
                            st.video(str(sec.section_video_path))

                        st.markdown("---")

            # Final video
            st.subheader("Final Video")
            if state.final_video_path and Path(state.final_video_path).exists():
                st.video(str(state.final_video_path))
                with open(state.final_video_path, "rb") as f:
                    st.download_button(
                        "Download Video",
                        data=f,
                        file_name=(
                            f"moceanai_v2_long_{topic[:30].replace(' ', '_')}.mp4"
                        ),
                        mime="video/mp4",
                        use_container_width=True,
                    )
            else:
                st.warning("No video file was produced.")

    else:
        st.info(
            "Configure your video on the left and click "
            "**Generate Long-Form Video** to begin."
        )
        st.markdown(
            """
            **V2 Long-Form Pipeline Improvements:**
            - **Deep Research** -- Multi-query web search grounds content in real facts
            - **Retention-Aware Outline** -- Section types, energy targets, retention devices
            - **Outline Quality Gate** -- Structure evaluated and revised automatically
            - **Parallel Processing** -- Audio, images, and clips for all sections at once
            - **Script Strategy Choice** -- Parallel (fast) or sequential (safe) writing
            - **Style Guide + Storyboard** -- Coherent visual language across all sections
            """
        )
