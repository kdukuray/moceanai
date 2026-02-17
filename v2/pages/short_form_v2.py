"""
Short-Form Video Creator V2 Page.

Enhanced pipeline with:
  - Optional web research (Tavily)
  - Single-pass script generation
  - Quality gates (script evaluation with retry)
  - Global style guide + storyboard-based visual planning
  - Visual quality assessment

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
from v2.core.v2_models import ShortFormV2State

init_db()

st.title("Short-Form Video Creator V2")
st.markdown(
    "Enhanced pipeline with research, quality gates, "
    "and storyboard-based visual planning."
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
        placeholder="e.g., 5 credit score myths that are costing you money",
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
        placeholder="e.g., Young adults 18-30 interested in personal finance",
    )

    c3, c4 = st.columns(2)
    with c3:
        platform = st.selectbox("Platform", options=PLATFORMS, index=0)
    with c4:
        duration = st.number_input(
            "Duration (seconds)", min_value=15, max_value=300, value=60, step=5
        )

    orientation = st.selectbox(
        "Orientation", options=["Portrait", "Landscape"], index=0
    )

    st.markdown("---")

    # --- Research (V2 feature) ---
    st.subheader("Research")

    enable_research = st.toggle(
        "Enable web research",
        value=True,
        help="Uses Tavily to research the topic before writing the script. "
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

    image_style = st.selectbox("Image Style", options=IMAGE_STYLES, index=1)
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

    c7, c8, c9 = st.columns(3)
    with c7:
        add_subtitles = st.toggle("Burn-in subtitles", value=False)
    with c8:
        allow_faces = st.toggle("Allow faces in images", value=False)
    with c9:
        single_image = st.toggle(
            "One image per clip",
            value=False,
            help="Use a single image for each clip instead of multiple per ~3s",
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
        "Generate Video", type="primary", use_container_width=True
    )


# ---------------------------------------------------------------------------
# Partial results display
# ---------------------------------------------------------------------------
def _display_partial_results(state: ShortFormV2State) -> None:
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
                st.markdown(f"**Recommended Angle:** {brief.angle_recommendation}")

    if state.full_script:
        has_content = True
        with st.expander("Script (before error)", expanded=True):
            st.markdown(f"**Goal:** {state.full_script.goal}")
            st.markdown(f"**Hook:** {state.full_script.hook}")
            full_text = " ".join(b.raw_text for b in state.full_script.beats)
            st.text_area(
                "Script", value=full_text, height=200,
                disabled=True, label_visibility="collapsed",
            )

    if state.audio_path and state.audio_path.exists():
        has_content = True
        with st.expander("Audio (before error)", expanded=False):
            st.audio(str(state.audio_path))

    image_paths = []
    for plan in state.segment_visual_plans:
        image_paths.extend(p for p in plan.image_paths if p.exists())
    if image_paths:
        has_content = True
        with st.expander(f"Generated Images ({len(image_paths)})", expanded=False):
            cols = st.columns(min(4, len(image_paths)))
            for i, img in enumerate(image_paths):
                cols[i % len(cols)].image(str(img), use_container_width=True)

    clip_paths = [p for p in state.clip_paths if p and p.exists()]
    if clip_paths:
        has_content = True
        with st.expander(f"Animated Clips ({len(clip_paths)})", expanded=False):
            for clip in clip_paths:
                st.video(str(clip))

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

        state = ShortFormV2State(
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
            add_subtitles=add_subtitles,
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
        )

        progress_bar = st.progress(0.0, text="Starting V2 pipeline...")
        status_container = st.status("Generating video...", expanded=True)

        def on_progress(message: str, percent: float):
            progress_bar.progress(percent, text=message)
            status_container.write(message)

        from v2.pipeline.pipeline_runner_v2 import PipelineRunnerV2, PipelineV2Error

        pipeline_failed = False

        try:
            runner = PipelineRunnerV2(model_provider=model_provider)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                state = loop.run_until_complete(
                    runner.run_short_form_v2(state=state, on_progress=on_progress)
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

            # Script with beat annotations
            if state.full_script:
                with st.expander("Script", expanded=False):
                    st.markdown(f"**Goal:** {state.full_script.goal}")
                    st.markdown(f"**Hook:** {state.full_script.hook}")
                    st.markdown(f"**CTA:** {state.full_script.cta}")
                    st.markdown("---")
                    for i, beat in enumerate(state.full_script.beats):
                        energy_bar = "█" * beat.energy_level + "░" * (10 - beat.energy_level)
                        st.markdown(
                            f"**Beat {i+1}** "
                            f"`{beat.beat_type}` "
                            f"Energy: {energy_bar} ({beat.energy_level}/10)"
                        )
                        st.markdown(f"> {beat.raw_text}")
                        st.caption(f"Visual: {beat.visual_intent}")

            # Quality Report
            if state.quality_report:
                with st.expander("Quality Report", expanded=False):
                    qr = state.quality_report
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Hook", f"{qr.hook_score}/10")
                    c2.metric("Clarity", f"{qr.clarity_score}/10")
                    c3.metric("Engagement", f"{qr.engagement_score}/10")
                    c4.metric("CTA", f"{qr.cta_score}/10")
                    c5.metric("Pacing", f"{qr.pacing_score}/10")

                    if qr.passed:
                        st.success("Script passed quality gate.")
                    else:
                        st.warning(
                            f"Script did not pass quality gate "
                            f"(revised {state.script_revision_count} time(s))."
                        )
                    if qr.revision_notes:
                        st.markdown("**Revision Notes:**")
                        for n in qr.revision_notes:
                            st.markdown(f"- {n}")
                    if qr.factual_flags:
                        st.markdown("**Factual Flags:**")
                        for f in qr.factual_flags:
                            st.markdown(f"- {f}")

            # Style Guide
            if state.style_guide:
                with st.expander("Style Guide", expanded=False):
                    sg = state.style_guide
                    st.markdown(
                        f"**Colors:** {', '.join(sg.color_palette)}"
                    )
                    st.markdown(f"**Lighting:** {sg.lighting_direction}")
                    st.markdown(
                        f"**Composition:** {', '.join(sg.composition_rules)}"
                    )
                    st.markdown(f"**Texture:** {sg.texture_notes}")
                    st.markdown(
                        f"**Style Keywords:** {', '.join(sg.style_keywords)}"
                    )

            # Storyboard
            if state.storyboard:
                with st.expander("Storyboard", expanded=False):
                    for i, sb in enumerate(state.storyboard):
                        st.markdown(
                            f"**Segment {i+1}** "
                            f"(Energy: {sb.segment_energy}/10, "
                            f"{len(sb.shots)} shot(s))"
                        )
                        for j, shot in enumerate(sb.shots):
                            st.caption(
                                f"  Shot {j+1}: "
                                f"{shot.motion_type} ({shot.motion_speed}) | "
                                f"Transition: {shot.transition_in} | "
                                f"{shot.duration_ms}ms"
                            )
                            st.markdown(f"  > {shot.image_prompt[:120]}...")

            # Audio
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
                        file_name=f"moceanai_v2_{topic[:30].replace(' ', '_')}.mp4",
                        mime="video/mp4",
                        use_container_width=True,
                    )
            else:
                st.warning("No video file was produced.")

    else:
        st.info(
            "Configure your video on the left and click "
            "**Generate Video** to begin."
        )
        st.markdown(
            """
            **V2 Pipeline Improvements:**
            - **Research Phase** -- Grounds scripts in real, current facts via web search
            - **Single-Pass Script** -- One LLM call produces the full structured script
            - **Quality Gates** -- Script is evaluated and revised automatically
            - **Style Guide** -- Global visual style ensures image coherence
            - **Storyboard** -- Intentional motion and transitions per shot
            - **Visual QA** -- Images checked before animation
            """
        )
