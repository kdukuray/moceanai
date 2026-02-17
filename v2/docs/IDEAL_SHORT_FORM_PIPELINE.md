# Ideal Short-Form Video Pipeline (Designed from Scratch, 2026)

## Overview

This document describes what a short-form video generation pipeline (15-180 seconds, for TikTok/Reels/Shorts) would look like if designed from scratch with no legacy constraints, using the best available techniques and AI capabilities as of 2026. The goal is to serve as a comparison benchmark — not a rewrite spec.

---

## Design Principles

1. **Fewer LLM round-trips, richer context per call.** Each LLM call should carry maximum context and return maximum structure. Avoid sequential chains where one call's only purpose is to feed the next.
2. **Quality gates before expensive operations.** Never send a mediocre script to TTS. Never send a bad image to video generation. Validate and retry at every stage boundary.
3. **Audio drives everything.** The audio track is the backbone. All visual timing, pacing, and transitions derive from actual audio data — not word-count estimates.
4. **Visual coherence is a first-class concern.** Images aren't generated in isolation. A global style guide and visual continuity plan govern every image prompt.
5. **Post-production matters.** Music, sound design, caption styling, and color grading are not optional polish — they're core to engagement.

---

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INPUT                              │
│                                                                 │
│  topic, purpose, target_audience, tone, platform, duration,     │
│  orientation, voice, image_style, visual_mode,                  │
│  reference_urls (optional), brand_guidelines (optional)         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 1: RESEARCH & CONTEXT GATHERING  (0% → 8%)               │
│                                                                  │
│  This phase does NOT exist in most pipelines and it should.      │
│  Generating a script without research produces generic slop.     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  1a. TOPIC RESEARCH  (parallel)                            │  │
│  │                                                            │  │
│  │  Tool:   Web search API (Tavily / Serper / Brave Search)   │  │
│  │  Input:  topic, target_audience                            │  │
│  │  Output: research_context (key facts, statistics, recent   │  │
│  │          developments, common misconceptions, quotes)      │  │
│  │                                                            │  │
│  │  Why: An LLM writing about "intermittent fasting" without  │  │
│  │  fresh data will produce the same tired script every time.  │  │
│  │  Real facts and recent studies make scripts unique.         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  1b. TREND / COMPETITOR ANALYSIS  (parallel)               │  │
│  │                                                            │  │
│  │  Tool:   Web search + LLM analysis                         │  │
│  │  Input:  topic, platform                                   │  │
│  │  Output: trend_context (what hooks are working, what       │  │
│  │          angles are saturated, what gaps exist)             │  │
│  │                                                            │  │
│  │  Why: The best short-form content doesn't just cover a     │  │
│  │  topic — it finds an angle that hasn't been beaten to      │  │
│  │  death. This step prevents the "same video everyone else   │  │
│  │  already made" problem.                                    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  1c. REFERENCE VIDEO ANALYSIS  (parallel, optional)        │  │
│  │                                                            │  │
│  │  Tool:   Multimodal model (Gemini) video analysis          │  │
│  │  Input:  reference_urls or uploaded videos                 │  │
│  │  Output: style_analysis (pacing, hook structure, visual    │  │
│  │          language, transition patterns, caption style)      │  │
│  │                                                            │  │
│  │  Why: "Make it like this" is the most common creative      │  │
│  │  brief. Analyzing reference material makes the output      │  │
│  │  match the creator's actual vision.                        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  All three run in parallel. Total latency = slowest one.         │
│  ✓ Checkpoint: after_research                                    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 2: SCRIPT GENERATION  (8% → 22%)                         │
│                                                                  │
│  ONE call, not five. Modern LLMs with structured output can      │
│  generate a complete, segmented, TTS-ready script in a single    │
│  call when given rich context. Splitting into goal → hook →      │
│  script → enhance → segment creates unnecessary latency and      │
│  loses cross-step coherence.                                     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  2a. GENERATE FULL SCRIPT  (single LLM call)              │  │
│  │                                                            │  │
│  │  Service:  LLM with structured output (Pydantic model)     │  │
│  │  Input:    topic, purpose, audience, tone, platform,       │  │
│  │            duration, research_context, trend_context,      │  │
│  │            style_analysis, brand_guidelines                │  │
│  │  Output:   FullScript object containing:                   │  │
│  │    - goal: strategic CTA                                   │  │
│  │    - hook: opening line (first 3 seconds)                  │  │
│  │    - segments: list of ScriptBeat, each with:              │  │
│  │        - raw_text: clean narration text                    │  │
│  │        - tts_text: text with speech tags ([whisper], etc.) │  │
│  │        - visual_intent: what the viewer should SEE         │  │
│  │        - beat_type: hook | tension | payoff | cta | etc.   │  │
│  │        - energy_level: 1-10 (pacing indicator)             │  │
│  │    - cta: closing call-to-action                           │  │
│  │                                                            │  │
│  │  The visual_intent field is critical — the writer should   │  │
│  │  be thinking about what the viewer SEES while they hear    │  │
│  │  each line. This is a screenplay, not a blog post.         │  │
│  │                                                            │  │
│  │  The beat_type and energy_level fields inform downstream   │  │
│  │  decisions (motion speed, transition type, music energy).  │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_script_draft                          │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  2b. SCRIPT QUALITY GATE  (LLM-as-judge)                  │  │
│  │                                                            │  │
│  │  Service:  LLM evaluation (different model or temperature) │  │
│  │  Input:    FullScript, topic, platform, audience           │  │
│  │  Output:   QualityReport containing:                       │  │
│  │    - hook_score: 1-10 (stops the scroll?)                  │  │
│  │    - clarity_score: 1-10 (easy to follow?)                 │  │
│  │    - engagement_score: 1-10 (holds attention?)             │  │
│  │    - cta_score: 1-10 (motivates action?)                   │  │
│  │    - pacing_score: 1-10 (right speed for platform?)        │  │
│  │    - factual_flags: list of claims that seem unverified    │  │
│  │    - revision_notes: specific improvement suggestions      │  │
│  │    - pass: bool (all scores >= 7)                          │  │
│  │                                                            │  │
│  │  If pass == False: loop back to 2a with revision_notes     │  │
│  │  injected as additional instructions. Max 2 retries.       │  │
│  │                                                            │  │
│  │  Why: TTS costs money. Image generation costs money.       │  │
│  │  Video generation costs a LOT of money. Catching a weak    │  │
│  │  script here saves dollars and minutes downstream.         │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_quality_gate                          │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 3: AUDIO PRODUCTION  (22% → 35%)                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3a. GENERATE VOICE-OVER  (TTS)                            │  │
│  │                                                            │  │
│  │  Service:  ElevenLabs / PlayHT / LMNT                      │  │
│  │  Input:    Concatenated tts_text from all segments          │  │
│  │  Output:   audio.mp3 + word_alignments[]                   │  │
│  │                                                            │  │
│  │  Use word-level timestamp API. Character-to-word grouping   │  │
│  │  happens here. Each word gets (start_ms, end_ms).           │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_audio                                 │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  3b. AUDIO ANALYSIS  (local computation)                   │  │
│  │                                                            │  │
│  │  Tool:     librosa / pydub (local, no API cost)            │  │
│  │  Input:    audio.mp3, word_alignments                      │  │
│  │  Output:   AudioAnalysis containing:                       │  │
│  │    - segment_timings: start/end per script beat            │  │
│  │    - energy_envelope: loudness curve over time             │  │
│  │    - speech_rate_curve: words-per-second over time         │  │
│  │    - pause_map: natural pauses and their durations         │  │
│  │    - beat_sync_points: optimal cut points (on pauses,      │  │
│  │      between sentences, on emphasis words)                 │  │
│  │                                                            │  │
│  │  Why: Instead of just mapping "segment N starts at 4.2s",  │  │
│  │  we extract the FULL audio character. This data drives     │  │
│  │  visual pacing, transition timing, and music sync.         │  │
│  │                                                            │  │
│  │  The beat_sync_points are particularly important — cutting  │  │
│  │  on a natural pause feels professional, cutting mid-word   │  │
│  │  feels jarring.                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 4: VISUAL PLANNING  (35% → 42%)                          │
│                                                                  │
│  This is the "director's pass" — deciding WHAT to show and      │
│  WHEN, before generating any pixels.                             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  4a. GENERATE GLOBAL STYLE GUIDE  (single LLM call)       │  │
│  │                                                            │  │
│  │  Service:  LLM                                             │  │
│  │  Input:    topic, image_style, tone, brand_guidelines      │  │
│  │  Output:   StyleGuide containing:                          │  │
│  │    - color_palette: primary/secondary/accent colors        │  │
│  │    - lighting_direction: warm/cool/dramatic/natural        │  │
│  │    - composition_rules: rule of thirds, centered, etc.     │  │
│  │    - texture_notes: matte/glossy/grainy/clean              │  │
│  │    - banned_elements: things to avoid (text, watermarks)   │  │
│  │    - style_keywords: "cinematic", "flat lay", etc.         │  │
│  │                                                            │  │
│  │  Why: Without this, image 1 might be warm and golden       │  │
│  │  while image 4 is cold and blue. The video looks like a    │  │
│  │  random slideshow instead of a cohesive piece.             │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  4b. GENERATE VISUAL STORYBOARD  (single LLM call)        │  │
│  │                                                            │  │
│  │  Service:  LLM with structured output                      │  │
│  │  Input:    segments[], style_guide, audio_analysis,        │  │
│  │            visual_intents from script, visual_mode         │  │
│  │  Output:   Storyboard containing for each segment:         │  │
│  │    - shot_list: list of ShotPlan, each with:               │  │
│  │        - image_prompt: detailed generation prompt          │  │
│  │          (includes style guide keywords automatically)     │  │
│  │        - duration_ms: how long this shot holds             │  │
│  │        - motion_type: zoom_in | zoom_out | pan_left |     │  │
│  │          pan_right | static | ken_burns | dolly_in         │  │
│  │        - motion_speed: slow | medium | fast                │  │
│  │        - transition_in: cut | dissolve | wipe | none       │  │
│  │    - segment_energy: maps to audio energy_level            │  │
│  │                                                            │  │
│  │  The storyboard sees ALL segments at once, so it can       │  │
│  │  plan visual variety (don't show 3 close-ups in a row),    │  │
│  │  plan transitions (dissolve between related ideas, hard    │  │
│  │  cut for topic changes), and pace motion to audio energy.  │  │
│  │                                                            │  │
│  │  The motion_type and motion_speed are driven by the        │  │
│  │  beat_type and energy_level from the script, not random    │  │
│  │  cycling through patterns.                                 │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_storyboard                            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 5: VISUAL GENERATION  (42% → 70%)                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  5a. GENERATE IMAGES  (parallel, rate-limited)             │  │
│  │                                                            │  │
│  │  Service:  Image API (Imagen / DALL-E / Flux)              │  │
│  │  Input:    shot_list[].image_prompt (from storyboard)      │  │
│  │  Output:   image_paths[] (one per shot)                    │  │
│  │                                                            │  │
│  │  All shots across all segments generated in parallel.      │  │
│  │  Rate limiting via semaphore + token bucket (same idea     │  │
│  │  as existing: per-provider limits).                        │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_images                                │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  5b. VISUAL QUALITY GATE  (parallel, vision model)         │  │
│  │                                                            │  │
│  │  Service:  Vision model (Gemini / GPT-4o)                  │  │
│  │  Input:    generated images + their prompts                │  │
│  │  Output:   Per-image quality assessment:                   │  │
│  │    - relevance: does it match the prompt? (1-10)           │  │
│  │    - quality: artifacts, blur, distortion? (1-10)          │  │
│  │    - style_match: consistent with style guide? (1-10)      │  │
│  │    - reject: bool (any score < 6)                          │  │
│  │                                                            │  │
│  │  Rejected images get regenerated (max 2 retries per image  │  │
│  │  with the rejection reason appended to the prompt).        │  │
│  │                                                            │  │
│  │  Why: Image generation is inconsistent. Without this gate, │  │
│  │  you get random bad images polluting the final video.      │  │
│  │  A 2-second vision model call is worth the cost to avoid   │  │
│  │  ruining a $2 video generation downstream.                 │  │
│  │                                                            │  │
│  │  ✓ Checkpoint: after_image_review                          │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 6: MOTION & VIDEO CLIPS  (70% → 82%)                     │
│                                                                  │
│  Two modes, same as most pipelines:                              │
│                                                                  │
│  ┌─── IF visual_mode == "animate" ────────────────────────────┐  │
│  │                                                            │  │
│  │  Tool:     FFmpeg                                          │  │
│  │  Input:    images + storyboard motion plans                │  │
│  │  Process:  For each shot:                                  │  │
│  │    1. Apply the SPECIFIC motion_type from the storyboard   │  │
│  │       (not a cycling pattern — intentional per-shot)       │  │
│  │    2. Apply the SPECIFIC motion_speed (derived from        │  │
│  │       audio energy for that segment)                       │  │
│  │    3. Apply transition_in (dissolve/wipe/cut) between      │  │
│  │       shots within the same segment                        │  │
│  │    4. Upscale 2x before zoompan to prevent pixelation      │  │
│  │    5. Temporal smoothing (tmix)                            │  │
│  │                                                            │  │
│  │  Key improvement: motion is INTENTIONAL, not decorative.   │  │
│  │  A zoom-in on a key stat. A slow pan across a landscape.   │  │
│  │  A fast zoom-out for a reveal. Each motion serves the      │  │
│  │  narrative.                                                │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─── IF visual_mode == "video_gen" ──────────────────────────┐  │
│  │                                                            │  │
│  │  API:     Runway / Luma / Kling / Veo                      │  │
│  │  Input:   image + image_prompt + motion description        │  │
│  │  Process: Image-to-video generation per shot               │  │
│  │  Duration: clamped to API limits (3-10s typically)          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Output: clip_paths[] (one video clip per shot)                  │
│  ✓ Checkpoint: after_clips                                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 7: SOUND DESIGN  (82% → 88%)                             │
│                                                                  │
│  This phase is often entirely missing from generation pipelines  │
│  and it makes a MASSIVE difference to perceived quality.         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  7a. BACKGROUND MUSIC SELECTION                            │  │
│  │                                                            │  │
│  │  Option A: Music generation API (Suno / Udio)              │  │
│  │  Option B: Licensed library search (Epidemic Sound API)    │  │
│  │  Option C: Pre-loaded royalty-free tracks matched by tone  │  │
│  │                                                            │  │
│  │  Input:   tone, energy_levels from script, duration        │  │
│  │  Output:  music_track.mp3 (full duration, matched energy)  │  │
│  │                                                            │  │
│  │  The track should match the ENERGY CURVE of the script:    │  │
│  │  softer during setup, building during tension, peaks at    │  │
│  │  the payoff, resolves during CTA.                          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  7b. SOUND EFFECTS  (optional)                             │  │
│  │                                                            │  │
│  │  Tool:     SFX library lookup or generation                │  │
│  │  Input:    transition points, beat_types                   │  │
│  │  Output:   sfx_timeline (whoosh on transitions, subtle     │  │
│  │            emphasis sounds on key reveals, ambient layers)  │  │
│  │                                                            │  │
│  │  Even simple whoosh transitions between segments make the  │  │
│  │  video feel dramatically more polished.                    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  7c. AUDIO MIXING                                          │  │
│  │                                                            │  │
│  │  Tool:     FFmpeg / pydub                                  │  │
│  │  Process:                                                  │  │
│  │    1. Duck music under voice-over (-12dB to -18dB)         │  │
│  │    2. Layer SFX at transition points                       │  │
│  │    3. Apply subtle compression to voice track              │  │
│  │    4. Normalize final mix to -1dB peak (platform spec)     │  │
│  │  Output:   mixed_audio.mp3                                 │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 8: ASSEMBLY & POST-PRODUCTION  (88% → 97%)               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  8a. VIDEO ASSEMBLY                                        │  │
│  │                                                            │  │
│  │  Tool:     FFmpeg                                          │  │
│  │  Input:    clip_paths, mixed_audio, word_alignments        │  │
│  │  Process:                                                  │  │
│  │    1. Concatenate clips with specified transitions          │  │
│  │       (cross-dissolve, etc. from storyboard)               │  │
│  │    2. Mux with mixed audio track                           │  │
│  │    3. Apply global color grade for consistency              │  │
│  │       (LUT or FFmpeg color filters matched to style guide) │  │
│  │    4. Encode: libx264 slow preset, AAC audio               │  │
│  │  Output:   assembled_video.mp4 (no captions yet)           │  │
│  └────────────────────────────┬───────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  8b. ANIMATED CAPTIONS  (burned-in or sidecar)             │  │
│  │                                                            │  │
│  │  Tool:     Custom renderer or FFmpeg ASS subtitles          │  │
│  │  Input:    word_alignments, caption_style config            │  │
│  │  Styles:                                                    │  │
│  │    - "word_highlight": one word at a time, highlighted     │  │
│  │      (CapCut / Hormozi style — proven highest retention)   │  │
│  │    - "line_scroll": 2-3 words, scrolling up               │  │
│  │    - "standard_srt": traditional subtitles                 │  │
│  │  Output:   final_video.mp4 with captions burned in         │  │
│  │                                                            │  │
│  │  Why: 85% of short-form viewers watch without sound.       │  │
│  │  Animated captions aren't a feature, they're table stakes. │  │
│  │  Word-level alignment makes this possible. The highlight   │  │
│  │  style (bouncing/scaling the active word) is the current   │  │
│  │  gold standard for retention.                              │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ✓ Checkpoint: after_assembly                                    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 9: FINAL QUALITY CHECK  (97% → 100%)                     │
│                                                                  │
│  Service:  Vision model (Gemini / GPT-4o) — multimodal           │
│  Input:    final_video.mp4 (sampled frames + audio)              │
│  Output:   FinalReview containing:                               │
│    - visual_consistency: do all shots feel cohesive? (1-10)      │
│    - audio_sync: are captions synced? any drift? (1-10)          │
│    - pacing: does it feel rushed or draggy? (1-10)               │
│    - hook_effectiveness: would YOU stop scrolling? (1-10)        │
│    - technical_issues: black frames, glitches, artifacts         │
│    - overall_score: weighted average                             │
│    - notes: free-text observations                               │
│                                                                  │
│  This is a sanity check, not a gate. If overall_score < 5, flag │
│  for user review. Otherwise, deliver.                            │
│                                                                  │
│  ✓ Checkpoint: complete                                          │
│  ✓ Saved to history                                              │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  FINAL .mp4  │
                        └──────────────┘
```

---

## Phase Comparison: This Pipeline vs. Typical Implementation

| Phase | Typical Pipeline | This Pipeline | Why It Matters |
|-------|-----------------|---------------|----------------|
| Research | None. LLM writes from training data only. | Web search + trend analysis + reference analysis. | Scripts are grounded in real, current facts. No generic slop. |
| Script | 4-5 sequential LLM calls (goal → hook → script → enhance → segment). | 1 structured LLM call + 1 quality gate. | 60-70% less latency. Better coherence (writer sees everything at once). |
| Quality gates | None. Whatever the LLM produces goes straight to TTS. | Script quality gate + image quality gate + final review. | Catches problems BEFORE they cost money at downstream stages. |
| Audio analysis | Segment timing via string matching only. | Full audio analysis: energy, speech rate, pause detection, beat sync points. | Visual pacing is driven by actual audio characteristics, not guesses. |
| Visual planning | Per-segment image count (duration / ideal). Image descriptions generated per-segment in isolation. | Global style guide + full storyboard with intentional motion and transitions. | Visually cohesive. No random mismatched images. Intentional camera work. |
| Sound design | None. Voice-over only. | Background music + SFX + professional audio mix. | Dramatic quality improvement. Music and SFX are 50% of perceived production value. |
| Captions | Optional SRT burn-in. | Animated word-highlight captions as default. | 85% of viewers watch without sound. This is a retention multiplier. |
| Post-production | Raw concat + mux. | Color grading, transitions between shots, audio normalization. | The difference between "AI generated" and "professionally produced." |

---

## Architecture Notes

### Parallelization Strategy

```
Phase 1: Research  →  [1a, 1b, 1c] all parallel
Phase 2: Script    →  sequential (generate → quality gate → optional retry)
Phase 3: Audio     →  sequential (TTS → analysis)
Phase 4: Planning  →  sequential (style guide → storyboard)
Phase 5: Visuals   →  [all images] parallel → [quality gate] parallel → [retries] parallel
Phase 6: Clips     →  [all clips] parallel (if animate) or [all jobs] parallel (if video_gen)
Phase 7: Sound     →  [music gen, SFX selection] parallel → mixing sequential
Phase 8: Assembly  →  sequential
Phase 9: Review    →  single call
```

### Cost Awareness

The pipeline is designed to be **cost-efficient through quality gates**:
- Catch bad scripts before spending $0.50-2.00 on TTS
- Catch bad images before spending $2-15 on video generation per clip
- A $0.01 LLM evaluation call can prevent a $5+ wasted video generation

### Checkpointing

Checkpoint after every phase (not every step). Phases are the natural recovery boundaries — you wouldn't want to resume in the middle of a quality gate loop.

### Error Recovery

On failure:
1. State is checkpointed with all completed phases
2. Error includes: failed_phase, partial_state, original_error
3. Recovery restarts from the failed phase, not from scratch
4. All generated assets (audio, images, clips) are preserved on disk

---

## What This Pipeline Optimizes For

1. **Script quality** — research grounding + quality gate ensures the foundation is solid
2. **Visual coherence** — global style guide + full-context storyboard prevents random visuals
3. **Professional audio** — music, SFX, and mixing make the video FEEL professional
4. **Efficient spending** — quality gates prevent expensive downstream waste
5. **Intentional pacing** — audio analysis drives visual timing, not arbitrary duration math
6. **Platform-native feel** — animated captions, platform-aware pacing, trend-informed hooks
