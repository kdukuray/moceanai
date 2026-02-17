"""
UGC (User-Generated Content) product video pipeline orchestrator.

Generates realistic product review videos by coordinating:
  - Gemini multimodal analysis of reference videos and product images
  - Natural-sounding reviewer script generation
  - ElevenLabs TTS with word-level alignment
  - Photorealistic scene image generation with accurate product placement
  - Video clip creation (zoompan or AI video generation)
  - Final video assembly

Pipeline steps:
  0. Analyze reference videos (optional, Gemini multimodal)
  1. Describe product appearance from uploaded images (Gemini multimodal)
  2. Generate UGC script (LLM)
  3. Enhance script for TTS (LLM, reuses existing)
  4. Segment script (LLM, reuses existing)
  5. Generate audio + word-level alignment (ElevenLabs, reuses existing)
  6. Plan scenes (LLM with product visual description)
  7. Generate product-in-environment images (ImageService)
  8. Generate video clips (zoompan or AI video gen)
  9. Assemble final video (FFmpeg, reuses existing VideoAssembler)

Error handling:
  Every step is individually guarded with try/except. On failure, the state
  is checkpointed and a PipelineError is raised carrying the partial state.
  The UI displays all successfully generated content before the failure.

Reused services from existing pipeline:
  - ScriptGenerator (enhance_script, segment_script)
  - AudioGenerator (generate_and_align_short_form)
  - ImageService (generate_images)
  - VideoGenerationService (generate_video, for video_gen mode)
  - VideoAssembler (assemble_short_form)
  - ImageGenerator (animate_segments, for zoompan mode)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from v2.core.config import OUTPUT_DIR, VIDEO_DIR
from v2.core.models import (
    ScriptSegment,
    SegmentTiming,
    SegmentVisualPlan,
)
from v2.core.ugc_models import (
    UGCState,
    UGCSceneDescription,
    UGCScenePlanContainer,
    UGCScriptContainer,
)
from v2.core.ugc_prompts import (
    UGC_SCRIPT_WRITER_PROMPT,
    UGC_SCENE_PLANNER_PROMPT_TEMPLATE,
    UGC_SIMPLE_SCENES_RULE,
    UGC_COMPLEX_SCENES_RULE,
)
from v2.core.prompts import FACE_FREE_RULE, FACES_ALLOWED_RULE
from v2.pipeline.pipeline_runner import PipelineError
from v2.pipeline.script_generator import ScriptGenerator
from v2.pipeline.audio_generator import AudioGenerator, compute_images_per_segment
from v2.pipeline.image_generator import ImageGenerator, animate_with_motion_effect
from v2.pipeline.video_assembler import VideoAssembler
from v2.services.llm_service import LLMService
from v2.services.image_service import ImageService
from v2.services.video_service import VideoGenerationService
from v2.services.gemini_video_analyzer import GeminiVideoAnalyzer

logger = logging.getLogger(__name__)

# Type alias for the progress callback: (message, percent 0.0-1.0)
ProgressCallback = Optional[Callable[[str, float], None]]

# Checkpoint directory for UGC-specific checkpoints
UGC_CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints" / "ugc"
UGC_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

# Number of worker processes for CPU-bound FFmpeg animation
NUM_WORKERS = os.cpu_count() or 4


def _save_ugc_checkpoint(state: UGCState, label: str) -> Optional[Path]:
    """
    Save a UGC pipeline checkpoint to disk.

    Writes the current state as JSON so that if a later step fails,
    all previously generated content is preserved on disk.
    """
    try:
        safe_label = label.replace(" ", "_").replace("/", "-")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = UGC_CHECKPOINT_DIR / f"{ts}_{safe_label}.json"
        path.write_text(
            state.model_dump_json(indent=2, exclude={"word_alignments"}),
            encoding="utf-8",
        )
        logger.debug(f"UGC checkpoint saved: {path.name}")
        return path
    except Exception as e:
        logger.warning(f"UGC checkpoint write failed ({label}): {e}")
        return None


class UGCPipeline:
    """
    Orchestrates the full UGC product video generation workflow.

    Usage:
        pipeline = UGCPipeline(model_provider="google")
        state = await pipeline.run(state, on_progress=callback)

    If any step fails, a PipelineError is raised with the partial state
    attached so the UI can display everything generated before the error.
    """

    def __init__(self, model_provider: str = "google"):
        """
        Initialize with all required sub-services.

        Args:
            model_provider: LLM provider for script and scene generation.
        """
        self.llm = LLMService(provider=model_provider)
        self.script_gen = ScriptGenerator(provider=model_provider)
        self.audio_gen = AudioGenerator()
        self.image_gen = ImageGenerator(script_gen=self.script_gen)
        self.image_service = ImageService()
        self.video_service = VideoGenerationService()
        self.assembler = VideoAssembler()
        self.gemini_analyzer = GeminiVideoAnalyzer()

    async def run(
        self,
        state: UGCState,
        on_progress: ProgressCallback = None,
    ) -> UGCState:
        """
        Run the complete UGC video generation pipeline.

        Args:
            state: UGCState with config populated from the UI.
            on_progress: Optional callback(message, percent) for UI updates.

        Returns:
            Fully populated UGCState with final_video_path set.

        Raises:
            PipelineError: On any step failure, with partial_state attached.
        """
        config = state.config

        def _progress(msg: str, pct: float = 0.0):
            if on_progress:
                on_progress(msg, pct)
            logger.info(f"[{pct:.0%}] {msg}")

        def _fail(step_name: str, error: Exception) -> None:
            logger.error(f"UGC pipeline failed at '{step_name}': {error}")
            logger.error(traceback.format_exc())
            _save_ugc_checkpoint(state, f"FAILED_{step_name}")
            raise PipelineError(step_name, state, error)

        # ─── Step 0: Analyze reference videos (optional) ────────────
        if config.reference_video_paths:
            try:
                _progress(
                    f"Analyzing {len(config.reference_video_paths)} reference video(s)...",
                    0.03,
                )
                state.reference_analyses = await self.gemini_analyzer.analyze_multiple(
                    config.reference_video_paths
                )
                _save_ugc_checkpoint(state, "after_ref_analysis")
                _progress(
                    f"Analyzed {len(state.reference_analyses)} reference video(s)",
                    0.07,
                )
            except PipelineError:
                raise
            except Exception as e:
                _fail("analyze_reference_videos", e)

        # ─── Step 1: Describe product from uploaded images ───────────
        try:
            _progress("Analyzing product images...", 0.10)
            state.product_visual_description = await self.gemini_analyzer.describe_product(
                config.product_image_paths
            )
            _save_ugc_checkpoint(state, "after_product_description")
        except PipelineError:
            raise
        except Exception as e:
            _fail("describe_product", e)

        # ─── Step 2: Generate UGC script ─────────────────────────────
        try:
            _progress("Writing product review script...", 0.18)

            # Build reference analyses JSON for the prompt (empty array if none)
            ref_analyses_json = json.dumps(
                [a.model_dump() for a in state.reference_analyses]
            ) if state.reference_analyses else "[]"

            script_result = self.llm.generate_structured(
                system_prompt=UGC_SCRIPT_WRITER_PROMPT,
                user_payload={
                    "product_name": config.product_name,
                    "product_description": config.product_description,
                    "tone": config.tone,
                    "platform": config.platform,
                    "duration_seconds": config.duration_seconds,
                    "reference_analyses": ref_analyses_json,
                    "script_guidance": config.script_guidance,
                    "allow_faces": config.allow_faces,
                },
                output_model=UGCScriptContainer,
            )
            state.script = script_result.script
            _save_ugc_checkpoint(state, "after_script")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_script", e)

        # ─── Step 3: Enhance script for TTS ──────────────────────────
        try:
            _progress("Enhancing script for voice generation...", 0.25)
            if config.enhance_for_tts:
                state.enhanced_script = self.script_gen.enhance_script(state.script)
            else:
                state.enhanced_script = state.script
            _save_ugc_checkpoint(state, "after_enhance")
        except PipelineError:
            raise
        except Exception as e:
            _fail("enhance_script", e)

        # ─── Step 4: Segment script ──────────────────────────────────
        try:
            _progress("Segmenting script into clips...", 0.30)
            state.segments = self.script_gen.segment_script(
                script=state.script,
                enhanced_script=state.enhanced_script,
            )
            _save_ugc_checkpoint(state, "after_segment")
        except PipelineError:
            raise
        except Exception as e:
            _fail("segment_script", e)

        # ─── Step 5: Generate audio + word-level alignment ───────────
        try:
            _progress("Generating voice-over audio...", 0.38)
            audio_path, word_alignments, segment_timings = (
                self.audio_gen.generate_and_align_short_form(
                    script=state.script,
                    enhanced_script=state.enhanced_script,
                    segments=state.segments,
                    voice_actor=config.voice_actor,
                    voice_model="eleven_v3",
                    use_enhanced=config.enhance_for_tts,
                )
            )
            state.audio_path = audio_path
            state.word_alignments = word_alignments
            state.segment_timings = segment_timings
            _save_ugc_checkpoint(state, "after_audio")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_audio", e)

        # ─── Step 6: Plan scenes ─────────────────────────────────────
        try:
            _progress("Planning visual scenes...", 0.48)

            # Build the scene planner prompt with face and complexity rules
            face_rule = FACES_ALLOWED_RULE if config.allow_faces else FACE_FREE_RULE
            complexity_rule = (
                UGC_SIMPLE_SCENES_RULE if config.simple_scenes
                else UGC_COMPLEX_SCENES_RULE
            )
            scene_prompt = UGC_SCENE_PLANNER_PROMPT_TEMPLATE.format(
                face_rule=face_rule,
                complexity_rule=complexity_rule,
            )

            # Extract segment texts and durations for the scene planner
            segment_texts = [seg.script_segment for seg in state.segments]
            segment_durations = [t.duration for t in state.segment_timings]

            scene_plan_result = self.llm.generate_structured(
                system_prompt=scene_prompt,
                user_payload={
                    "script_segments": segment_texts,
                    "product_name": config.product_name,
                    "product_visual_description": state.product_visual_description,
                    "product_description": config.product_description,
                    "segment_durations": segment_durations,
                    "platform": config.platform,
                },
                output_model=UGCScenePlanContainer,
            )
            state.scene_descriptions = scene_plan_result.scenes
            _save_ugc_checkpoint(state, "after_scene_plan")
        except PipelineError:
            raise
        except Exception as e:
            _fail("plan_scenes", e)

        # ─── Step 7: Generate product-in-environment images ──────────
        try:
            _progress("Generating product images in realistic environments...", 0.58)

            # Collect all image prompts from the scene plan
            image_prompts = [scene.image_prompt for scene in state.scene_descriptions]

            # Force photo realism for UGC (override any other style)
            scene_image_paths = await self.image_service.generate_images(
                descriptions=image_prompts,
                provider=config.image_provider,
                orientation=config.orientation.lower(),
            )
            state.scene_image_paths = scene_image_paths
            _save_ugc_checkpoint(state, "after_images")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_images", e)

        # ─── Step 8: Generate video clips ────────────────────────────
        try:
            if config.visual_mode == "video_gen":
                _progress(
                    f"Generating video clips via {config.video_provider}...", 0.72
                )
                await self._generate_video_clips_via_api(state)
            else:
                _progress("Animating images into video clips...", 0.72)
                await self._animate_with_zoompan(state)

            _save_ugc_checkpoint(state, "after_clips")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_video_clips", e)

        # ─── Step 9: Assemble final video ────────────────────────────
        try:
            _progress("Assembling final video...", 0.92)

            # Build SegmentVisualPlans for the assembler (it expects this format)
            visual_plans = []
            for i, clip_path in enumerate(state.clip_paths):
                plan = SegmentVisualPlan(
                    segment_index=i,
                    num_images=1,
                    last_image_duration=state.segment_timings[i].duration if i < len(state.segment_timings) else 3.0,
                    video_path=clip_path,
                )
                if i < len(state.scene_image_paths):
                    plan.image_paths = [state.scene_image_paths[i]]
                visual_plans.append(plan)

            state.segment_visual_plans = visual_plans

            state.final_video_path = self.assembler.assemble_short_form(
                visual_plans=visual_plans,
                audio_path=state.audio_path,
                orientation=config.orientation,
                add_end_buffer=True,
                add_subtitles=False,
            )
            _save_ugc_checkpoint(state, "complete")
        except PipelineError:
            raise
        except Exception as e:
            _fail("assemble_final_video", e)

        _progress("UGC video generation complete!", 1.0)
        return state

    # ------------------------------------------------------------------
    # Private helpers for video clip generation
    # ------------------------------------------------------------------

    async def _generate_video_clips_via_api(self, state: UGCState) -> None:
        """
        Generate video clips using AI video generation APIs (Runway/Luma/Kling).

        Each scene's generated image is used as the base for image-to-video,
        with the scene's video_prompt providing the motion description.
        """
        config = state.config
        clip_paths: list[Path] = []

        tasks = []
        async with asyncio.TaskGroup() as tg:
            for i, scene in enumerate(state.scene_descriptions):
                # Use the generated scene image as the base for image-to-video
                base_image = (
                    state.scene_image_paths[i]
                    if i < len(state.scene_image_paths)
                    else None
                )

                # Clamp duration to API limits (3-10 seconds)
                duration = max(3, min(int(scene.duration_seconds), 10))

                task = tg.create_task(
                    self.video_service.generate_video(
                        prompt=scene.video_prompt,
                        provider=config.video_provider,
                        duration=duration,
                        orientation=config.orientation.lower(),
                        image_path=base_image,
                    )
                )
                tasks.append(task)

        for task in tasks:
            clip_paths.append(task.result())

        state.clip_paths = clip_paths

    async def _animate_with_zoompan(self, state: UGCState) -> None:
        """
        Animate scene images into video clips using FFmpeg zoompan effects.

        This is the cheaper/faster alternative to AI video generation.
        Uses the same proven zoompan technique from the main video pipeline.
        """
        clip_paths: list[Path] = []
        motion_pattern = ["zoom_in", "zoom_out", "pan_right", "ken_burns"]

        loop = asyncio.get_running_loop()
        tasks = []

        with ProcessPoolExecutor(NUM_WORKERS) as executor:
            for i, scene in enumerate(state.scene_descriptions):
                if i >= len(state.scene_image_paths):
                    break

                video_path = VIDEO_DIR / f"ugc_{uuid.uuid4().hex}.mp4"
                video_path.parent.mkdir(parents=True, exist_ok=True)
                clip_paths.append(video_path)

                # Each scene gets its full duration as a single image clip
                task = loop.run_in_executor(
                    executor,
                    animate_with_motion_effect,
                    [state.scene_image_paths[i]],  # Single image per scene
                    video_path,
                    float(scene.duration_seconds),  # ideal = scene duration
                    float(scene.duration_seconds),  # last = same (only 1 image)
                    motion_pattern,
                    i % len(motion_pattern),         # Cycle through patterns
                    state.config.orientation.lower(),
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

        state.clip_paths = clip_paths
