# Ebook Generation Pipeline

## Overview

Generates professional ebooks with AI-written chapters, optional illustrations, and publication-ready output in PDF and/or DOCX format. Uses a multi-agent approach where specialized LLM calls handle outlining, writing, and editing separately, with a "baton pass" continuity pattern between chapters.

**Entry point:** `v2/pipeline/ebook_pipeline.py` → `EbookPipeline.run()`  
**UI page:** `v2/pages/ebook.py`  
**State model:** `v2/core/ebook_models.py` → `EbookState`  
**Formatters:** `v2/pipeline/ebook_formatter.py` → `render_pdf()`, `render_docx()`

---

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INPUT (Streamlit UI)                   │
│                                                                 │
│  title, subtitle, author_name, topic, target_audience,          │
│  tone, writing_style, num_chapters, model_provider,             │
│  image_provider, image_style, include_images, allow_faces,      │
│  output_formats (pdf / docx / both), additional_instructions    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 1: GENERATE OUTLINE  (5%)                                  │
│                                                                  │
│  Service:  LLMService.generate_structured()                      │
│  Model:    LLM (Gemini / GPT / Claude)                           │
│  Prompt:   EBOOK_OUTLINE_PROMPT                                  │
│  Input:    title, subtitle, topic, target_audience, tone,        │
│            writing_style, num_chapters, additional_instructions  │
│  Output:   EbookOutlineContainer →                               │
│            state.outline (with ebook_title, ebook_subtitle)      │
│            state.chapters (list[ChapterState], one per chapter)  │
│                                                                  │
│  Each chapter outline contains:                                  │
│    chapter_number: 1                                             │
│    chapter_title: "Building Your Foundation"                     │
│    chapter_purpose: "Establishes core concepts..."               │
│    sections: [                                                   │
│      {title: "Why This Matters", brief: "Sets the stakes..."},  │
│      {title: "The Framework", brief: "Introduces the model..."} │
│    ]                                                             │
│    key_takeaway: "Start with the basics before..."              │
│                                                                  │
│  The LLM may refine the title/subtitle while staying true       │
│  to the user's intent.                                           │
│                                                                  │
│  ✓ Checkpoint: after_outline                                     │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 2: WRITE INTRODUCTION  (10%)                               │
│                                                                  │
│  Service:  LLMService.generate_structured()                      │
│  Model:    LLM                                                   │
│  Prompt:   EBOOK_INTRODUCTION_PROMPT                             │
│  Input:    title, subtitle, topic, target_audience, tone,        │
│            writing_style, chapter_titles (for preview),          │
│            additional_instructions                               │
│  Output:   IntroductionContainer → state.introduction_text (str) │
│                                                                  │
│  400-700 words: hooks the reader, establishes why the topic      │
│  matters, previews the journey without spoiling insights.        │
│                                                                  │
│  ✓ Checkpoint: after_introduction                                │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 3: WRITE CHAPTERS  (12% → 52%)  [SEQUENTIAL]              │
│                                                                  │
│  Service:  LLMService.generate_structured()  (one call per ch.)  │
│  Model:    LLM                                                   │
│  Prompt:   EBOOK_CHAPTER_WRITER_PROMPT                           │
│                                                                  │
│  SEQUENTIAL because each chapter receives the previous chapter's │
│  summary for narrative continuity ("baton pass" pattern).        │
│                                                                  │
│  For each chapter (i = 1 to N):                                  │
│    Input:  ebook_title, target_audience, tone, writing_style,    │
│            chapter_outline (sections, purpose, key_takeaway),    │
│            previous_chapter_summary,                             │
│            full_outline_context (all chapter titles),            │
│            additional_instructions                               │
│    Output: ChapterContentContainer →                             │
│            chapter.raw_sections (list[SectionContent])            │
│            chapter.raw_summary (str, 2-3 sentences)              │
│                                                                  │
│  Each SectionContent has:                                        │
│    section_title: "Why This Matters"                             │
│    section_text: "Full prose paragraphs..." (300-600 words)      │
│                                                                  │
│  The summary is passed to the NEXT chapter as context:           │
│                                                                  │
│    Ch 1 summary ──▶ Ch 2 input                                  │
│    Ch 2 summary ──▶ Ch 3 input                                  │
│    Ch 3 summary ──▶ Ch 4 input   ...and so on                   │
│                                                                  │
│  ✓ Checkpoint: after_chapter_{N} (after each)                    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 4: WRITE CONCLUSION  (55%)                                 │
│                                                                  │
│  Service:  LLMService.generate_structured()                      │
│  Model:    LLM                                                   │
│  Prompt:   EBOOK_CONCLUSION_PROMPT                               │
│  Input:    title, topic, target_audience, tone, writing_style,   │
│            chapter_summaries (all of them)                       │
│  Output:   ConclusionContainer → state.conclusion_text (str)     │
│                                                                  │
│  400-600 words: synthesizes key themes, reinforces               │
│  transformation, provides next steps, empowering close.          │
│                                                                  │
│  ✓ Checkpoint: after_conclusion                                  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 5: EDIT CHAPTERS  (60%)  [PARALLEL]                        │
│                                                                  │
│  Service:  LLMService.generate_structured()                      │
│  Model:    LLM (one call per chapter, all run in parallel)       │
│  Prompt:   EBOOK_EDITOR_PROMPT                                   │
│  Input:    chapter_title, raw sections,                          │
│            previous_chapter_summary (for transition context),    │
│            next_chapter_summary (for forward continuity),        │
│            tone, writing_style                                   │
│  Output:   EditedChapterContainer →                              │
│            chapter.edited_sections (list[SectionContent])         │
│                                                                  │
│  PARALLEL because editing is independent per chapter once all    │
│  chapters are written. The editor:                               │
│    - Simplifies convoluted sentences                             │
│    - Removes redundancy                                          │
│    - Smooths transitions between paragraphs and sections         │
│    - Strips AI-sounding phrases                                  │
│    - Ensures consistent voice throughout                         │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Edit Ch1 │  │ Edit Ch2 │  │ Edit Ch3 │  │ Edit Ch4 │        │
│  │ (thread) │  │ (thread) │  │ (thread) │  │ (thread) │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│       │             │             │             │                │
│       └─────────────┴──────┬──────┴─────────────┘                │
│                            ▼                                     │
│                      All complete                                │
│                                                                  │
│  ✓ Checkpoint: after_editing                                     │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 6: GENERATE SECTION IMAGES  (72%)  [IF include_images]     │
│                                                                  │
│  Service:  LLMService (for descriptions) + ImageService          │
│  API:      Google Imagen / OpenAI / Flux                         │
│  Process:                                                        │
│    1. For each chapter, LLM generates an image description       │
│       based on the first section's content                       │
│       (uses EBOOK_SECTION_IMAGE_PROMPT, parallel via TaskGroup)  │
│    2. All descriptions sent to ImageService.generate_images()    │
│       for actual image generation                                │
│  Output:   chapter.section_image_paths (list[Path])              │
│                                                                  │
│  Skipped entirely if include_images is False.                    │
│  Uses the allow_faces toggle (same {face_rule} pattern).         │
│                                                                  │
│  ✓ Checkpoint: after_section_images                              │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 7: GENERATE COVER IMAGE  (82%)                             │
│                                                                  │
│  Service:  LLMService (for description) + ImageService           │
│  API:      Google Imagen / OpenAI / Flux                         │
│  Process:                                                        │
│    1. LLM generates cover image description                      │
│       (EBOOK_COVER_DESCRIPTION_PROMPT with title, topic, tone)   │
│    2. ImageService generates the actual image (portrait)         │
│  Output:   state.cover_description (str)                         │
│            state.cover_image_path (Path)                         │
│                                                                  │
│  ✓ Checkpoint: after_cover                                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 8: RENDER OUTPUT FILES  (90%)                              │
│                                                                  │
│  ┌─── render_pdf() ────────────────────────────────────────────┐ │
│  │  Library: fpdf2                                              │ │
│  │  Builds:                                                     │ │
│  │    1. COVER PAGE (image + title + subtitle + author)         │ │
│  │    2. COPYRIGHT PAGE (year, author, "Generated by MoceanAI") │ │
│  │    3. TABLE OF CONTENTS (auto-generated from start_section)  │ │
│  │       - fpdf2's insert_toc_placeholder() fills this with     │ │
│  │         chapter names and page numbers automatically         │ │
│  │    4. INTRODUCTION                                           │ │
│  │    5. CHAPTERS (each on new page):                           │ │
│  │       - Chapter heading (Helvetica Bold 22pt)                │ │
│  │       - Section headings (Helvetica Bold 15pt)               │ │
│  │       - Body text (Helvetica 11pt)                           │ │
│  │       - Optional chapter image (centered, 65% width)         │ │
│  │    6. CONCLUSION                                             │ │
│  │                                                              │ │
│  │  Header: ebook title (italic, gray)                          │ │
│  │  Footer: page number (centered)                              │ │
│  │  Margins: 25mm left/right, 20mm top/bottom                   │ │
│  │                                                              │ │
│  │  Unicode handling: _sanitize_text() replaces em dashes,      │ │
│  │  smart quotes, copyright symbols with Latin-1 equivalents    │ │
│  │                                                              │ │
│  │  Output: state.pdf_path (Path)                               │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─── render_docx() ──────────────────────────────────────────┐  │
│  │  Library: python-docx                                       │  │
│  │  Builds:                                                    │  │
│  │    1. COVER PAGE (title 28pt bold, subtitle, author)        │  │
│  │    2. COPYRIGHT PAGE                                        │  │
│  │    3. TABLE OF CONTENTS (Word TOC field — auto-populates    │  │
│  │       when opened in Word based on Heading 1/2 styles)      │  │
│  │    4. INTRODUCTION (Heading 1 + body paragraphs)            │  │
│  │    5. CHAPTERS (Heading 1 for chapter, Heading 2 for secs)  │  │
│  │    6. CONCLUSION                                            │  │
│  │                                                             │  │
│  │  Output: state.docx_path (Path)                             │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ✓ Checkpoint: complete                                          │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  OUTPUT FILES       │
                    │  - ebook.pdf        │
                    │  - ebook.docx       │
                    │  (or both)          │
                    └─────────────────────┘
```

---

## Multi-Agent Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                    AGENT ROLES                                │
│                                                               │
│  ┌──────────────┐   Designs the full structure, decides       │
│  │ OUTLINE      │   what chapters exist and what each         │
│  │ AGENT        │   covers. Sets the foundation.              │
│  │ (Step 1)     │                                             │
│  └──────┬───────┘                                             │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────┐   Writes one chapter at a time.             │
│  │ CHAPTER      │   Receives the previous chapter's           │
│  │ WRITER       │   summary so it can maintain narrative      │
│  │ AGENT        │   continuity. The "voice" of the ebook.     │
│  │ (Step 3)     │   Runs SEQUENTIALLY.                        │
│  └──────┬───────┘                                             │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────┐   Polishes each chapter after all are       │
│  │ EDITOR       │   written. Smooths transitions, cuts        │
│  │ AGENT        │   redundancy, strips AI-sounding phrases.   │
│  │ (Step 5)     │   Runs IN PARALLEL (chapters independent).  │
│  └──────┬───────┘                                             │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────┐   Generates detailed image prompts for      │
│  │ COVER +      │   the cover and chapter illustrations.      │
│  │ ILLUSTRATION │   Actual images generated by ImageService.  │
│  │ AGENTS       │                                             │
│  │ (Steps 6-7)  │                                             │
│  └──────┬───────┘                                             │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────┐   Renders the final PDF and/or DOCX with   │
│  │ FORMATTER    │   proper typography, TOC, page numbers,     │
│  │ (Step 8)     │   and professional styling.                 │
│  └──────────────┘                                             │
│                                                               │
│  All agents use the same LLMService instance but with         │
│  different system prompts and output schemas.                 │
└───────────────────────────────────────────────────────────────┘
```

---

## PDF Output Structure

```
┌─────────────────────────────┐
│         COVER PAGE          │
│                             │
│   [Cover Image if present]  │
│                             │
│      THE EBOOK TITLE        │
│       A Subtitle Here       │
│      by Author Name         │
├─────────────────────────────┤
│       COPYRIGHT PAGE        │
│                             │
│  (c) 2026 Author Name.     │
│  All rights reserved.      │
│  Generated by MoceanAI     │
├─────────────────────────────┤
│    TABLE OF CONTENTS        │
│                             │
│  Introduction ........... 3 │
│  Ch 1: Title ............ 5 │
│    Section A ............ 5 │
│    Section B ............ 7 │
│  Ch 2: Title ........... 10 │
│    Section A ........... 10 │
│    ...                      │
│  Conclusion ............ 42 │
├─────────────────────────────┤
│       INTRODUCTION          │
│                             │
│  Full introduction text     │
│  with flowing paragraphs.   │
├─────────────────────────────┤
│       CHAPTER 1             │
│  Building Your Foundation   │
│                             │
│  [Chapter image if present] │
│                             │
│  -- Why This Matters --     │
│  Section body text...       │
│                             │
│  -- The Framework --        │
│  Section body text...       │
├─────────────────────────────┤
│       CHAPTER 2             │
│       ...                   │
├─────────────────────────────┤
│       CONCLUSION            │
│                             │
│  Full conclusion text.      │
└─────────────────────────────┘
```

---

## Key Files

| File | Role |
|------|------|
| `v2/pipeline/ebook_pipeline.py` | 8-step orchestrator |
| `v2/pipeline/ebook_formatter.py` | render_pdf (fpdf2) + render_docx (python-docx) |
| `v2/core/ebook_models.py` | EbookConfig, EbookState, ChapterState, outline models |
| `v2/core/ebook_prompts.py` | 7 agent prompts (outline, intro, writer, conclusion, editor, cover, section image) |
| `v2/pages/ebook.py` | Streamlit UI |
| `v2/services/llm_service.py` | Shared LLM wrapper (used by all agents) |
| `v2/services/image_service.py` | Shared image gen (cover + section illustrations) |
