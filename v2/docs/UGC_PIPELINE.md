# UGC Product Video Pipeline

## Overview

Generates realistic UGC (User-Generated Content) style product review videos. The user uploads product images (multiple angles) and the product listing description, optionally provides reference viral videos for style inspiration, and the pipeline produces a natural-sounding review video with the product placed in realistic home environments.

**Entry point:** `v2/pipeline/ugc_pipeline.py` → `UGCPipeline.run()`  
**UI page:** `v2/pages/ugc.py`  
**State model:** `v2/core/ugc_models.py` → `UGCState`

---

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INPUT (Streamlit UI)                   │
│                                                                 │
│  product_name, product_description (from listing),              │
│  product_images[] (multiple angles),                            │
│  reference_videos[] (optional, max 3),                          │
│  script_guidance (optional),                                    │
│  voice_actor, tone, platform, duration, orientation,            │
│  visual_mode, allow_faces, simple_scenes                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 0: ANALYZE REFERENCE VIDEOS  (3-7%)  [OPTIONAL]           │
│                                                                  │
│  Service:  GeminiVideoAnalyzer.analyze_multiple()                │
│  API:      Google Gemini 2.5 Flash (multimodal)                  │
│  Process:  For each reference video (up to 3, in parallel):      │
│                                                                  │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │  1. Upload video to Gemini Files API                     │   │
│    │  2. Send video + UGC_REFERENCE_VIDEO_ANALYSIS_PROMPT     │   │
│    │  3. Gemini watches the video (frames + audio)            │   │
│    │  4. Returns structured JSON:                             │   │
│    │     {                                                    │   │
│    │       "hook_style": "direct address with product reveal",│   │
│    │       "pacing": "fast cuts every 2-3 seconds",           │   │
│    │       "tone": "genuinely enthusiastic",                  │   │
│    │       "cta_style": "casual link in bio mention",         │   │
│    │       "shot_types": ["close-up", "POV", "overhead"],     │   │
│    │       "structure_summary": "Hook → demo → results → CTA",│   │
│    │       "key_phrases": ["okay hear me out", "game changer"]│   │
│    │     }                                                    │   │
│    └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Output: state.reference_analyses (list[ReferenceVideoAnalysis]) │
│  These cues feed into the script writer to mirror viral style.   │
│                                                                  │
│  ✓ Checkpoint: after_ref_analysis                                │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 1: DESCRIBE PRODUCT APPEARANCE  (10%)                      │
│                                                                  │
│  Service:  GeminiVideoAnalyzer.describe_product()                │
│  API:      Google Gemini 2.5 Flash (multimodal)                  │
│  Process:                                                        │
│    1. Upload all product images to Gemini Files API              │
│    2. Send images + UGC_PRODUCT_IMAGE_DESCRIPTION_PROMPT         │
│    3. Gemini examines all angles and returns:                    │
│       "Compact cylindrical fan, approximately 15cm tall,         │
│        matte white plastic body with a chrome accent ring at     │
│        the base. Three speed buttons on the front (labeled 1,   │
│        2, 3) in dark gray. USB-C port on the back. Brand logo   │
│        'NovaCool' embossed in silver on the top..."             │
│                                                                  │
│  Output: state.product_visual_description (str)                  │
│  This description is embedded into EVERY scene prompt so the     │
│  image/video model recreates the product accurately.             │
│                                                                  │
│  ✓ Checkpoint: after_product_description                         │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 2: GENERATE UGC REVIEW SCRIPT  (18%)                       │
│                                                                  │
│  Service:  LLMService.generate_structured()                      │
│  Model:    LLM (Gemini / GPT / Claude)                           │
│  Prompt:   UGC_SCRIPT_WRITER_PROMPT                              │
│  Input:    product_name, product_description, tone, platform,    │
│            duration, reference_analyses (if any),                │
│            script_guidance (if any), allow_faces                 │
│  Output:   UGCScriptContainer → state.script (str)               │
│                                                                  │
│  The script is written as a real person reviewing the product:   │
│  "Okay so I've been using this mini fan for about a week now     │
│   and honestly... I did not expect it to be this good. Like      │
│   look at the size of this thing, it literally fits in my purse. │
│   And three speed settings? On a fan this small? The battery     │
│   lasts me about eight hours on medium which is wild..."         │
│                                                                  │
│  If reference_analyses provided → mirrors hook style, pacing     │
│  If script_guidance provided → follows user's content direction  │
│                                                                  │
│  ✓ Checkpoint: after_script                                      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 3: ENHANCE SCRIPT FOR TTS  (25%)                           │
│  STEP 4: SEGMENT SCRIPT  (30%)                                   │
│  STEP 5: GENERATE AUDIO + WORD ALIGNMENT  (38%)                  │
│                                                                  │
│  These three steps reuse the exact same services as the          │
│  short-form pipeline:                                            │
│                                                                  │
│    ScriptGenerator.enhance_script()                              │
│      → Adds [excited], [softly], [pause] ElevenLabs tags         │
│                                                                  │
│    ScriptGenerator.segment_script()                              │
│      → Splits into 12-35 word beats with aligned tracks          │
│                                                                  │
│    AudioGenerator.generate_and_align_short_form()                │
│      → ElevenLabs TTS → word alignment → segment timing          │
│                                                                  │
│  Output: state.audio_path, state.word_alignments,                │
│          state.segment_timings, state.segments                   │
│                                                                  │
│  ✓ Checkpoints: after_enhance, after_segment, after_audio        │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 6: PLAN SCENES  (48%)                                      │
│                                                                  │
│  Service:  LLMService.generate_structured()                      │
│  Model:    LLM                                                   │
│  Prompt:   UGC_SCENE_PLANNER_PROMPT_TEMPLATE                     │
│            with {face_rule} and {complexity_rule} substituted     │
│  Input:    script_segments, product_name,                        │
│            product_visual_description, segment_durations          │
│  Output:   UGCScenePlanContainer → state.scene_descriptions      │
│                                                                  │
│  Each scene gets TWO prompts:                                    │
│                                                                  │
│  image_prompt (for image gen):                                   │
│    "Photorealistic photograph of the NovaCool portable mini      │
│     fan (matte white, 15cm tall, chrome accent ring, three       │
│     gray speed buttons) sitting on a light oak bedside table     │
│     next to a reading lamp. Warm bedroom lighting, shallow       │
│     depth of field, shot from 45-degree angle..."               │
│                                                                  │
│  video_prompt (for video gen):                                   │
│    "Slow push-in on the product, soft ambient light shifts       │
│     slightly, shallow depth of field with background bokeh"      │
│                                                                  │
│  Scene types cycle through: product_closeup, in_use,             │
│  environment, detail, lifestyle                                  │
│                                                                  │
│  ┌─── simple_scenes == True ──────────────────────────────────┐  │
│  │  Scenes constrained to: static shots, flat-lays, close-ups │  │
│  │  No complex hand interactions or flowing liquids            │  │
│  │  Better results from video generation models                │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─── simple_scenes == False ─────────────────────────────────┐  │
│  │  Dynamic scenes allowed: hands holding product, pressing    │  │
│  │  buttons, product in action                                 │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ✓ Checkpoint: after_scene_plan                                  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 7: GENERATE PRODUCT-IN-ENVIRONMENT IMAGES  (58%)           │
│                                                                  │
│  Service:  ImageService.generate_images()                        │
│  API:      Google Imagen 4 / OpenAI / Flux (parallel)            │
│  Input:    scene.image_prompt for each scene                     │
│  Style:    Photo Realism forced (UGC must look real)             │
│  Output:   state.scene_image_paths (list[Path])                  │
│                                                                  │
│  The image model recreates the product (from the visual          │
│  description embedded in every prompt) and places it in          │
│  realistic environments: bedside table, desk, kitchen counter,   │
│  reviewer's hand, gym bag, etc.                                  │
│                                                                  │
│  ✓ Checkpoint: after_images                                      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 8: GENERATE VIDEO CLIPS  (72%)                             │
│                                                                  │
│  ┌─── IF visual_mode == "zoompan" ─────────────────────────────┐ │
│  │  Tool: FFmpeg (ProcessPoolExecutor)                          │ │
│  │  Uses: animate_with_motion_effect() from image_generator.py  │ │
│  │  Each scene image → zoompan clip with motion effects         │ │
│  │  Patterns: zoom_in, zoom_out, pan_right, ken_burns           │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─── IF visual_mode == "video_gen" ───────────────────────────┐ │
│  │  API: Runway / Luma / Kling (parallel via TaskGroup)         │ │
│  │  For each scene:                                             │ │
│  │    - Base image: scene_image_paths[i] (image-to-video)       │ │
│  │    - Prompt: scene.video_prompt (motion description)         │ │
│  │    - Duration: clamped to 3-10s per API limits               │ │
│  │  The generated image serves as the first frame, and the      │ │
│  │  video model animates it with the described motion.          │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Output: state.clip_paths (list[Path])                           │
│  ✓ Checkpoint: after_clips                                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 9: ASSEMBLE FINAL VIDEO  (92%)                             │
│                                                                  │
│  Service:  VideoAssembler.assemble_short_form()                  │
│  Tool:     FFmpeg                                                │
│  Process:  Concat all clips → mux with audio → add end buffer   │
│  Output:   state.final_video_path (Path)                         │
│                                                                  │
│  ✓ Checkpoint: complete                                          │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │  FINAL .mp4  │
                        │  (UGC review)│
                        └──────────────┘
```

---

## Data Flow: How Product Photos Become Video Scenes

```
 UPLOADED PRODUCT PHOTOS             GEMINI MULTIMODAL
 (multiple angles)                   (describe_product)
         │                                  │
         ▼                                  ▼
 ┌───────────────┐              ┌───────────────────────────┐
 │  photo_1.jpg  │              │ "Matte white cylindrical   │
 │  photo_2.jpg  │──────────────▶  fan, 15cm tall, chrome   │
 │  photo_3.jpg  │              │  ring, three gray buttons, │
 └───────────────┘              │  USB-C port, 'NovaCool'   │
                                │  logo embossed..."         │
                                └─────────────┬─────────────┘
                                              │
                                              │ embedded into every
                                              │ scene prompt
                                              ▼
                                ┌───────────────────────────┐
                                │  SCENE PLANNER (LLM)      │
                                │                           │
                                │  image_prompt:            │
                                │  "Photo of NovaCool fan   │
                                │   (matte white, 15cm,     │
                                │   chrome ring...) on a    │
                                │   wooden bedside table,   │
                                │   warm lamp light..."     │
                                │                           │
                                │  video_prompt:            │
                                │  "Slow push-in, soft      │
                                │   ambient light shift"    │
                                └─────────────┬─────────────┘
                                              │
                              ┌───────────────┴───────────────┐
                              ▼                               ▼
                    ┌──────────────────┐            ┌──────────────────┐
                    │  IMAGE SERVICE   │            │  VIDEO SERVICE   │
                    │  (Imagen/OpenAI) │            │  (Runway/Luma)   │
                    │                  │            │                  │
                    │  Generates a     │───────────▶│  Animates the    │
                    │  photorealistic  │  base img  │  still image     │
                    │  still image     │            │  into a clip     │
                    └──────────────────┘            └──────────────────┘
```

---

## Reference Video Analysis Flow

```
 UPLOADED REFERENCE VIDEO              GEMINI MULTIMODAL
 (viral TikTok/IG example)            (analyze_video)
         │                                    │
         ▼                                    ▼
 ┌───────────────┐              ┌────────────────────────────┐
 │  viral_1.mp4  │              │ Gemini watches the video:  │
 │               │──────────────▶  - Frames (visual content) │
 │               │              │  - Audio (speech, music)    │
 └───────────────┘              │  - Duration, cuts, pacing   │
                                └─────────────┬──────────────┘
                                              │
                                              ▼
                                ┌────────────────────────────┐
                                │  ReferenceVideoAnalysis:    │
                                │                            │
                                │  hook: "product reveal     │
                                │         with surprise"     │
                                │  pacing: "fast, 2s cuts"   │
                                │  tone: "enthusiastic"       │
                                │  shots: [closeup, POV]     │
                                │  phrases: ["game changer"] │
                                └─────────────┬──────────────┘
                                              │
                                              │ fed into script writer
                                              ▼
                                ┌────────────────────────────┐
                                │  UGC SCRIPT WRITER (LLM)   │
                                │                            │
                                │  Mirrors the reference's   │
                                │  hook style, pacing, tone, │
                                │  and CTA approach.         │
                                └────────────────────────────┘
```

---

## Key Files

| File | Role |
|------|------|
| `v2/pipeline/ugc_pipeline.py` | 10-step orchestrator |
| `v2/services/gemini_video_analyzer.py` | Multimodal video/image analysis via Gemini |
| `v2/core/ugc_models.py` | UGCConfig, UGCState, scene descriptions |
| `v2/core/ugc_prompts.py` | 6 specialized UGC prompts |
| `v2/pages/ugc.py` | Streamlit UI with file uploaders |
| `v2/pipeline/script_generator.py` | Reused: enhance_script, segment_script |
| `v2/pipeline/audio_generator.py` | Reused: generate_and_align_short_form |
| `v2/services/image_service.py` | Reused: generate_images |
| `v2/services/video_service.py` | Reused: generate_video |
| `v2/pipeline/video_assembler.py` | Reused: assemble_short_form |
