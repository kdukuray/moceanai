"""
Ebook Creator Page.

Two-column layout: configuration on the left, results on the right.
Generates professional ebooks with AI-written chapters, optional images,
and outputs in PDF and/or DOCX format.

Error handling: catches PipelineError and displays the partial state
(outline, completed chapters, images) that was generated before the
failure, so you never lose work from paid API calls.
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
    TONES,
)
from v2.core.database import init_db
from v2.core.ebook_models import EbookConfig, EbookState

init_db()

# Writing style options for the ebook
WRITING_STYLES = [
    "Practical Guide",
    "Conversational",
    "Academic",
    "Narrative",
    "Journalistic",
]

st.title("Ebook Creator")
st.markdown("Generate professional ebooks with AI-powered writing, editing, and formatting.")

# ---------------------------------------------------------------------------
# Layout: Config (left) | Output (right)
# ---------------------------------------------------------------------------
col_config, col_output = st.columns([1, 1], gap="large")

with col_config:
    st.subheader("Ebook Details")

    title = st.text_input(
        "Title *",
        placeholder="e.g., The Complete Guide to Personal Finance in Your 20s",
        key="eb_title",
    )
    subtitle = st.text_input(
        "Subtitle",
        placeholder="e.g., Build Wealth, Crush Debt, and Live Your Best Life",
        key="eb_subtitle",
    )
    author_name = st.text_input(
        "Author Name",
        value="MoceanAI",
        key="eb_author",
    )

    topic = st.text_area(
        "Topic / Subject Matter *",
        placeholder=(
            "Describe what this ebook should cover in detail. The more context you "
            "provide, the better the output. Include key themes, specific areas to "
            "cover, the problem it solves, and any unique angle you want."
        ),
        height=120,
        key="eb_topic",
    )

    target_audience = st.text_input(
        "Target Audience *",
        placeholder="e.g., College graduates and young professionals aged 22-30",
        key="eb_audience",
    )

    st.markdown("---")
    st.subheader("Style & Structure")

    c1, c2 = st.columns(2)
    with c1:
        tone = st.selectbox("Tone", options=TONES, index=2, key="eb_tone")  # Professional
    with c2:
        writing_style = st.selectbox("Writing Style", options=WRITING_STYLES, index=0, key="eb_style")

    num_chapters = st.slider(
        "Number of Chapters",
        min_value=3,
        max_value=20,
        value=8,
        step=1,
        help="Body chapters only (introduction and conclusion are added automatically).",
        key="eb_chapters",
    )

    st.markdown("---")
    st.subheader("Models & Images")

    c3, c4 = st.columns(2)
    with c3:
        model_provider = st.selectbox(
            "LLM Provider",
            options=["google", "openai", "anthropic", "xai"],
            index=0,
            key="eb_llm",
        )
    with c4:
        image_provider = st.selectbox(
            "Image Provider",
            options=["google", "openai", "flux"],
            index=0,
            key="eb_img_provider",
        )

    image_style = st.selectbox(
        "Image Style",
        options=IMAGE_STYLES,
        index=7,  # Cinematic
        key="eb_img_style",
    )

    c5, c6 = st.columns(2)
    with c5:
        include_images = st.toggle(
            "Include section images",
            value=True,
            help="Generate one illustration per chapter.",
            key="eb_include_images",
        )
    with c6:
        allow_faces = st.toggle(
            "Allow faces in images",
            value=False,
            key="eb_allow_faces",
        )

    st.markdown("---")
    st.subheader("Output Format")

    c7, c8 = st.columns(2)
    with c7:
        output_pdf = st.checkbox("PDF", value=True, key="eb_pdf")
    with c8:
        output_docx = st.checkbox("DOCX (Word)", value=False, key="eb_docx")

    additional_instructions = st.text_area(
        "Additional Instructions",
        placeholder=(
            "Brand voice guidelines, specific topics to include or avoid, "
            "target page count, any special requirements..."
        ),
        height=80,
        key="eb_instructions",
    )

    # Generate button
    generate = st.button(
        "Generate Ebook",
        type="primary",
        use_container_width=True,
        key="eb_generate",
    )


# ---------------------------------------------------------------------------
# Helper: display partial ebook results on failure
# ---------------------------------------------------------------------------
def _display_partial_ebook(state: EbookState) -> None:
    """Show whatever was generated before the pipeline failed."""
    has_content = False

    # Outline
    if state.outline:
        has_content = True
        with st.expander("Ebook Outline (generated before error)", expanded=True):
            st.markdown(f"**Title:** {state.outline.ebook_title}")
            if state.outline.ebook_subtitle:
                st.markdown(f"**Subtitle:** {state.outline.ebook_subtitle}")
            for ch in state.outline.chapters:
                st.markdown(f"**Ch {ch.chapter_number}: {ch.chapter_title}**")
                st.caption(ch.chapter_purpose)

    # Introduction
    if state.introduction_text:
        has_content = True
        with st.expander("Introduction", expanded=False):
            st.text_area(
                "Intro", value=state.introduction_text, height=200,
                disabled=True, label_visibility="collapsed",
                key="partial_intro",
            )

    # Completed chapters
    completed_chapters = [
        (i, ch) for i, ch in enumerate(state.chapters)
        if ch.raw_sections or ch.edited_sections
    ]
    if completed_chapters:
        has_content = True
        with st.expander(f"Completed Chapters ({len(completed_chapters)})", expanded=False):
            for i, ch in completed_chapters:
                sections = ch.edited_sections or ch.raw_sections
                st.markdown(f"### Chapter {i + 1}: {ch.outline.chapter_title}")
                for sec in sections:
                    st.markdown(f"**{sec.section_title}**")
                    st.text(sec.section_text[:300] + "...")
                st.markdown("---")

    # Cover image
    if state.cover_image_path and state.cover_image_path.exists():
        has_content = True
        st.image(str(state.cover_image_path), caption="Generated cover image", width=300)

    if not has_content:
        st.info("No partial results were generated before the error.")


# ---------------------------------------------------------------------------
# Output column
# ---------------------------------------------------------------------------
with col_output:
    if generate:
        # Validation
        if not title:
            st.error("Please enter an ebook title.")
            st.stop()
        if not topic:
            st.error("Please describe the ebook topic.")
            st.stop()
        if not target_audience:
            st.error("Please specify the target audience.")
            st.stop()
        if not output_pdf and not output_docx:
            st.error("Please select at least one output format (PDF or DOCX).")
            st.stop()

        # Build output formats list
        output_formats = []
        if output_pdf:
            output_formats.append("pdf")
        if output_docx:
            output_formats.append("docx")

        # Build config and state
        config = EbookConfig(
            title=title,
            subtitle=subtitle or "",
            author_name=author_name or "MoceanAI",
            topic=topic,
            target_audience=target_audience,
            tone=tone,
            writing_style=writing_style,
            num_chapters=num_chapters,
            model_provider=model_provider,
            image_provider=image_provider,
            image_style=image_style,
            include_images=include_images,
            allow_faces=allow_faces,
            output_formats=output_formats,
            additional_instructions=additional_instructions or "",
        )
        state = EbookState(config=config)

        # Progress widgets
        progress_bar = st.progress(0.0, text="Starting ebook pipeline...")
        status_container = st.status("Generating ebook...", expanded=True)

        def on_progress(message: str, percent: float):
            progress_bar.progress(percent, text=message)
            status_container.write(message)

        from v2.pipeline.ebook_pipeline import EbookPipeline
        from v2.pipeline.pipeline_runner import PipelineError

        pipeline_failed = False

        try:
            pipeline = EbookPipeline(model_provider=model_provider)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                state = loop.run_until_complete(
                    pipeline.run(state=state, on_progress=on_progress)
                )
            finally:
                loop.close()

            status_container.update(label="Ebook generation complete!", state="complete")

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
            _display_partial_ebook(state)
        else:
            # Outline preview
            if state.outline:
                with st.expander("Ebook Outline", expanded=False):
                    st.markdown(f"**{state.outline.ebook_title}**")
                    if state.outline.ebook_subtitle:
                        st.caption(state.outline.ebook_subtitle)
                    for ch in state.outline.chapters:
                        st.markdown(f"- **Ch {ch.chapter_number}: {ch.chapter_title}** -- {ch.key_takeaway}")

            # Cover image
            if state.cover_image_path and state.cover_image_path.exists():
                with st.expander("Cover Image", expanded=False):
                    st.image(str(state.cover_image_path), width=300)

            # Chapter previews
            with st.expander("Chapter Previews", expanded=False):
                for i, ch in enumerate(state.chapters):
                    sections = ch.edited_sections or ch.raw_sections
                    if sections:
                        st.markdown(f"### Chapter {i + 1}: {ch.outline.chapter_title}")
                        # Show first section preview
                        st.text(sections[0].section_text[:500] + "...")
                        st.markdown("---")

            # Download buttons
            st.subheader("Download")

            dl_cols = st.columns(len(output_formats))
            col_idx = 0

            if state.pdf_path and state.pdf_path.exists():
                with dl_cols[col_idx]:
                    with open(state.pdf_path, "rb") as f:
                        st.download_button(
                            "Download PDF",
                            data=f,
                            file_name=f"{title[:40].replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            key="dl_pdf",
                        )
                    st.caption(f"PDF: {state.pdf_path.stat().st_size // 1024} KB")
                col_idx += 1

            if state.docx_path and state.docx_path.exists():
                with dl_cols[min(col_idx, len(dl_cols) - 1)]:
                    with open(state.docx_path, "rb") as f:
                        st.download_button(
                            "Download DOCX",
                            data=f,
                            file_name=f"{title[:40].replace(' ', '_')}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                            key="dl_docx",
                        )
                    st.caption(f"DOCX: {state.docx_path.stat().st_size // 1024} KB")

    else:
        st.info("Configure your ebook on the left and click **Generate Ebook** to begin.")
        st.markdown("""
        **What this creates:**
        - A structured ebook with introduction, body chapters, and conclusion
        - Each chapter is written by a specialized AI agent for quality
        - A separate editing pass polishes the full text for cohesion
        - Professional PDF with cover, table of contents, and styled typography
        - Optional DOCX output for further editing in Word/Google Docs
        - Optional AI-generated illustrations for each chapter

        **Typical generation time:** 5-20 minutes depending on chapter count and model.
        """)
