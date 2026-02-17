"""
Pydantic models for the ebook generation pipeline.

These models represent every stage of ebook creation:

  1. **EbookConfig** -- User-provided inputs (title, topic, audience, etc.)
  2. **Outline models** -- The structural blueprint (chapters and sections)
  3. **Content models** -- Written chapter text with sections
  4. **EbookState** -- Full pipeline state accumulating all generated data

The EbookState follows the same pattern as ShortFormState / LongFormState:
fields start as None and are populated step-by-step. If the pipeline fails
at any step, earlier fields are preserved in the PipelineError's partial_state.

To extend:
  - Add a new field to EbookConfig for a new user input, then read it
    in ebook_pipeline.py and pass it to the appropriate prompt.
  - Add a new LLM output model here if you need a new agent step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════
# USER INPUT
# ═══════════════════════════════════════════════════════════════════════════

class EbookConfig(BaseModel):
    """
    All user-provided settings for ebook generation.

    This is populated from the Streamlit UI form before the pipeline starts.
    """
    # --- Required fields ---
    title: str = Field(..., description="The ebook title displayed on the cover and header.")
    topic: str = Field(..., description="Detailed description of the ebook's subject matter.")
    target_audience: str = Field(..., description="Who this ebook is written for.")

    # --- Optional / defaulted fields ---
    subtitle: str = Field("", description="Subtitle shown below the title on the cover.")
    author_name: str = Field("MoceanAI", description="Author name for the cover and copyright page.")
    tone: str = Field("Professional", description="Writing tone (e.g., Professional, Conversational).")
    writing_style: str = Field(
        "Practical Guide",
        description=(
            "The overall writing approach. Options: 'Conversational', 'Academic', "
            "'Practical Guide', 'Narrative', 'Journalistic'."
        ),
    )
    num_chapters: int = Field(8, ge=3, le=20, description="Number of body chapters (excluding intro/conclusion).")
    model_provider: str = Field("google", description="LLM provider for all text generation.")
    image_provider: str = Field("google", description="Image generation provider for cover and section images.")
    image_style: str = Field("Cinematic", description="Art style for generated images.")
    include_images: bool = Field(True, description="Whether to generate images for chapter sections.")
    allow_faces: bool = Field(False, description="Whether generated images may include visible faces.")
    output_formats: list[str] = Field(
        default_factory=lambda: ["pdf"],
        description="List of output formats to render: 'pdf', 'docx', or both.",
    )
    additional_instructions: str = Field(
        "",
        description="Extra guidance: brand voice, things to avoid, specific topics to cover, etc.",
    )


# ═══════════════════════════════════════════════════════════════════════════
# LLM STRUCTURED OUTPUT MODELS — OUTLINE
# ═══════════════════════════════════════════════════════════════════════════

class SectionOutline(BaseModel):
    """One section within a chapter's outline."""
    section_title: str = Field(..., description="Descriptive title for this section.")
    section_brief: str = Field(
        ...,
        description="1-2 sentence summary of what this section covers and why it matters.",
    )


class ChapterOutline(BaseModel):
    """Outline for a single chapter, including its sections."""
    chapter_number: int = Field(..., description="1-indexed chapter number.")
    chapter_title: str = Field(..., description="The chapter's title.")
    chapter_purpose: str = Field(
        ...,
        description="2-3 sentence explanation of this chapter's role in the ebook.",
    )
    sections: list[SectionOutline] = Field(
        ...,
        description="Ordered list of sections within this chapter (typically 3-6).",
    )
    key_takeaway: str = Field(
        ...,
        description="The single most important thing the reader should learn from this chapter.",
    )


class EbookOutlineContainer(BaseModel):
    """LLM output: the full ebook outline with all chapters."""
    ebook_title: str = Field(..., description="Final ebook title (may be refined from user input).")
    ebook_subtitle: str = Field("", description="Refined subtitle.")
    chapters: list[ChapterOutline] = Field(..., description="Ordered list of chapter outlines.")


# ═══════════════════════════════════════════════════════════════════════════
# LLM STRUCTURED OUTPUT MODELS — CHAPTER CONTENT
# ═══════════════════════════════════════════════════════════════════════════

class SectionContent(BaseModel):
    """Written content for one section within a chapter."""
    section_title: str = Field(..., description="The section heading.")
    section_text: str = Field(
        ...,
        description=(
            "The full written prose for this section. Should be multiple paragraphs "
            "of natural, well-structured text."
        ),
    )


class ChapterContentContainer(BaseModel):
    """LLM output: the written content for one chapter."""
    chapter_title: str = Field(..., description="The chapter's title.")
    sections: list[SectionContent] = Field(..., description="Written sections in order.")
    chapter_summary: str = Field(
        ...,
        description=(
            "A 2-3 sentence summary of this chapter's key points. "
            "Used by subsequent chapters for continuity."
        ),
    )


class EditedChapterContainer(BaseModel):
    """LLM output: polished version of a chapter after editing."""
    sections: list[SectionContent] = Field(..., description="Edited sections in order.")


class IntroductionContainer(BaseModel):
    """LLM output: the ebook's introduction/preface."""
    introduction_text: str = Field(
        ..., description="Full text of the introduction."
    )


class ConclusionContainer(BaseModel):
    """LLM output: the ebook's conclusion/closing chapter."""
    conclusion_text: str = Field(
        ..., description="Full text of the conclusion."
    )


class CoverDescriptionContainer(BaseModel):
    """LLM output: a detailed image prompt for the cover."""
    cover_description: str = Field(
        ..., description="Exhaustively detailed image generation prompt for the ebook cover."
    )


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE STATE
# ═══════════════════════════════════════════════════════════════════════════

class ChapterState(BaseModel):
    """
    Tracks all generated data for a single chapter.

    Accumulates content through the pipeline steps:
      outline -> raw_content -> edited_content -> section_images
    """
    outline: ChapterOutline
    raw_sections: list[SectionContent] = Field(default_factory=list)
    raw_summary: str = ""
    edited_sections: list[SectionContent] = Field(default_factory=list)
    section_image_paths: list[Path] = Field(default_factory=list)


class EbookState(BaseModel):
    """
    Full pipeline state for ebook generation.

    Populated incrementally as each pipeline step completes.
    If the pipeline fails, all previously completed fields are preserved.
    """
    # --- Configuration (set before pipeline starts) ---
    config: EbookConfig

    # --- Generated outline ---
    outline: Optional[EbookOutlineContainer] = None

    # --- Introduction and conclusion ---
    introduction_text: Optional[str] = None
    conclusion_text: Optional[str] = None

    # --- Per-chapter state ---
    chapters: list[ChapterState] = Field(default_factory=list)

    # --- Cover ---
    cover_description: Optional[str] = None
    cover_image_path: Optional[Path] = None

    # --- Output files ---
    pdf_path: Optional[Path] = None
    docx_path: Optional[Path] = None
