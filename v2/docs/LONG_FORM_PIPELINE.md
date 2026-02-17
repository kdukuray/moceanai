# Long-Form Video Pipeline

## Overview

Generates long-form videos (2-20 minutes) for YouTube. The pipeline generates a structured multi-section video where each section has its own script, audio, and visuals, then concatenates them into a single cohesive video.

**Entry point:** `v2/pipeline/pipeline_runner.py` → `PipelineRunner.run_long_form()`  
**UI page:** `v2/pages/long_form.py`  
**State model:** `v2/core/models.py` → `LongFormState`

---

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INPUT (Streamlit UI)                   │
│                                                                 │
│  topic, purpose, target_audience, tone, platform, duration,     │
│  orientation, model_provider, image_provider, voice_actor,      │
│  image_style, visual_mode, video_provider, allow_faces          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 1: GENERATE GOAL  (3%)                                     │
│                                                                  │
│  Same as short-form: LLM generates a strategic CTA goal.         │
│  Output: state.goal                                              │
│  ✓ Checkpoint: lf_after_goal                                     │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 2: GENERATE STRUCTURE  (8%)                                │
│                                                                  │
│  Service:  ScriptGenerator → LLMService.generate_structured()    │
│  Model:    LLM                                                   │
│  Prompt:   LONG_FORM_STRUCTURE_PROMPT                            │
│  Input:    topic, purpose, target_audience, tone, goal           │
│  Output:   SectionsStructureContainer →                          │
│            state.sections (list[SectionState])                   │
│                                                                  │
│  Generates 5-8 sections, each with:                              │
│    - section_name: "Building Your Foundation"                    │
│    - section_purpose: "Establishes context and key concepts..."  │
│    - section_directives: ["Build tension", "Use analogies"]      │
│    - section_talking_points: ["87% of people...", "The key..."]  │
│                                                                  │
│  ✓ Checkpoint: lf_after_structure                                │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 3: PROCESS EACH SECTION (10% → 90%)                       │
│                                                                  │
│  Loops through each section. Per-section weight is distributed   │
│  evenly across the 10-90% progress range.                        │
│                                                                  │
│  For each section:                                               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3a. WRITE SECTION SCRIPT  (sequential — baton pass)       │  │
│  │                                                            │  │
│  │  Service: ScriptGenerator.generate_section_script()        │  │
│  │  Model:   LLM                                              │  │
│  │  Prompt:  LONG_FORM_SECTION_SCRIPT_PROMPT                  │  │
│  │  Input:   section_info + cumulative_script (all previous)  │  │
│  │  Output:  section.section_script (str)                     │  │
│  │                                                            │  │
│  │  SEQUENTIAL because each section reads the cumulative      │  │
│  │  script to maintain narrative continuity. The opening of   │  │
│  │  section N flows naturally from the ending of section N-1. │  │
│  │                                                            │  │
│  │  cumulative_script += section.section_script               │  │
│  │  ✓ Checkpoint: lf_sec{N}_script                            │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3b. SEGMENT SECTION SCRIPT                                │  │
│  │                                                            │  │
│  │  Service: ScriptGenerator.segment_section_script()         │  │
│  │  Output:  section.segments (list[SectionScriptSegmentItem])│  │
│  │  Splits the section script into ~12-35 word vocal units.   │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3c. GENERATE SECTION AUDIO + ALIGNMENT                    │  │
│  │                                                            │  │
│  │  Service: AudioGenerator.generate_and_align_section()      │  │
│  │  API:     ElevenLabs TTS                                   │  │
│  │  Output:  section.audio_path, section.word_alignments,     │  │
│  │           section.segment_timings                          │  │
│  │  ✓ Checkpoint: lf_sec{N}_audio                             │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3d. PLAN VISUALS                                          │  │
│  │  → How many images per segment (same as short-form)        │  │
│  │  Output: section.segment_visual_plans                      │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3e. GENERATE IMAGE DESCRIPTIONS  (parallel LLM calls)     │  │
│  │  → One LLM call per segment, run concurrently              │  │
│  │  ✓ Checkpoint: lf_sec{N}_img_desc                          │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3f. GENERATE IMAGES  (parallel API calls)                 │  │
│  │  API: Google Imagen / OpenAI / Flux (REAL, not mock)       │  │
│  │  ✓ Checkpoint: lf_sec{N}_images                            │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3g. CREATE VIDEO CLIPS  (zoompan or video_gen)            │  │
│  │  Same two modes as short-form pipeline.                    │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3h. ASSEMBLE SECTION VIDEO                                │  │
│  │                                                            │  │
│  │  Service: VideoAssembler.assemble_section()                │  │
│  │  Tool:    FFmpeg                                           │  │
│  │  Process: Concat segment clips → mux with section audio    │  │
│  │  Output:  section.section_video_path (Path)                │  │
│  │  ✓ Checkpoint: lf_sec{N}_complete                          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ... repeat for each section ...                                 │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 4: CONCATENATE ALL SECTIONS  (93%)                         │
│                                                                  │
│  Service:  VideoAssembler.assemble_long_form()                   │
│  Tool:     FFmpeg (concat filter with v=1, a=1)                  │
│  Input:    section_video_paths (each has its own video + audio)  │
│  Process:  Interleave video/audio streams:                       │
│            [v1, a1, v2, a2, v3, a3, ...]                         │
│  Output:   state.final_video_path (Path)                         │
│                                                                  │
│  ✓ Checkpoint: lf_complete                                       │
│  ✓ Saved to VideoHistory database                                │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  FINAL .mp4  │
                        └──────────────┘
```

---

## Section Processing Detail

```
Section 1       Section 2       Section 3       Section 4
    │               │               │               │
    ▼               ▼               ▼               ▼
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│ Script │───▶│ Script │───▶│ Script │───▶│ Script │
│(reads  │    │(reads  │    │(reads  │    │(reads  │
│ nothing)    │ sec 1) │    │ sec 1+2│    │sec 1-3)│
└───┬────┘    └───┬────┘    └───┬────┘    └───┬────┘
    │             │             │             │
    ▼             ▼             ▼             ▼
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│Segment │    │Segment │    │Segment │    │Segment │
└───┬────┘    └───┬────┘    └───┬────┘    └───┬────┘
    │             │             │             │
    ▼             ▼             ▼             ▼
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│ Audio  │    │ Audio  │    │ Audio  │    │ Audio  │
└───┬────┘    └───┬────┘    └───┬────┘    └───┬────┘
    │             │             │             │
    ▼             ▼             ▼             ▼
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│Images +│    │Images +│    │Images +│    │Images +│
│Animate │    │Animate │    │Animate │    │Animate │
└───┬────┘    └───┬────┘    └───┬────┘    └───┬────┘
    │             │             │             │
    ▼             ▼             ▼             ▼
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│ Sec.   │    │ Sec.   │    │ Sec.   │    │ Sec.   │
│ Video  │    │ Video  │    │ Video  │    │ Video  │
└───┬────┘    └───┬────┘    └───┬────┘    └───┬────┘
    │             │             │             │
    └─────────────┴──────┬──────┴─────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  FINAL .mp4  │
                  │  (all secs   │
                  │  concatenated)│
                  └──────────────┘
```

The "baton pass" continuity pattern: each section's script generation receives all previously written sections as `cumulative_script`, so it can flow naturally from where the previous section left off.

---

## Key Differences from Short-Form

| Aspect | Short-Form | Long-Form |
|--------|-----------|-----------|
| Duration | 15-300 seconds | 2-20 minutes |
| Structure | Flat (segments only) | Hierarchical (sections → segments) |
| Script gen | One-shot full script | Sequential per-section with cumulative context |
| Audio | One audio file | One audio file per section |
| Assembly | Single concat + mux | Per-section assembly, then final concat |
| Continuity | N/A | Baton-pass via cumulative_script |

---

## Key Files

| File | Role |
|------|------|
| `v2/pipeline/pipeline_runner.py` | Orchestrator (run_long_form) |
| `v2/pipeline/script_generator.py` | generate_structure, generate_section_script, segment_section_script |
| `v2/pipeline/audio_generator.py` | generate_and_align_section |
| `v2/pipeline/image_generator.py` | Same as short-form |
| `v2/pipeline/video_assembler.py` | assemble_section + assemble_long_form |
| `v2/core/models.py` | LongFormState, SectionState |
| `v2/core/prompts.py` | LONG_FORM_STRUCTURE_PROMPT, LONG_FORM_SECTION_SCRIPT_PROMPT, LONG_FORM_SECTION_SEGMENTER_PROMPT |
