"""
Ebook generation pipeline orchestrator.

Coordinates a multi-agent workflow to produce a professional ebook:

  Step 1: Generate outline (structure agent)
  Step 2: Write introduction (intro agent)
  Step 3: Write chapters sequentially (chapter writer agent, baton-pass continuity)
  Step 4: Write conclusion (conclusion agent)
  Step 5: Edit/polish chapters in parallel (editor agent)
  Step 6: Generate section images if enabled (reuses ImageService)
  Step 7: Generate cover image
  Step 8: Render output files (PDF and/or DOCX via ebook_formatter)

Error handling follows the same pattern as the video pipeline:
  - Every step is individually try/except guarded
  - State is checkpointed after every API call
  - On failure, PipelineError carries the partial state so the UI
    can display everything that was generated before the error

Architecture note:
  Chapters are written SEQUENTIALLY (step 3) because each chapter
  receives the previous chapter's summary for narrative continuity.
  Editing (step 5) runs in PARALLEL because each chapter is independent
  at that stage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from v2.core.config import OUTPUT_DIR, IMAGE_DIR
from v2.core.ebook_models import (
    EbookState,
    EbookConfig,
    ChapterState,
    ChapterContentContainer,
    EditedChapterContainer,
    EbookOutlineContainer,
    IntroductionContainer,
    ConclusionContainer,
    CoverDescriptionContainer,
    SectionContent,
)
from v2.core.ebook_prompts import (
    EBOOK_OUTLINE_PROMPT,
    EBOOK_INTRODUCTION_PROMPT,
    EBOOK_CHAPTER_WRITER_PROMPT,
    EBOOK_CONCLUSION_PROMPT,
    EBOOK_EDITOR_PROMPT,
    EBOOK_COVER_DESCRIPTION_PROMPT,
    EBOOK_SECTION_IMAGE_PROMPT,
)
from v2.pipeline.pipeline_runner import PipelineError, _save_checkpoint
from v2.services.llm_service import LLMService
from v2.services.image_service import ImageService

logger = logging.getLogger(__name__)

# Type alias for progress callback: (message, percent 0.0-1.0)
ProgressCallback = Optional[Callable[[str, float], None]]

# Checkpoint directory for ebook-specific checkpoints
EBOOK_CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints" / "ebooks"
EBOOK_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def _save_ebook_checkpoint(state: EbookState, label: str) -> Optional[Path]:
    """
    Save an ebook pipeline checkpoint to disk.

    Writes the current state as JSON so that if a later step fails,
    all previously generated content (outline, chapters, images) is preserved.
    """
    try:
        safe_label = label.replace(" ", "_").replace("/", "-")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = EBOOK_CHECKPOINT_DIR / f"{ts}_{safe_label}.json"
        path.write_text(
            state.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.debug(f"Ebook checkpoint saved: {path.name}")
        return path
    except Exception as e:
        logger.warning(f"Ebook checkpoint write failed ({label}): {e}")
        return None


class EbookPipeline:
    """
    Orchestrates the full ebook generation workflow.

    Usage:
        pipeline = EbookPipeline(model_provider="google")
        state = await pipeline.run(state, on_progress=callback)
    """

    def __init__(self, model_provider: str = "google"):
        """
        Initialize with all required sub-services.

        Args:
            model_provider: Which LLM provider for text generation
                            ("google", "openai", "anthropic", "xai", "deepseek").
        """
        self.llm = LLMService(provider=model_provider)
        self.image_service = ImageService()

    async def run(
        self,
        state: EbookState,
        on_progress: ProgressCallback = None,
    ) -> EbookState:
        """
        Run the complete ebook generation pipeline.

        Args:
            state: EbookState with config populated.
            on_progress: Optional callback(message, percent) for UI updates.

        Returns:
            Fully populated EbookState with output file paths.

        Raises:
            PipelineError: On any step failure, with partial_state attached.
        """
        config = state.config

        def _progress(msg: str, pct: float = 0.0):
            if on_progress:
                on_progress(msg, pct)
            logger.info(f"[{pct:.0%}] {msg}")

        def _fail(step_name: str, error: Exception) -> None:
            logger.error(f"Ebook pipeline failed at '{step_name}': {error}")
            logger.error(traceback.format_exc())
            _save_ebook_checkpoint(state, f"FAILED_{step_name}")
            raise PipelineError(step_name, state, error)

        # ─── Step 1: Generate outline ────────────────────────────────
        try:
            _progress("Generating ebook outline...", 0.05)
            outline = self.llm.generate_structured(
                system_prompt=EBOOK_OUTLINE_PROMPT,
                user_payload={
                    "title": config.title,
                    "subtitle": config.subtitle,
                    "topic": config.topic,
                    "target_audience": config.target_audience,
                    "tone": config.tone,
                    "writing_style": config.writing_style,
                    "num_chapters": config.num_chapters,
                    "additional_instructions": config.additional_instructions,
                },
                output_model=EbookOutlineContainer,
            )
            state.outline = outline

            # Initialize per-chapter state from the outline
            state.chapters = [
                ChapterState(outline=ch)
                for ch in outline.chapters
            ]
            _save_ebook_checkpoint(state, "after_outline")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_outline", e)

        num_chapters = len(state.chapters)

        # ─── Step 2: Write introduction ──────────────────────────────
        try:
            _progress("Writing introduction...", 0.10)
            chapter_titles = [ch.outline.chapter_title for ch in state.chapters]
            intro_result = self.llm.generate_structured(
                system_prompt=EBOOK_INTRODUCTION_PROMPT,
                user_payload={
                    "title": state.outline.ebook_title,
                    "subtitle": state.outline.ebook_subtitle,
                    "topic": config.topic,
                    "target_audience": config.target_audience,
                    "tone": config.tone,
                    "writing_style": config.writing_style,
                    "chapter_titles": chapter_titles,
                    "additional_instructions": config.additional_instructions,
                },
                output_model=IntroductionContainer,
            )
            state.introduction_text = intro_result.introduction_text
            _save_ebook_checkpoint(state, "after_introduction")
        except PipelineError:
            raise
        except Exception as e:
            _fail("write_introduction", e)

        # ─── Step 3: Write chapters (sequential for continuity) ──────
        # Each chapter receives the previous chapter's summary so it can
        # pick up where the last one left off ("baton pass" pattern).
        all_chapter_titles = [ch.outline.chapter_title for ch in state.chapters]
        previous_summary = ""

        for ch_idx, chapter in enumerate(state.chapters):
            try:
                _progress(
                    f"Writing chapter {ch_idx + 1}/{num_chapters}: "
                    f"{chapter.outline.chapter_title}...",
                    0.12 + (ch_idx / num_chapters) * 0.40,
                )

                chapter_result = self.llm.generate_structured(
                    system_prompt=EBOOK_CHAPTER_WRITER_PROMPT,
                    user_payload={
                        "ebook_title": state.outline.ebook_title,
                        "target_audience": config.target_audience,
                        "tone": config.tone,
                        "writing_style": config.writing_style,
                        "chapter_outline": chapter.outline.model_dump(),
                        "previous_chapter_summary": previous_summary,
                        "full_outline_context": json.dumps(all_chapter_titles),
                        "additional_instructions": config.additional_instructions,
                    },
                    output_model=ChapterContentContainer,
                )

                chapter.raw_sections = chapter_result.sections
                chapter.raw_summary = chapter_result.chapter_summary
                previous_summary = chapter_result.chapter_summary

                _save_ebook_checkpoint(state, f"after_chapter_{ch_idx + 1}")
            except PipelineError:
                raise
            except Exception as e:
                _fail(f"write_chapter_{ch_idx + 1}", e)

        # ─── Step 4: Write conclusion ────────────────────────────────
        try:
            _progress("Writing conclusion...", 0.55)
            all_summaries = [ch.raw_summary for ch in state.chapters]
            conclusion_result = self.llm.generate_structured(
                system_prompt=EBOOK_CONCLUSION_PROMPT,
                user_payload={
                    "title": state.outline.ebook_title,
                    "topic": config.topic,
                    "target_audience": config.target_audience,
                    "tone": config.tone,
                    "writing_style": config.writing_style,
                    "chapter_summaries": all_summaries,
                    "additional_instructions": config.additional_instructions,
                },
                output_model=ConclusionContainer,
            )
            state.conclusion_text = conclusion_result.conclusion_text
            _save_ebook_checkpoint(state, "after_conclusion")
        except PipelineError:
            raise
        except Exception as e:
            _fail("write_conclusion", e)

        # ─── Step 5: Edit/polish chapters (parallel) ─────────────────
        try:
            _progress("Editing and polishing chapters...", 0.60)
            edit_tasks = []

            async with asyncio.TaskGroup() as tg:
                for ch_idx, chapter in enumerate(state.chapters):
                    # Provide surrounding chapter context for transition polish
                    prev_summary = (
                        state.chapters[ch_idx - 1].raw_summary
                        if ch_idx > 0 else ""
                    )
                    next_summary = (
                        state.chapters[ch_idx + 1].raw_summary
                        if ch_idx < num_chapters - 1 else ""
                    )

                    task = tg.create_task(
                        asyncio.to_thread(
                            self._edit_chapter,
                            chapter_title=chapter.outline.chapter_title,
                            sections=chapter.raw_sections,
                            prev_summary=prev_summary,
                            next_summary=next_summary,
                            tone=config.tone,
                            writing_style=config.writing_style,
                        )
                    )
                    edit_tasks.append((ch_idx, task))

            for ch_idx, task in edit_tasks:
                state.chapters[ch_idx].edited_sections = task.result()

            _save_ebook_checkpoint(state, "after_editing")
        except PipelineError:
            raise
        except Exception as e:
            _fail("edit_chapters", e)

        # ─── Step 6: Generate section images (if enabled, parallel) ──
        if config.include_images:
            try:
                _progress("Generating section images...", 0.72)
                await self._generate_section_images(state)
                _save_ebook_checkpoint(state, "after_section_images")
            except PipelineError:
                raise
            except Exception as e:
                _fail("generate_section_images", e)

        # ─── Step 7: Generate cover image ────────────────────────────
        try:
            _progress("Generating cover image...", 0.82)
            cover_desc_result = self.llm.generate_structured(
                system_prompt=EBOOK_COVER_DESCRIPTION_PROMPT,
                user_payload={
                    "title": state.outline.ebook_title,
                    "subtitle": state.outline.ebook_subtitle,
                    "topic": config.topic,
                    "tone": config.tone,
                    "image_style": config.image_style,
                    "allow_faces": config.allow_faces,
                },
                output_model=CoverDescriptionContainer,
            )
            state.cover_description = cover_desc_result.cover_description

            # Generate the actual cover image
            cover_paths = await self.image_service.generate_images(
                descriptions=[state.cover_description],
                provider=config.image_provider,
                orientation="portrait",
            )
            if cover_paths:
                state.cover_image_path = cover_paths[0]

            _save_ebook_checkpoint(state, "after_cover")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_cover", e)

        # ─── Step 8: Render output files ─────────────────────────────
        try:
            _progress("Rendering output files...", 0.90)

            # Import here to avoid circular dependency and so weasyprint/docx
            # are only required when actually rendering
            from v2.pipeline.ebook_formatter import render_pdf, render_docx

            if "pdf" in config.output_formats:
                _progress("Rendering PDF...", 0.92)
                state.pdf_path = render_pdf(state)

            if "docx" in config.output_formats:
                _progress("Rendering DOCX...", 0.96)
                state.docx_path = render_docx(state)

            _save_ebook_checkpoint(state, "complete")
        except PipelineError:
            raise
        except Exception as e:
            _fail("render_output", e)

        _progress("Ebook generation complete!", 1.0)
        return state

    # ------------------------------------------------------------------
    # Private helper methods
    # ------------------------------------------------------------------

    def _edit_chapter(
        self,
        chapter_title: str,
        sections: list[SectionContent],
        prev_summary: str,
        next_summary: str,
        tone: str,
        writing_style: str,
    ) -> list[SectionContent]:
        """
        Edit a single chapter via the editor agent LLM call.
        Called in a thread from the parallel editing step.
        """
        result = self.llm.generate_structured(
            system_prompt=EBOOK_EDITOR_PROMPT,
            user_payload={
                "chapter_title": chapter_title,
                "sections": [s.model_dump() for s in sections],
                "previous_chapter_summary": prev_summary,
                "next_chapter_summary": next_summary,
                "tone": tone,
                "writing_style": writing_style,
            },
            output_model=EditedChapterContainer,
        )
        return result.sections

    async def _generate_section_images(self, state: EbookState) -> None:
        """
        Generate one image per chapter (for the first section of each chapter).

        Uses the existing ImageService for generation. Each chapter gets one
        image based on its first section's content.
        """
        config = state.config

        # Build image prompts for each chapter's first section
        from v2.core.ebook_models import CoverDescriptionContainer as _CDummyImport  # noqa

        image_tasks = []
        chapters_needing_images = []

        async with asyncio.TaskGroup() as tg:
            for ch_idx, chapter in enumerate(state.chapters):
                # Use edited sections if available, else raw
                sections = chapter.edited_sections or chapter.raw_sections
                if not sections:
                    continue

                first_section = sections[0]
                # Generate a description via LLM for this section's image
                prompt_payload = {
                    "section_title": first_section.section_title,
                    "section_text_excerpt": first_section.section_text[:200],
                    "ebook_topic": config.topic,
                    "image_style": config.image_style,
                    "allow_faces": config.allow_faces,
                }

                task = tg.create_task(
                    asyncio.to_thread(
                        self._generate_section_image_description,
                        prompt_payload,
                    )
                )
                image_tasks.append((ch_idx, task))
                chapters_needing_images.append(ch_idx)

        # Now generate the actual images from the descriptions
        image_descriptions = []
        chapter_indices = []
        for ch_idx, task in image_tasks:
            desc = task.result()
            if desc:
                image_descriptions.append(desc)
                chapter_indices.append(ch_idx)

        if image_descriptions:
            image_paths = await self.image_service.generate_images(
                descriptions=image_descriptions,
                provider=config.image_provider,
                orientation="landscape",  # Landscape works better for ebook images
            )
            for i, ch_idx in enumerate(chapter_indices):
                if i < len(image_paths):
                    state.chapters[ch_idx].section_image_paths = [image_paths[i]]

    def _generate_section_image_description(self, payload: dict) -> str:
        """Generate a single section image description via LLM."""
        from v2.core.ebook_prompts import EBOOK_SECTION_IMAGE_PROMPT

        # Use a simple Pydantic model for the response
        from pydantic import BaseModel, Field

        class _ImageDescResult(BaseModel):
            image_description: str = Field(...)

        result = self.llm.generate_structured(
            system_prompt=EBOOK_SECTION_IMAGE_PROMPT,
            user_payload=payload,
            output_model=_ImageDescResult,
        )
        return result.image_description
