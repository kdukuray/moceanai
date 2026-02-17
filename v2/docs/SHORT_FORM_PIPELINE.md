# Short-Form Video Pipeline

## Overview

Generates short-form videos (15-300 seconds) for TikTok, Instagram, and YouTube Shorts. The pipeline takes a topic and configuration, then produces a fully assembled video with AI-generated script, voice-over, B-roll images, and motion effects.

**Entry point:** `v2/pipeline/pipeline_runner.py` → `PipelineRunner.run_short_form()`  
**UI page:** `v2/pages/short_form.py`  
**State model:** `v2/core/models.py` → `ShortFormState`

---

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INPUT (Streamlit UI)                   │
│                                                                 │
│  topic, purpose, target_audience, tone, platform, duration,     │
│  orientation, model_provider, image_provider, voice_actor,      │
│  image_style, visual_mode, allow_faces, enhance_for_tts        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 1: GENERATE GOAL  (5%)                                    │
│                                                                  │
│  Service:  ScriptGenerator → LLMService.generate_structured()    │
│  Model:    LLM (Gemini / GPT / Claude)                           │
│  Prompt:   GOAL_GENERATION_PROMPT                                │
│  Input:    topic, purpose, target_audience                       │
│  Output:   GoalContainer → state.goal (str)                      │
│                                                                  │
│  Example:  "get viewers to follow for more daily finance tips"   │
│                                                                  │
│  ✓ Checkpoint: after_goal                                        │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 2: GENERATE HOOK  (10%)                                    │
│                                                                  │
│  Service:  ScriptGenerator → LLMService.generate_structured()    │
│  Model:    LLM                                                   │
│  Prompt:   HOOK_GENERATION_PROMPT                                │
│  Input:    topic, purpose, target_audience, tone, platform       │
│  Output:   HookContainer → state.hook (str)                      │
│                                                                  │
│  Example:  "Your credit score is lying to you — here's why."    │
│                                                                  │
│  ✓ Checkpoint: after_hook                                        │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 3: GENERATE SCRIPT  (18%)                                  │
│                                                                  │
│  Service:  ScriptGenerator → LLMService.generate_structured()    │
│  Model:    LLM                                                   │
│  Prompt:   SCRIPT_GENERATION_PROMPT                              │
│  Input:    topic, goal, hook, purpose, target_audience, tone,    │
│            platform, duration_seconds, additional_instructions,  │
│            style_reference                                       │
│  Output:   ScriptContainer → state.script (str)                  │
│                                                                  │
│  The script is pure spoken narration — no stage directions,      │
│  timestamps, or visual cues. TTS-optimized with punctuation     │
│  for natural pacing. Word count scaled to duration.              │
│                                                                  │
│  ✓ Checkpoint: after_script                                      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 4: ENHANCE SCRIPT FOR TTS  (25%)                           │
│                                                                  │
│  Service:  ScriptGenerator → LLMService.generate_structured()    │
│  Model:    LLM                                                   │
│  Prompt:   SCRIPT_ENHANCEMENT_PROMPT                             │
│  Input:    state.script                                          │
│  Output:   EnhancedScriptContainer → state.enhanced_script (str) │
│                                                                  │
│  Adds ElevenLabs audio tags like [whispers], [pause], [excited]  │
│  Skipped if enhance_for_tts is False (uses raw script instead).  │
│                                                                  │
│  ✓ Checkpoint: after_enhance                                     │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 5: SEGMENT SCRIPT  (30%)                                   │
│                                                                  │
│  Service:  ScriptGenerator → LLMService.generate_structured()    │
│  Model:    LLM                                                   │
│  Prompt:   SCRIPT_SEGMENTATION_PROMPT                            │
│  Input:    script, enhanced_script (both tracks)                 │
│  Output:   ScriptListContainer → state.segments                  │
│            (list[ScriptSegment], each with script_segment and    │
│             enhanced_script_segment)                              │
│                                                                  │
│  Splits the script into 12-35 word beats, each suitable for     │
│  one visual clip. Both raw and enhanced tracks are aligned 1:1.  │
│                                                                  │
│  ✓ Checkpoint: after_segment                                     │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 6: GENERATE AUDIO + WORD ALIGNMENT  (38%)                  │
│                                                                  │
│  Service:  AudioGenerator → ElevenLabsService.generate_audio()   │
│  API:      ElevenLabs TTS (convert_with_timestamps)              │
│  Input:    enhanced_script (or script), voice_actor, voice_model │
│  Output:   state.audio_path (Path to .mp3)                       │
│            state.word_alignments (list[WordAlignment])            │
│            state.segment_timings (list[SegmentTiming])            │
│                                                                  │
│  1. Send text to ElevenLabs → get audio + character timestamps   │
│  2. Group characters into words → word-level alignment           │
│  3. Match each script segment to its audio position via          │
│     string matching (exact first, fuzzy fallback)                │
│  4. Each segment gets: start_time, end_time, duration            │
│                                                                  │
│  This replaces v1's fragile character-index offset approach.     │
│                                                                  │
│  ✓ Checkpoint: after_audio                                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 7: PLAN VISUALS  (45%)                                     │
│                                                                  │
│  Service:  ImageGenerator.plan_visuals() (local computation)     │
│  Input:    segment_timings, ideal_image_duration (3s),           │
│            min_image_duration (2s)                                │
│  Output:   state.segment_visual_plans (list[SegmentVisualPlan])  │
│                                                                  │
│  For each segment, compute:                                      │
│    - How many B-roll images are needed (duration / ideal)        │
│    - Duration of the last image (absorbs leftover time)          │
│                                                                  │
│  Example: 7.5s segment → 2 images (3s + 4.5s)                   │
│  Example: 11.5s segment → 4 images (3s + 3s + 3s + 2.5s)       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 8: GENERATE IMAGE DESCRIPTIONS  (50%)                      │
│                                                                  │
│  Service:  ImageGenerator → ScriptGenerator (parallel via        │
│            asyncio.TaskGroup, one LLM call per segment)          │
│  Model:    LLM                                                   │
│  Prompt:   SEGMENT_IMAGE_DESCRIPTIONS_PROMPT_TEMPLATE            │
│            (with {face_rule} substituted based on allow_faces)   │
│  Input:    script_segment, full_script, image_style, topic,     │
│            tone, num_of_image_descriptions                       │
│  Output:   Updates segment_visual_plans with image_descriptions  │
│            (list[ImageDescription] per segment)                  │
│                                                                  │
│  Each description is exhaustively detailed for AI image gen:     │
│  subject, environment, composition, lighting, color, texture.    │
│  Face-free or faces-allowed based on the allow_faces toggle.     │
│                                                                  │
│  ✓ Checkpoint: after_image_descriptions                          │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 9: GENERATE IMAGES  (60%)                                  │
│                                                                  │
│  Service:  ImageGenerator → ImageService.generate_images()       │
│  API:      Google Imagen 4 / OpenAI gpt-image-1.5 / Flux 2 Pro  │
│  Input:    image_descriptions, provider, orientation             │
│  Output:   Updates segment_visual_plans with image_paths         │
│            (list[Path] per segment)                              │
│                                                                  │
│  All images generated in parallel with:                          │
│    - Per-provider rate limiter (1 req / 9 seconds)               │
│    - Per-provider semaphore (8 concurrent for Google/OpenAI)     │
│    - Per-image 3-attempt retry with exponential backoff          │
│                                                                  │
│  ✓ Checkpoint: after_images                                      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 10: CREATE VIDEO CLIPS  (78%)                              │
│                                                                  │
│  ┌─── IF visual_mode == "zoompan" ─────────────────────────────┐ │
│  │ Service:  ImageGenerator.animate_segments()                  │ │
│  │ Tool:     FFmpeg (ProcessPoolExecutor for parallelism)       │ │
│  │ Process:  For each segment's images:                         │ │
│  │   1. loop=1 + t=duration → exact frame count                │ │
│  │   2. scale 2x (lanczos) → prevent zoom pixelation           │ │
│  │   3. zoompan filter (d=1) → camera motion                   │ │
│  │   4. tmix frames=3 → temporal smoothing                     │ │
│  │   5. concat all sub-clips → segment video                   │ │
│  │   6. libx264 slow preset → output .mp4                      │ │
│  │ Motion patterns cycle: zoom_in → zoom_out → ...             │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─── IF visual_mode == "video_gen" ───────────────────────────┐ │
│  │ Service:  ImageGenerator.generate_video_clips()              │ │
│  │ API:      Runway / Luma / Kling (via VideoGenerationService) │ │
│  │ Process:  For each segment:                                  │ │
│  │   1. Use first image description as video prompt             │ │
│  │   2. Use generated image as base (image-to-video)            │ │
│  │   3. Submit job → poll until done → download clip            │ │
│  │   Duration clamped to 3-10s per API limits                   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Output: state.clip_paths (list[Path])                           │
│                                                                  │
│  ✓ Checkpoint: after_animation                                   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 11: ASSEMBLE FINAL VIDEO  (90%)                            │
│                                                                  │
│  Service:  VideoAssembler.assemble_short_form()                  │
│  Tool:     FFmpeg (via ffmpeg-python)                             │
│  Input:    clip_paths, audio_path, orientation, add_end_buffer   │
│  Output:   state.final_video_path (Path to .mp4)                 │
│                                                                  │
│  1. Concatenate all video clips (v=1, a=0)                       │
│  2. Optionally append 1s black buffer at the end                 │
│  3. Mux with audio stream (acodec=aac)                           │
│  4. Optionally burn in subtitles from word_alignments            │
│     (generates SRT → FFmpeg subtitles filter)                    │
│                                                                  │
│  ✓ Checkpoint: complete                                          │
│  ✓ Saved to VideoHistory database                                │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  FINAL .mp4  │
                        └──────────────┘
```

---

## Error Handling

Every step is wrapped in `try/except`. On failure:
1. State is checkpointed to `v2/output/checkpoints/`
2. `PipelineError` is raised with `failed_step`, `partial_state`, `original_error`
3. The UI catches this and displays all content generated before the failure
4. Previously generated audio, images, and clips are preserved on disk

---

## Key Files

| File | Role |
|------|------|
| `v2/pipeline/pipeline_runner.py` | Orchestrator (run_short_form) |
| `v2/pipeline/script_generator.py` | All LLM calls for script creation |
| `v2/pipeline/audio_generator.py` | ElevenLabs TTS + word alignment |
| `v2/pipeline/image_generator.py` | Image gen + zoompan + video gen |
| `v2/pipeline/video_assembler.py` | FFmpeg final assembly |
| `v2/services/llm_service.py` | Multi-provider LLM wrapper |
| `v2/services/elevenlabs_service.py` | TTS with word-level timing |
| `v2/services/image_service.py` | Google/OpenAI/Flux image gen |
| `v2/services/video_service.py` | Runway/Luma/Kling video gen |
| `v2/core/models.py` | ShortFormState + all data models |
| `v2/core/prompts.py` | System prompts for all LLM calls |
| `v2/pages/short_form.py` | Streamlit UI |
