"""
UGC Product Video Creator Page.

Generates realistic user-generated content (UGC) style product review videos.
The user uploads product images and description, optionally provides reference
videos for style inspiration, and the pipeline produces a natural-sounding
review video with the product placed in realistic environments.

Two-column layout: configuration on the left, results on the right.
Real-time progress tracking with st.progress() and st.status().

Error handling: catches PipelineError and displays partial state (script,
audio, images, clips) generated before the failure.
"""

import sys
import asyncio
import uuid
from pathlib import Path

# Ensure the project root is importable
_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st

from v2.core.config import (
    TONES,
    PLATFORMS,
    VOICE_ACTOR_NAMES,
    VISUAL_MODES,
    VIDEO_PROVIDERS,
    OUTPUT_DIR,
)
from v2.core.database import init_db
from v2.core.ugc_models import UGCConfig, UGCState

init_db()

# Directory for saving uploaded files (product images and reference videos)
UGC_UPLOAD_DIR = OUTPUT_DIR / "ugc_uploads"
UGC_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

st.title("UGC Product Video Creator")
st.markdown(
    "Generate realistic product review videos from product images and descriptions. "
    "Upload product photos, paste the listing description, and get a UGC-style review video."
)

# ---------------------------------------------------------------------------
# Layout: Config (left) | Output (right)
# ---------------------------------------------------------------------------
col_config, col_output = st.columns([1, 1], gap="large")

with col_config:
    # --- Product Info ---
    st.subheader("Product Information")

    product_name = st.text_input(
        "Product Name *",
        placeholder="e.g., NovaCool Portable Mini Fan",
        key="ugc_name",
    )

    product_description = st.text_area(
        "Product Description *",
        placeholder=(
            "Paste the product listing description from Amazon, TikTok Shop, "
            "or any website. Include features, specs, and selling points."
        ),
        height=150,
        key="ugc_desc",
    )

    product_images = st.file_uploader(
        "Product Images * (multiple angles recommended)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        help="Upload product photos from different angles. These are analyzed so the AI knows exactly what the product looks like.",
        key="ugc_images",
    )

    st.markdown("---")

    # --- Reference Content (optional) ---
    st.subheader("Reference Content (Optional)")

    reference_videos = st.file_uploader(
        "Reference Videos (max 3)",
        type=["mp4", "mov", "webm"],
        accept_multiple_files=True,
        help=(
            "Upload viral/successful UGC videos for style inspiration. "
            "Gemini AI will analyze their hook, pacing, tone, and shot types "
            "to guide your video's script and structure."
        ),
        key="ugc_ref_videos",
    )
    if reference_videos and len(reference_videos) > 3:
        st.warning("Only the first 3 reference videos will be analyzed.")

    script_guidance = st.text_area(
        "Script Guidance",
        placeholder=(
            "Optional: tell the AI what to focus on in the review. "
            "e.g., 'Focus on the battery life and portability. Mention it fits in a purse.'"
        ),
        height=80,
        key="ugc_guidance",
    )

    st.markdown("---")

    # --- Video Settings ---
    st.subheader("Video Settings")

    c1, c2 = st.columns(2)
    with c1:
        platform = st.selectbox("Platform", options=PLATFORMS, index=0, key="ugc_platform")
    with c2:
        duration = st.slider(
            "Duration (seconds)", min_value=15, max_value=120, value=30, step=5,
            key="ugc_duration",
        )

    c3, c4 = st.columns(2)
    with c3:
        orientation = st.selectbox(
            "Orientation", options=["Portrait", "Landscape"], index=0, key="ugc_orient",
        )
    with c4:
        tone = st.selectbox("Tone", options=TONES, index=1, key="ugc_tone")  # Conversational

    voice_actor = st.selectbox(
        "Voice Actor", options=VOICE_ACTOR_NAMES, index=7, key="ugc_voice",
    )  # american_female_media_influencer

    st.markdown("---")

    # --- Visual Mode & Models ---
    st.subheader("Visual Mode & Models")

    visual_mode = st.radio(
        "How to create video clips",
        options=VISUAL_MODES,
        index=0,
        format_func=lambda x: {
            "zoompan": "Zoompan (image + camera motion) -- fast & cheap",
            "video_gen": "AI Video Generation (Runway/Luma/Kling) -- higher quality",
        }.get(x, x),
        horizontal=True,
        key="ugc_vis_mode",
    )

    video_provider = "runway"
    if visual_mode == "video_gen":
        video_provider = st.selectbox(
            "Video Provider", options=VIDEO_PROVIDERS, index=0, key="ugc_vid_prov",
        )

    c5, c6 = st.columns(2)
    with c5:
        model_provider = st.selectbox(
            "LLM Provider", options=["google", "openai", "anthropic", "xai"],
            index=0, key="ugc_llm",
        )
    with c6:
        image_provider = st.selectbox(
            "Image Provider", options=["google", "openai", "flux"],
            index=0, key="ugc_img_prov",
        )

    st.markdown("---")

    # --- Toggles ---
    st.subheader("Options")

    c7, c8, c9 = st.columns(3)
    with c7:
        allow_faces = st.toggle("Allow faces", value=False, key="ugc_faces")
    with c8:
        simple_scenes = st.toggle(
            "Simple scenes",
            value=True,
            help="Keep scenes static/minimal movement for better video gen results.",
            key="ugc_simple",
        )
    with c9:
        enhance_tts = st.toggle("Enhance for TTS", value=True, key="ugc_tts")

    # --- Generate button ---
    generate = st.button(
        "Generate UGC Video", type="primary", use_container_width=True, key="ugc_gen",
    )


# ---------------------------------------------------------------------------
# Helper: save uploaded files to disk and return paths
# ---------------------------------------------------------------------------
def _save_uploaded_files(uploaded_files, subdir: str) -> list[Path]:
    """
    Save Streamlit UploadedFile objects to disk with UUID filenames.

    Args:
        uploaded_files: List of Streamlit UploadedFile objects.
        subdir: Subdirectory under UGC_UPLOAD_DIR (e.g., "images", "videos").

    Returns:
        List of Paths to the saved files on disk.
    """
    save_dir = UGC_UPLOAD_DIR / subdir
    save_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for uf in uploaded_files:
        # Preserve the original extension
        ext = Path(uf.name).suffix or ".bin"
        dest = save_dir / f"{uuid.uuid4().hex}{ext}"
        dest.write_bytes(uf.getbuffer())
        paths.append(dest)
    return paths


# ---------------------------------------------------------------------------
# Helper: display partial UGC results on failure
# ---------------------------------------------------------------------------
def _display_partial_ugc(state: UGCState) -> None:
    """Show whatever was generated before the pipeline failed."""
    has_content = False

    # Reference analyses
    if state.reference_analyses:
        has_content = True
        with st.expander(
            f"Reference Video Analysis ({len(state.reference_analyses)} videos)",
            expanded=False,
        ):
            for i, analysis in enumerate(state.reference_analyses):
                st.markdown(f"**Video {i + 1}**")
                st.json(analysis.model_dump())

    # Product description
    if state.product_visual_description:
        has_content = True
        with st.expander("Product Visual Description", expanded=False):
            st.text(state.product_visual_description[:1000])

    # Script
    if state.script:
        has_content = True
        with st.expander("Script (generated before error)", expanded=True):
            st.text_area(
                "Script", value=state.script, height=200,
                disabled=True, label_visibility="collapsed",
                key="partial_ugc_script",
            )

    # Audio
    if state.audio_path and state.audio_path.exists():
        has_content = True
        with st.expander("Audio", expanded=False):
            st.audio(str(state.audio_path))

    # Scene images
    existing_images = [p for p in state.scene_image_paths if p.exists()]
    if existing_images:
        has_content = True
        with st.expander(f"Generated Images ({len(existing_images)})", expanded=False):
            cols = st.columns(min(4, len(existing_images)))
            for i, img in enumerate(existing_images):
                cols[i % len(cols)].image(str(img), use_container_width=True)

    # Video clips
    existing_clips = [p for p in state.clip_paths if p and p.exists()]
    if existing_clips:
        has_content = True
        with st.expander(f"Video Clips ({len(existing_clips)})", expanded=False):
            for clip in existing_clips:
                st.video(str(clip))

    if not has_content:
        st.info("No partial results were generated before the error.")


# ---------------------------------------------------------------------------
# Output column
# ---------------------------------------------------------------------------
with col_output:
    if generate:
        # --- Validation ---
        if not product_name:
            st.error("Please enter a product name.")
            st.stop()
        if not product_description:
            st.error("Please paste the product description.")
            st.stop()
        if not product_images:
            st.error("Please upload at least one product image.")
            st.stop()

        # --- Save uploaded files to disk ---
        product_image_paths = _save_uploaded_files(product_images, "images")

        reference_video_paths = []
        if reference_videos:
            reference_video_paths = _save_uploaded_files(
                reference_videos[:3], "videos"
            )

        # --- Build config and state ---
        config = UGCConfig(
            product_name=product_name,
            product_description=product_description,
            product_image_paths=product_image_paths,
            reference_video_paths=reference_video_paths,
            script_guidance=script_guidance or "",
            voice_actor=voice_actor,
            tone=tone,
            platform=platform,
            duration_seconds=int(duration),
            orientation=orientation,
            model_provider=model_provider,
            image_provider=image_provider,
            video_provider=video_provider,
            visual_mode=visual_mode,
            allow_faces=allow_faces,
            simple_scenes=simple_scenes,
            enhance_for_tts=enhance_tts,
        )
        state = UGCState(config=config)

        # --- Progress widgets ---
        progress_bar = st.progress(0.0, text="Starting UGC pipeline...")
        status_container = st.status("Generating UGC video...", expanded=True)

        def on_progress(message: str, percent: float):
            progress_bar.progress(percent, text=message)
            status_container.write(message)

        # --- Run pipeline ---
        from v2.pipeline.ugc_pipeline import UGCPipeline
        from v2.pipeline.pipeline_runner import PipelineError

        pipeline_failed = False

        try:
            pipeline = UGCPipeline(model_provider=model_provider)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                state = loop.run_until_complete(
                    pipeline.run(state=state, on_progress=on_progress)
                )
            finally:
                loop.close()

            status_container.update(label="UGC video complete!", state="complete")

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
            _display_partial_ugc(state)
        else:
            # Reference analysis (if provided)
            if state.reference_analyses:
                with st.expander(
                    f"Reference Video Analysis ({len(state.reference_analyses)} videos)",
                    expanded=False,
                ):
                    for i, analysis in enumerate(state.reference_analyses):
                        st.markdown(f"**Video {i + 1}**: {analysis.hook_style}")
                        st.caption(f"Tone: {analysis.tone} | Pacing: {analysis.pacing}")

            # Script
            with st.expander("Script", expanded=False):
                st.text_area(
                    "Review script", value=state.script or "", height=200,
                    disabled=True, label_visibility="collapsed",
                )

            # Audio player
            if state.audio_path and state.audio_path.exists():
                with st.expander("Audio", expanded=False):
                    st.audio(str(state.audio_path))

            # Scene images
            if state.scene_image_paths:
                existing = [p for p in state.scene_image_paths if p.exists()]
                if existing:
                    with st.expander(f"Generated Scenes ({len(existing)})", expanded=False):
                        cols = st.columns(min(4, len(existing)))
                        for i, img in enumerate(existing):
                            cols[i % len(cols)].image(str(img), use_container_width=True)

            # Final video
            st.subheader("Final Video")
            if state.final_video_path and Path(state.final_video_path).exists():
                st.video(str(state.final_video_path))

                with open(state.final_video_path, "rb") as f:
                    st.download_button(
                        "Download Video",
                        data=f,
                        file_name=f"ugc_{product_name[:30].replace(' ', '_')}.mp4",
                        mime="video/mp4",
                        use_container_width=True,
                    )
            else:
                st.warning("No video file was produced.")

    else:
        st.info(
            "Upload product images and description on the left, "
            "then click **Generate UGC Video** to begin."
        )
        st.markdown("""
        **How it works:**
        1. Upload product photos from multiple angles
        2. Paste the product listing description
        3. Optionally upload reference videos for style inspiration
        4. The AI writes a natural review script, generates realistic scenes
           with your product, and assembles a UGC-style video

        **Tips for best results:**
        - Upload 3-5 product photos from different angles
        - Include the full product listing description with features
        - Use "Simple scenes" toggle for more reliable video generation
        - Reference videos help the AI match trending styles
        """)
