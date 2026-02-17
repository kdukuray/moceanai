# Ideal Long-Form Video Pipeline (Designed from Scratch, 2026)

## Overview

This document describes what a long-form video generation pipeline (2-30 minutes, primarily for YouTube) would look like if designed from scratch with no legacy constraints. Long-form content has fundamentally different challenges than short-form: narrative arc, audience retention over minutes not seconds, information density management, and the need for structural variety to prevent monotony.

---

## Design Principles

1. **Research is non-negotiable.** A 10-minute video built on LLM training data alone will be shallow, generic, and factually stale. Real research separates "content" from "content mill."
2. **Structure before prose.** The outline is the most important artifact. A great outline with mediocre writing produces a watchable video. A bad outline with brilliant writing produces a confusing one.
3. **Retention-aware pacing.** YouTube analytics show predictable drop-off patterns. The pipeline should explicitly design for retention: re-hooks every 60-90 seconds, pattern interrupts, payoff before setup fatigue.
4. **Sections are independent production units.** Each section should be fully producible in isolation. This enables parallelization, partial regeneration, and modular editing.
5. **The viewer experience is multimodal.** Script, visuals, music, pacing, and captions must be designed together, not sequentially bolted on.

---

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INPUT                              │
│                                                                 │
│  topic, purpose, target_audience, tone, duration_minutes,       │
│  orientation, voice, image_style, visual_mode,                  │
│  source_material (optional: URLs, PDFs, documents),             │
│  reference_videos (optional), brand_guidelines (optional)       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 1: DEEP RESEARCH  (0% → 10%)                             │
│                                                                  │
│  Long-form demands deeper research than short-form. A 60-second │
│  video can get away with one interesting fact. A 10-minute       │
│  video needs a BODY of knowledge to draw from.                   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  1a. SOURCE MATERIAL INGESTION  (parallel)                 │  │
│  │                                                            │  │
│  │  Tool:   Document parser (PDF, URL scraper, text)          │  │
│  │  Input:  user-provided URLs, PDFs, documents               │  │
│  │  Output: source_corpus (cleaned, chunked text)             │  │
│  │                                                            │  │
│  │  If the user provides source material, this is the         │  │
│  │  primary knowledge base. The video should cite and build   │  │
│  │  on THIS material, not hallucinate around the topic.       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  1b. WEB RESEARCH  (parallel)                              │  │
│  │                                                            │  │
│  │  Tool:   Search API (Tavily / Serper / Brave)              │  │
│  │  Input:  topic + subtopic decomposition (LLM generates     │  │
│  │          3-5 research queries from the topic)              │  │
│  │  Output: web_research (facts, statistics, expert quotes,   │  │
│  │          counterarguments, recent developments)             │  │
│  │                                                            │  │
│  │  Multiple search queries, not just one. A video about      │  │
│  │  "nuclear fusion" needs queries about: latest breakthroughs│  │
│  │  , economic viability, technical challenges, public opinion │  │
│  │  , comparison with renewables.                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  1c. REFERENCE VIDEO ANALYSIS  (parallel, optional)        │  │
│  │                                                            │  │
│  │  Tool:   Multimodal model (Gemini) video analysis          │  │
│  │  Input:  reference videos (uploaded or URLs)               │  │
│  │  Output: reference_analysis containing:                    │  │
│  │    - structure_pattern: how they organize sections          │  │
│  │    - pacing_pattern: fast/slow rhythm, section lengths      │  │
│  │    - visual_language: b-roll style, transition types        │  │
│  │    - hook_patterns: how they re-engage viewers              │  │
│  │    - retention_techniques: pattern interrupts, callbacks    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  1d. RESEARCH SYNTHESIS  (after 1a-1c complete)            │  │
│  │                                                            │  │
│  │  Service:  LLM                                             │  │
│  │  Input:    source_corpus + web_research + reference_analysis│  │
│  │  Output:   ResearchBrief containing:                       │  │
│  │    - key_facts: verified, citable facts (with sources)     │  │
│  │    - key_statistics: numbers that tell a story             │  │
│  │    - expert_perspectives: notable quotes/positions         │  │
│  │    - counterarguments: opposing views to address           │  │
│  │    - knowledge_gaps: what we DON'T know (honest framing)   │  │
│  │    - angle_recommendation: unique perspective suggestion   │  │
│  │    - fact_confidence: per-fact confidence rating            │  │
│  │                                                            │  │
│  │  This synthesis is the knowledge base for ALL downstream   │  │
│  │  writing. No fact should appear in the script that isn't   │  │
│  │  grounded here.                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ✓ Checkpoint: after_research                                    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 2: STRUCTURAL DESIGN  (10% → 18%)                        │
│                                                                  │
│  The outline is the most consequential decision in the pipeline. │
│  It determines whether the video is watchable or abandoned.      │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  2a. GENERATE OUTLINE  (single LLM call)                   │  │
│  │                                                            │  │
│  │  Service:  LLM with structured output                      │  │
│  │  Input:    topic, purpose, audience, tone, duration_minutes│  │
│  │            research_brief, reference_analysis              │  │
│  │  Output:   VideoOutline containing:                        │  │
│  │    - thesis: one-sentence core argument/promise            │  │
│  │    - target_duration_seconds: total                        │  │
│  │    - sections: list of SectionPlan, each with:             │  │
│  │        - title: section name                               │  │
│  │        - purpose: what this section accomplishes           │  │
│  │        - talking_points: key beats to hit                  │  │
│  │        - facts_to_use: refs into research_brief            │  │
│  │        - target_duration_seconds: section length           │  │
│  │        - section_type: one of:                             │  │
│  │            hook | context | argument | evidence |           │  │
│  │            counterargument | story | demonstration |        │  │
│  │            synthesis | callback | cta                       │  │
│  │        - energy_target: calm | building | peak | resolving │  │
│  │        - retention_device: what keeps them watching INTO    │  │
│  │            the next section (open loop, tease, question)   │  │
│  │        - transition_from_previous: how to bridge           │  │
│  │    - retention_map: planned re-hook points (every 60-90s)  │  │
│  │    - emotional_arc: setup → tension → payoff pattern       │  │
│  │                                                            │  │
│  │  The section_type taxonomy matters. A video that's         │  │
│  │  "argument, argument, argument, argument, CTA" is boring.  │  │
│  │  A video that's "hook, context, argument, story, counter-  │  │
│  │  argument, synthesis, CTA" has variety and depth.           │  │
│  │                                                            │  │
│  │  The retention_device per section is critical for long-form │  │
│  │  — it's the "but first..." or "we'll get to that in a     │  │
│  │  moment" technique that prevents drop-off at section       │  │
│  │  boundaries.                                               │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  2b. OUTLINE QUALITY GATE  (LLM-as-judge)                 │  │
│  │                                                            │  │
│  │  Service:  LLM evaluation                                  │  │
│  │  Input:    VideoOutline, research_brief, audience          │  │
│  │  Output:   OutlineReview containing:                       │  │
│  │    - structure_score: logical flow? (1-10)                 │  │
│  │    - variety_score: section types diverse enough? (1-10)   │  │
│  │    - retention_score: re-hooks well-placed? (1-10)         │  │
│  │    - depth_score: substance over fluff? (1-10)             │  │
│  │    - pacing_score: duration allocation makes sense? (1-10) │  │
│  │    - revision_notes: specific suggestions                  │  │
│  │    - pass: bool (all scores >= 7)                          │  │
│  │                                                            │  │
│  │  A bad outline produces a bad video no matter how good     │  │
│  │  everything downstream is. This is the single most         │  │
│  │  impactful quality gate in the entire pipeline.            │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_outline                               │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 3: SCRIPT WRITING  (18% → 35%)                           │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3a. WRITE ALL SECTION SCRIPTS  (semi-parallel)            │  │
│  │                                                            │  │
│  │  Two strategies, choose based on outline detail level:     │  │
│  │                                                            │  │
│  │  STRATEGY A: SEQUENTIAL WITH BATON PASS                    │  │
│  │  (when narrative continuity is critical)                   │  │
│  │                                                            │  │
│  │  For each section in order:                                │  │
│  │    LLM call with:                                          │  │
│  │      - section_plan (from outline)                         │  │
│  │      - research_brief (full)                               │  │
│  │      - cumulative_script (all previous sections)           │  │
│  │      - transition_from_previous (from outline)             │  │
│  │    Output: SectionScript with:                             │  │
│  │      - raw_text: clean narration                           │  │
│  │      - tts_text: with speech enhancement tags              │  │
│  │      - segments: pre-split into beats, each with:          │  │
│  │          - raw_text, tts_text                              │  │
│  │          - visual_intent: what viewer should see            │  │
│  │          - beat_type: setup | build | peak | resolve | etc.│  │
│  │          - energy_level: 1-10                              │  │
│  │                                                            │  │
│  │  STRATEGY B: PARALLEL WITH CONNECTORS                      │  │
│  │  (when outline has detailed transition instructions)       │  │
│  │                                                            │  │
│  │  Generate all sections in parallel, each receiving:         │  │
│  │    - section_plan (with transition_from_previous)          │  │
│  │    - research_brief (full)                                 │  │
│  │    - outline (full — so each writer sees the big picture)  │  │
│  │    - preceding_section_plan (so they know where sec N-1    │  │
│  │      was going, without needing its actual text)           │  │
│  │  Then: one "connector pass" LLM call rewrites the first   │  │
│  │  and last 2 sentences of each section to create smooth     │  │
│  │  transitions.                                              │  │
│  │                                                            │  │
│  │  Strategy B is 3-5x faster for 6+ sections but requires   │  │
│  │  a strong outline. For a 20-minute video with 8 sections,  │  │
│  │  Strategy A takes ~24s (8 sequential calls), Strategy B    │  │
│  │  takes ~6s (parallel + 1 connector pass).                  │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_scripts (per section)                 │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3b. SCRIPT QUALITY GATE  (parallel, one per section)      │  │
│  │                                                            │  │
│  │  Service:  LLM evaluation (parallel across sections)       │  │
│  │  Input:    each section script + outline + research_brief  │  │
│  │  Output:   Per-section QualityReport:                      │  │
│  │    - accuracy_score: facts match research? (1-10)          │  │
│  │    - engagement_score: holds attention? (1-10)             │  │
│  │    - pacing_score: right density for duration? (1-10)      │  │
│  │    - transition_score: flows from/to neighbors? (1-10)     │  │
│  │    - factual_flags: ungrounded claims                      │  │
│  │    - pass: bool                                            │  │
│  │                                                            │  │
│  │  Failed sections get rewritten individually.               │  │
│  │  The rest proceed.                                         │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_script_review                         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3c. FACT-CHECK PASS  (parallel)                           │  │
│  │                                                            │  │
│  │  Service:  LLM + web search                                │  │
│  │  Input:    factual_flags from quality gate + full scripts  │  │
│  │  Process:  For each flagged claim:                         │  │
│  │    1. Search the web for verification                      │  │
│  │    2. Score confidence (verified / plausible / unverified / │  │
│  │       contradicted)                                        │  │
│  │    3. If contradicted: rewrite that passage                │  │
│  │    4. If unverified: soften language ("studies suggest"     │  │
│  │       instead of "research proves")                        │  │
│  │  Output:   fact_checked scripts                            │  │
│  │                                                            │  │
│  │  Why: A 10-minute video that states something verifiably   │  │
│  │  wrong gets destroyed in YouTube comments. Fact-checking   │  │
│  │  is cheap insurance for credibility.                       │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 4: AUDIO PRODUCTION  (35% → 48%)                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  4a. GENERATE VOICE-OVER PER SECTION  (parallel)           │  │
│  │                                                            │  │
│  │  Service:  TTS API (ElevenLabs / PlayHT / LMNT)            │  │
│  │  Input:    tts_text per section                            │  │
│  │  Output:   Per-section:                                    │  │
│  │    - audio_path: section .mp3                              │  │
│  │    - word_alignments: word-level (start_ms, end_ms)        │  │
│  │                                                            │  │
│  │  KEY DIFFERENCE: Generate all section audio in PARALLEL.   │  │
│  │  Each section's TTS is independent. No need to wait for    │  │
│  │  section 1 audio before starting section 2.                │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_audio (per section)                   │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  4b. AUDIO ANALYSIS PER SECTION  (parallel)                │  │
│  │                                                            │  │
│  │  Tool:     librosa / pydub (local, no API cost)            │  │
│  │  Input:    section audio files + word alignments           │  │
│  │  Output:   Per-section AudioAnalysis:                      │  │
│  │    - segment_timings: per-beat timing                      │  │
│  │    - energy_envelope: loudness curve                       │  │
│  │    - speech_rate_curve: pacing changes                     │  │
│  │    - pause_map: natural cut points                         │  │
│  │    - beat_sync_points: optimal transition moments          │  │
│  │                                                            │  │
│  │  Plus a GLOBAL analysis:                                   │  │
│  │    - total_duration: actual runtime (not estimated)        │  │
│  │    - section_durations: actual per-section timing          │  │
│  │    - pacing_consistency: flag sections that are too fast    │  │
│  │      or too slow relative to the overall rhythm            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 5: VISUAL PLANNING  (48% → 55%)                          │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  5a. GLOBAL STYLE GUIDE  (single LLM call)                │  │
│  │                                                            │  │
│  │  Same as short-form: color palette, lighting, composition, │  │
│  │  texture, banned elements, style keywords.                 │  │
│  │                                                            │  │
│  │  PLUS for long-form:                                       │  │
│  │    - section_color_themes: subtle color shifts per section  │  │
│  │      (e.g., warmer for stories, cooler for data sections)  │  │
│  │    - visual_motifs: recurring visual elements that create   │  │
│  │      thematic unity (a particular object, color, pattern)  │  │
│  │    - variety_rules: min 3 different compositions before     │  │
│  │      repeating a style, alternate between close/wide shots  │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  5b. SECTION STORYBOARDS  (parallel, one LLM call each)   │  │
│  │                                                            │  │
│  │  Service:  LLM with structured output                      │  │
│  │  Input:    section script + segment beats + audio analysis │  │
│  │            + style guide + visual_intents from script       │  │
│  │  Output:   Per-section Storyboard:                         │  │
│  │    - shots: list of ShotPlan, each with:                   │  │
│  │        - image_prompt (includes style guide keywords)      │  │
│  │        - duration_ms (from audio timing)                   │  │
│  │        - motion_type: zoom_in | pan_left | static | etc.   │  │
│  │        - motion_speed: mapped to beat energy               │  │
│  │        - transition_in: cut | dissolve | wipe | dip_black  │  │
│  │    - section_transition: how the last shot of this section │  │
│  │      should visually bridge to the next section            │  │
│  │                                                            │  │
│  │  All section storyboards run in parallel. Each storyboard  │  │
│  │  receives the GLOBAL style guide and the FULL outline      │  │
│  │  (so it knows the broader visual journey), but only its    │  │
│  │  own section's script and audio analysis.                  │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_storyboards                           │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 6: VISUAL GENERATION  (55% → 75%)                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  6a. GENERATE ALL IMAGES  (fully parallel, rate-limited)   │  │
│  │                                                            │  │
│  │  Service:  Image API (Imagen / DALL-E / Flux)              │  │
│  │  Input:    ALL shot prompts from ALL sections               │  │
│  │  Output:   image_paths[] (one per shot, organized by       │  │
│  │            section)                                         │  │
│  │                                                            │  │
│  │  KEY DIFFERENCE: Images for ALL sections generated in a    │  │
│  │  single parallel batch. No reason to wait for section 1    │  │
│  │  images before starting section 2 images. For a 10-minute  │  │
│  │  video with ~60 shots, this is the difference between      │  │
│  │  ~9 minutes sequential vs ~90 seconds parallel (at 8       │  │
│  │  concurrent with rate limiting).                           │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_images (per section)                  │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  6b. VISUAL QUALITY GATE  (parallel, vision model)         │  │
│  │                                                            │  │
│  │  Service:  Vision model (Gemini / GPT-4o)                  │  │
│  │  Input:    images + their prompts + style guide            │  │
│  │  Process:  Same as short-form — reject bad images,         │  │
│  │            regenerate with feedback. Max 2 retries.         │  │
│  │                                                            │  │
│  │  PLUS for long-form:                                       │  │
│  │    - Cross-section consistency check: sample 1 image from  │  │
│  │      each section and verify they feel like one video,     │  │
│  │      not a patchwork.                                      │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_image_review                          │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 7: MOTION & CLIP GENERATION  (75% → 83%)                 │
│                                                                  │
│  Same two modes as short-form (animate via FFmpeg or video_gen   │
│  via AI APIs), but applied across ALL sections in parallel.      │
│                                                                  │
│  For animate mode:                                               │
│    - Motion types from storyboard (intentional, not cycling)     │
│    - Transitions from storyboard (dissolve, cut, wipe, etc.)     │
│    - Within-section transitions: from storyboard                 │  
│    - Between-section transitions: dip-to-black or dissolve       │
│      (always a clear visual break between sections)              │
│                                                                  │
│  Output: clip_paths[][] (per-section, per-shot)                  │
│  ✓ Checkpoint: after_clips                                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 8: SOUND DESIGN  (83% → 89%)                             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  8a. BACKGROUND MUSIC                                      │  │
│  │                                                            │  │
│  │  For long-form, music isn't one track — it's a SOUNDTRACK. │  │
│  │                                                            │  │
│  │  Option A: Generate per-section music snippets that match  │  │
│  │    the energy_target of each section, crossfaded together. │  │
│  │  Option B: Select a single track that matches the overall  │  │
│  │    tone, with volume automation mapped to section energy.  │  │
│  │  Option C: Select from a curated library with genre/mood   │  │
│  │    tags, using different tracks for different section types │  │
│  │    (e.g., ambient for context, driving for argument).      │  │
│  │                                                            │  │
│  │  The music should BREATHE with the content:                │  │
│  │    - Soft during calm explanation sections                 │  │
│  │    - Building during tension/argument sections             │  │
│  │    - Dropping out entirely for key revelations (silence    │  │
│  │      is the most powerful music cue)                       │  │
│  │    - Resolving during synthesis/CTA                        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  8b. TRANSITION SOUND EFFECTS                              │  │
│  │                                                            │  │
│  │  Input:   section boundaries, storyboard transitions       │  │
│  │  Output:  sfx_timeline:                                    │  │
│  │    - Section transitions: whoosh / impact / riser          │  │
│  │    - Key reveals: subtle emphasis sound                    │  │
│  │    - Pattern interrupts: distinct audio cue                │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  8c. AUDIO MIXING (per section, then global)               │  │
│  │                                                            │  │
│  │  Per section:                                              │  │
│  │    1. Duck music under voice (-12dB to -18dB)              │  │
│  │    2. Layer SFX at transition points                       │  │
│  │    3. Apply subtle compression to voice                    │  │
│  │  Global:                                                   │  │
│  │    4. Normalize loudness across sections (LUFS targeting)  │  │
│  │    5. Ensure section transitions are smooth (no jarring    │  │
│  │       volume jumps between sections)                       │  │
│  │    6. Master to -1dB peak, -14 LUFS (YouTube spec)         │  │
│  │  Output: mixed_audio per section (or one master track)     │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 9: ASSEMBLY  (89% → 95%)                                  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  9a. PER-SECTION ASSEMBLY  (parallel)                      │  │
│  │                                                            │  │
│  │  Tool:     FFmpeg                                          │  │
│  │  Input:    section clips + section mixed audio              │  │
│  │  Process:  Per section:                                    │  │
│  │    1. Concatenate clips with intra-section transitions      │  │
│  │    2. Mux with section audio                               │  │
│  │    3. Apply section color grade (from style guide)          │  │
│  │  Output:   section_video.mp4 per section                   │  │
│  │                                                            │  │
│  │  All sections assembled in parallel.                       │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  9b. FINAL CONCATENATION                                   │  │
│  │                                                            │  │
│  │  Tool:     FFmpeg                                          │  │
│  │  Input:    section_videos[] in order                       │  │
│  │  Process:                                                  │  │
│  │    1. Concat with inter-section transitions (dip-to-black, │  │
│  │       crossfade — 0.5-1s overlap)                          │  │
│  │    2. Burn in animated captions (word-highlight style)      │  │
│  │    3. Final encode: libx264 slow preset, AAC audio         │  │
│  │  Output:   final_video.mp4                                 │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ✓ Checkpoint: after_assembly                                    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 10: METADATA & PACKAGING  (95% → 98%)                    │
│                                                                  │
│  Long-form content (especially YouTube) has metadata that        │
│  directly impacts discoverability and click-through rate.        │
│  This should be part of the pipeline, not an afterthought.       │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  10a. GENERATE YOUTUBE METADATA  (single LLM call)         │  │
│  │                                                            │  │
│  │  Service:  LLM                                             │  │
│  │  Input:    full script, outline, research_brief, audience  │  │
│  │  Output:   YouTubeMetadata containing:                     │  │
│  │    - title_options: 3 titles (curiosity gap, direct, etc.) │  │
│  │    - description: SEO-optimized, with timestamps           │  │
│  │    - tags: 15-20 relevant tags                             │  │
│  │    - chapter_markers: timestamp + title per section         │  │
│  │      (derived from section titles + actual durations)       │  │
│  │    - hashtags: 3-5 trending hashtags                       │  │
│  │                                                            │  │
│  │  Chapter markers are generated from the ACTUAL section      │  │
│  │  timings (from audio analysis), not estimated. This is      │  │
│  │  only possible because we know exact section durations.     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  10b. GENERATE THUMBNAIL  (image generation)               │  │
│  │                                                            │  │
│  │  Service:  LLM (prompt design) + Image API (generation)    │  │
│  │  Input:    title, topic, style guide                       │  │
│  │  Process:                                                  │  │
│  │    1. LLM designs 2-3 thumbnail concepts following         │  │
│  │       YouTube thumbnail best practices (bold text,         │  │
│  │       expressive face, contrast, 1280x720)                │  │
│  │    2. Generate each concept                                │  │
│  │    3. Vision model scores: text readability, attention     │  │
│  │       grab, clickability                                   │  │
│  │    4. Return the highest-scoring option                    │  │
│  │  Output:   thumbnail.jpg (1280x720)                        │  │
│  │                                                            │  │
│  │  Why: The thumbnail is arguably more important than the    │  │
│  │  video itself for getting views. It deserves its own       │  │
│  │  generation + quality step.                                │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ✓ Checkpoint: after_metadata                                    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 11: FINAL QUALITY REVIEW  (98% → 100%)                   │
│                                                                  │
│  Service:  Vision model (Gemini / GPT-4o) — multimodal           │
│  Input:    final_video.mp4 (sampled frames + audio)              │
│  Output:   FinalReview:                                          │
│    - visual_consistency: cohesive look throughout? (1-10)        │
│    - audio_quality: clear voice, balanced mix? (1-10)            │
│    - pacing: engaging throughout? dragging anywhere? (1-10)      │
│    - section_transitions: smooth? jarring? (1-10)                │
│    - caption_sync: aligned correctly? (1-10)                     │
│    - overall_score: weighted average                             │
│    - timestamp_notes: specific issues at specific times          │
│                                                                  │
│  Informational only — flags issues for user review.              │
│                                                                  │
│  ✓ Checkpoint: complete                                          │
│  ✓ Saved to history                                              │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  DELIVERABLES:         │
                  │  • final_video.mp4     │
                  │  • thumbnail.jpg       │
                  │  • metadata.json       │
                  │  • chapter_markers.txt │
                  │  • transcript.srt      │
                  └────────────────────────┘
```

---

## Parallelization Deep Dive

This is where the biggest performance gains come from compared to a purely sequential pipeline.

```
PHASE 1: Research
  ├── [1a] Source ingestion ─┐
  ├── [1b] Web research     ├── parallel
  └── [1c] Reference analysis┘
  └── [1d] Synthesis (waits for all above)

PHASE 2: Outline
  └── Sequential: generate → review → optional retry

PHASE 3: Scripts
  ├── Strategy A: Sequential per section (safe, slower)
  └── Strategy B: All parallel → connector pass (fast, needs good outline)
  └── Quality gate: parallel across sections
  └── Fact-check: parallel across flagged claims

PHASE 4: Audio (ALL PARALLEL — this is a key win)
  ├── Section 1 TTS ─┐
  ├── Section 2 TTS  ├── all parallel
  ├── Section 3 TTS  │
  └── Section N TTS ─┘
  └── All audio analysis: parallel

PHASE 5: Visual Planning
  ├── Style guide: single call
  └── Section storyboards: all parallel

PHASE 6: Visual Generation (ALL PARALLEL — biggest time savings)
  ├── ALL images from ALL sections: one parallel batch
  └── Quality gate: all parallel

PHASE 7: Clips (ALL PARALLEL)
  └── All clips from all sections: one parallel batch

PHASE 8: Sound design
  ├── Music selection/generation ─┐ parallel
  └── SFX selection               ┘
  └── Per-section mixing: parallel
  └── Global mastering: sequential

PHASE 9: Assembly
  ├── Section assembly: all parallel
  └── Final concat: sequential

PHASE 10: Metadata
  ├── YouTube metadata ─┐ parallel
  └── Thumbnail gen      ┘

PHASE 11: Final review: single call
```

### Sequential vs. Parallel Comparison

For a 10-minute video with 6 sections, ~40 images:

| Operation | Sequential Pipeline | This Pipeline | Speedup |
|-----------|-------------------|---------------|---------|
| Script writing (6 sections) | 6 × 3s = 18s | 6s (parallel + connector) | 3x |
| TTS generation (6 sections) | 6 × 8s = 48s | 8s (parallel) | 6x |
| Image generation (40 images) | 40 × 9s = 360s | ~50s (8 concurrent, rate-limited) | 7x |
| Section assembly (6 sections) | 6 × 5s = 30s | 5s (parallel) | 6x |
| **Total pipeline** | **~12 minutes** | **~4 minutes** | **3x** |

The key insight: in a section-based pipeline, almost everything within each section is independent of other sections. The only truly sequential dependency is script writing with baton-pass — and even that can be parallelized with Strategy B.

---

## Long-Form Specific Challenges & Solutions

### 1. Retention Management

**Problem:** YouTube analytics show viewership drops at predictable points — section boundaries, slow stretches, and the 30% mark.

**Solution:**
- `retention_device` per section in the outline (open loops, teases, questions)
- Explicit re-hook points every 60-90 seconds (the outline's `retention_map`)
- Energy variation between sections (the `energy_target` field prevents monotone pacing)
- Pattern interrupts: sections of different types (story after argument, data after anecdote)

### 2. Visual Monotony

**Problem:** A 10-minute video with 40+ B-roll images can feel like a slideshow if not carefully planned.

**Solution:**
- `variety_rules` in the style guide (min 3 different compositions before repeating)
- `section_color_themes` for subtle visual shifts between sections
- `visual_motifs` for recurring elements that create thematic unity
- Cross-section consistency check in the visual quality gate

### 3. Audio Continuity

**Problem:** Per-section TTS generation can create audible discontinuities (volume, pacing, tone shifts) at section boundaries.

**Solution:**
- LUFS-targeted normalization across sections in the mastering step
- Inter-section audio crossfade (0.3-0.5s) during final concat
- Section energy analysis flags pacing inconsistencies before assembly

### 4. Narrative Coherence

**Problem:** Parallel script generation can produce sections that feel disconnected.

**Solution:**
- Strategy A (baton pass) for maximum continuity when needed
- Strategy B (parallel + connector pass) for speed when outline is detailed
- The connector pass specifically rewrites transition sentences
- Each writer receives the FULL outline so they understand the big picture

### 5. Duration Accuracy

**Problem:** Estimating duration from word count is unreliable — TTS speed varies with content, names, numbers, and emotional delivery.

**Solution:**
- Duration estimates in the outline are TARGETS, not constraints
- Actual duration is only known after TTS generation (Phase 4)
- If total duration is >15% off target, flag for user review
- Per-section duration analysis identifies which sections ran long/short

---

## Comparison with Typical Long-Form Pipelines

| Aspect | Typical Pipeline | This Pipeline |
|--------|-----------------|---------------|
| Research | None or minimal. Script from LLM training data. | Multi-source research with synthesis and fact-checking. |
| Outline | Section names + talking points. | Full structural design with section types, energy targets, retention devices, emotional arc. |
| Script quality | No validation. Whatever comes out goes to TTS. | Per-section quality gate + fact-check pass. |
| Script writing | Sequential only (baton pass). | Choice of sequential or parallel with connector pass. |
| Audio generation | Sequential per section. | All sections in parallel. |
| Image generation | Per-section batches, sequential sections. | All images from all sections in one parallel batch. |
| Visual planning | Per-segment image count. Per-segment descriptions in isolation. | Global style guide + per-section storyboards with intentional motion. |
| Visual QA | None. | Vision model quality gate + cross-section consistency check. |
| Sound design | Voice-over only. No music or SFX. | Background music + SFX + professional audio mixing + mastering. |
| Captions | Optional SRT. | Animated word-highlight as default. |
| Metadata | Manual / none. | Auto-generated titles, description, tags, chapters, thumbnail. |
| Assembly transitions | Hard cuts between sections. | Configurable transitions: dissolve, dip-to-black, crossfade. |
| Total parallelism | Low (sections processed sequentially). | High (most operations parallel across sections). |

---

## Error Handling & Recovery

Same pattern as short-form, but with section-level granularity:

1. Checkpoint after every phase (per-section where applicable)
2. On failure: `PipelineError` with `failed_phase`, `failed_section` (if applicable), `partial_state`
3. Recovery restarts at the failed section/phase, not from scratch
4. All generated assets preserved on disk
5. Partial results are displayable: if 4 of 6 sections completed, show those 4

### Section-Level Recovery

If section 4 of 6 fails during image generation:
- Sections 1-3 are fully assembled and playable
- Section 4 has scripts and audio, missing images
- Sections 5-6 have scripts (if Strategy B was used), missing audio and images
- Recovery regenerates section 4 images and continues from there

---

## What This Pipeline Optimizes For

1. **Depth over breadth** — research-grounded content that teaches something real
2. **Watchability** — retention-aware structure, energy management, pattern interrupts
3. **Speed** — aggressive parallelization across sections (3x faster than sequential)
4. **Visual quality** — cohesive style, intentional motion, quality-gated images
5. **Professional audio** — music, SFX, mixing, mastering = perceived production value
6. **Discoverability** — auto-generated thumbnail, SEO metadata, chapter markers
7. **Reliability** — quality gates at every stage boundary, section-level recovery
