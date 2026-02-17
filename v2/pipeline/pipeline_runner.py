"""
Pipeline orchestrator for short-form and long-form video generation.

This module coordinates all pipeline stages (script generation, audio, images,
animation, assembly) with:
  - Per-step error handling that preserves state on failure
  - Automatic checkpointing after every API call so you never lose paid work
  - Progress callbacks for the Streamlit UI
  - A custom PipelineError that carries the partial state, so the UI can
    display whatever was generated before the failure occurred

Architecture:
  PipelineRunner owns instances of ScriptGenerator, AudioGenerator,
  ImageGenerator, and VideoAssembler. It calls them in sequence, saving
  state after each step. If any step fails, the state (with everything
  generated so far) is attached to the raised PipelineError.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TypeVar, Union

from v2.core.config import OUTPUT_DIR
from v2.core.models import (
    ShortFormState,
    LongFormState,
    SectionState,
    SegmentVisualPlan,
)
from v2.core.database import save_video_record
from v2.pipeline.script_generator import ScriptGenerator
from v2.pipeline.audio_generator import AudioGenerator
from v2.pipeline.image_generator import ImageGenerator
from v2.pipeline.video_assembler import VideoAssembler

logger = logging.getLogger(__name__)

# Type alias for the progress callback accepted by run_short_form / run_long_form.
# Signature: on_progress(human_readable_message, percent_complete_0_to_1)
ProgressCallback = Optional[Callable[[str, float], None]]

# Generic state type for the checkpoint helper
StateT = TypeVar("StateT", ShortFormState, LongFormState)

# Directory where JSON checkpoints are written after every step
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Custom exception that carries partial pipeline state
# ---------------------------------------------------------------------------
class PipelineError(Exception):
    """
    Raised when a pipeline step fails.

    Attributes:
        failed_step:  Human-readable name of the step that failed (e.g. "generate_images").
        partial_state: The pipeline state *at the moment of failure*. This contains
                       every field that was successfully populated before the error,
                       so the UI can display partial results (script, audio, images, etc.).
        original_error: The underlying exception that caused the failure.
    """

    def __init__(
        self,
        failed_step: str,
        partial_state: Union[ShortFormState, LongFormState],
        original_error: Exception,
    ):
        self.failed_step = failed_step
        self.partial_state = partial_state
        self.original_error = original_error
        super().__init__(
            f"Pipeline failed at step '{failed_step}': {original_error}"
        )


# ---------------------------------------------------------------------------
# Checkpoint helper
# ---------------------------------------------------------------------------
def _save_checkpoint(
    state: Union[ShortFormState, LongFormState],
    label: str,
) -> Optional[Path]:
    """
    Persist the current pipeline state to a JSON file on disk.

    This is called after every successful step so that if a later step fails,
    you still have a record of everything that was generated (and paid for)
    up to that point.

    Args:
        state: The current pipeline state (ShortFormState or LongFormState).
        label: A short tag appended to the filename (e.g. "after_script").

    Returns:
        Path to the written checkpoint file, or None if writing failed.
    """
    try:
        safe_label = label.replace(" ", "_").replace("/", "-")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = CHECKPOINT_DIR / f"{ts}_{safe_label}.json"
        # Exclude word_alignments (large, not JSON-friendly) from checkpoint
        path.write_text(
            state.model_dump_json(indent=2, exclude={"word_alignments"}),
            encoding="utf-8",
        )
        logger.debug(f"Checkpoint saved: {path.name}")
        return path
    except Exception as e:
        # Checkpointing is best-effort; never let it crash the pipeline
        logger.warning(f"Checkpoint write failed ({label}): {e}")
        return None


class PipelineRunner:
    """
    High-level orchestrator that runs the complete video generation pipeline.

    Usage:
        runner = PipelineRunner(model_provider="google")
        state = await runner.run_short_form(state, on_progress=callback)

    If any step fails, a ``PipelineError`` is raised whose ``partial_state``
    attribute contains everything that was successfully generated. The UI
    can catch this and still show the script, audio, images, etc.
    """

    def __init__(self, model_provider: str = "google"):
        """
        Initialize the pipeline with all required sub-services.

        Args:
            model_provider: Which LLM provider to use for script generation.
                            One of "google", "openai", "anthropic", "xai", "deepseek".
        """
        self.script_gen = ScriptGenerator(provider=model_provider)
        self.audio_gen = AudioGenerator()
        self.image_gen = ImageGenerator(script_gen=self.script_gen)
        self.assembler = VideoAssembler()

    # ------------------------------------------------------------------
    # SHORT-FORM pipeline
    # ------------------------------------------------------------------

    async def run_short_form(
        self,
        state: ShortFormState,
        on_progress: ProgressCallback = None,
    ) -> ShortFormState:
        """
        Run the full short-form video pipeline with per-step error recovery.

        Pipeline steps (each is individually guarded):
          1.  Generate goal
          2.  Generate hook
          3.  Generate script
          4.  Enhance script for TTS
          5.  Segment script into clips
          6.  Generate voice-over audio + word-level alignment
          7.  Plan visuals (how many images per segment)
          8.  Generate image descriptions via LLM
          9.  Generate images via provider APIs
          10. Animate images into video clips (FFmpeg zoompan or video API)
          11. Assemble final video (concat clips + mux audio)

        If any step fails:
          - The state is checkpointed immediately
          - A PipelineError is raised carrying the partial state
          - The UI can display everything that succeeded before the failure

        Args:
            state: Initial ShortFormState with user inputs populated.
            on_progress: Optional callback(message, percent) for the UI.

        Returns:
            Fully populated ShortFormState with final_video_path set.

        Raises:
            PipelineError: If any step fails. Contains partial_state and failed_step.
        """
        def _progress(msg: str, pct: float = 0.0):
            """Report progress to the UI callback and logger."""
            if on_progress:
                on_progress(msg, pct)
            logger.info(f"[{pct:.0%}] {msg}")

        def _fail(step_name: str, error: Exception) -> None:
            """Checkpoint state and raise PipelineError on any step failure."""
            logger.error(f"Pipeline failed at '{step_name}': {error}")
            logger.error(traceback.format_exc())
            _save_checkpoint(state, f"FAILED_{step_name}")
            raise PipelineError(step_name, state, error)

        # --- Step 1: Generate goal ---
        try:
            _progress("Generating video goal...", 0.05)
            state.goal = self.script_gen.generate_goal(
                topic=state.topic,
                purpose=state.purpose,
                target_audience=state.target_audience,
            )
            _save_checkpoint(state, "after_goal")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_goal", e)

        # --- Step 2: Generate hook ---
        try:
            _progress("Crafting opening hook...", 0.10)
            state.hook = self.script_gen.generate_hook(
                topic=state.topic,
                purpose=state.purpose,
                target_audience=state.target_audience,
                tone=state.tone,
                platform=state.platform,
            )
            _save_checkpoint(state, "after_hook")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_hook", e)

        # --- Step 3: Generate script ---
        try:
            _progress("Writing narration script...", 0.18)
            state.script = self.script_gen.generate_script(
                topic=state.topic,
                goal=state.goal,
                hook=state.hook,
                purpose=state.purpose,
                target_audience=state.target_audience,
                tone=state.tone,
                platform=state.platform,
                duration_seconds=state.duration_seconds,
                additional_instructions=state.additional_instructions,
                style_reference=state.style_reference,
            )
            _save_checkpoint(state, "after_script")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_script", e)

        # --- Step 4: Enhance script for TTS ---
        try:
            _progress("Enhancing script for voice generation...", 0.25)
            if state.enhance_for_tts:
                state.enhanced_script = self.script_gen.enhance_script(state.script)
            else:
                state.enhanced_script = state.script
            _save_checkpoint(state, "after_enhance")
        except PipelineError:
            raise
        except Exception as e:
            _fail("enhance_script", e)

        # --- Step 5: Segment script ---
        try:
            _progress("Segmenting script into clips...", 0.30)
            state.segments = self.script_gen.segment_script(
                script=state.script,
                enhanced_script=state.enhanced_script,
            )
            _save_checkpoint(state, "after_segment")
        except PipelineError:
            raise
        except Exception as e:
            _fail("segment_script", e)

        # --- Step 6: Generate audio + word-level alignment ---
        try:
            _progress("Generating voice-over audio...", 0.38)
            audio_path, word_alignments, segment_timings = (
                self.audio_gen.generate_and_align_short_form(
                    script=state.script,
                    enhanced_script=state.enhanced_script,
                    segments=state.segments,
                    voice_actor=state.voice_actor,
                    voice_model=state.voice_model_version,
                    use_enhanced=state.enhance_for_tts,
                )
            )
            state.audio_path = audio_path
            state.word_alignments = word_alignments
            state.segment_timings = segment_timings
            _save_checkpoint(state, "after_audio")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_audio", e)

        # --- Step 7: Plan visuals ---
        try:
            _progress("Planning visual layout...", 0.45)
            state.segment_visual_plans = self.image_gen.plan_visuals(
                segment_timings=state.segment_timings,
                ideal_duration=state.ideal_image_duration,
                min_duration=state.min_image_duration,
                single_image_per_segment=state.single_image_per_segment,
            )
        except PipelineError:
            raise
        except Exception as e:
            _fail("plan_visuals", e)

        # --- Step 8: Generate image descriptions ---
        try:
            _progress("Generating image descriptions...", 0.50)
            state.segment_visual_plans = await self.image_gen.generate_descriptions(
                segments=state.segments,
                visual_plans=state.segment_visual_plans,
                full_script=state.script,
                image_style=state.image_style,
                topic=state.topic,
                tone=state.tone,
                additional_image_requests=state.additional_image_requests,
                allow_faces=state.allow_faces,
            )
            _save_checkpoint(state, "after_image_descriptions")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_image_descriptions", e)

        # --- Step 9: Generate images ---
        try:
            _progress("Generating B-roll images...", 0.60)
            state.segment_visual_plans = await self.image_gen.generate_images(
                visual_plans=state.segment_visual_plans,
                image_provider=state.image_provider,
                orientation=state.orientation,
            )
            _save_checkpoint(state, "after_images")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_images", e)

        # --- Step 10: Create video clips (zoompan OR video generation API) ---
        try:
            if state.visual_mode == "video_gen":
                # Use AI video generation API (Runway, Luma, Kling)
                _progress(
                    f"Generating video clips via {state.video_provider}...", 0.78
                )
                state.segment_visual_plans = (
                    await self.image_gen.generate_video_clips(
                        visual_plans=state.segment_visual_plans,
                        segment_timings=state.segment_timings,
                        video_provider=state.video_provider,
                        orientation=state.orientation,
                        # Use base images if we generated them (image-to-video)
                        use_base_images=bool(
                            state.segment_visual_plans
                            and state.segment_visual_plans[0].image_paths
                        ),
                    )
                )
            else:
                # Default: zoompan animation on static images
                _progress("Animating images into video clips...", 0.78)
                state.segment_visual_plans = (
                    await self.image_gen.animate_segments(
                        visual_plans=state.segment_visual_plans,
                        ideal_image_duration=state.ideal_image_duration,
                        orientation=state.orientation,
                    )
                )
            state.clip_paths = [
                p.video_path for p in state.segment_visual_plans if p.video_path
            ]
            _save_checkpoint(state, "after_animation")
        except PipelineError:
            raise
        except Exception as e:
            _fail("animate_segments", e)

        # --- Step 11: Assemble final video ---
        try:
            _progress("Assembling final video...", 0.90)
            state.final_video_path = self.assembler.assemble_short_form(
                visual_plans=state.segment_visual_plans,
                audio_path=state.audio_path,
                orientation=state.orientation,
                add_end_buffer=state.add_end_buffer,
                add_subtitles=state.add_subtitles,
                word_alignments=(
                    state.word_alignments if state.add_subtitles else None
                ),
            )
            _save_checkpoint(state, "complete")
        except PipelineError:
            raise
        except Exception as e:
            _fail("assemble_final_video", e)

        # --- Save to video history database ---
        try:
            save_video_record(
                topic=state.topic,
                video_type="short_form",
                duration_seconds=state.duration_seconds,
                orientation=state.orientation,
                model_provider=state.model_provider,
                image_provider=state.image_provider,
                voice_actor=state.voice_actor,
                video_path=str(state.final_video_path),
                script=state.script,
                goal=state.goal,
            )
        except Exception as e:
            logger.warning(f"Failed to save video history: {e}")

        _progress("Video generation complete!", 1.0)
        return state

    # ------------------------------------------------------------------
    # LONG-FORM pipeline
    # ------------------------------------------------------------------

    async def run_long_form(
        self,
        state: LongFormState,
        on_progress: ProgressCallback = None,
    ) -> LongFormState:
        """
        Run the full long-form video pipeline with per-step error recovery.

        Pipeline overview:
          1. Generate goal
          2. Generate structure (5-8 sections)
          3. For each section (sequential for script continuity):
             a. Write section script
             b. Segment the section script
             c. Generate section audio + alignment
             d. Plan visuals
             e. Generate image descriptions
             f. Generate images (real API, not mock)
             g. Animate images into clips
             h. Assemble section video (clips + section audio)
          4. Concatenate all section videos into final video

        Error handling:
          Each step is individually guarded. If section 3 fails at step (f),
          sections 1 and 2 are fully intact in state.sections, and section 3
          has its script, audio, and descriptions preserved. The UI can show
          all of this.

        Args:
            state: Initial LongFormState with user inputs populated.
            on_progress: Optional callback(message, percent) for the UI.

        Returns:
            Fully populated LongFormState with final_video_path set.

        Raises:
            PipelineError: If any step fails. Contains partial_state.
        """
        def _progress(msg: str, pct: float = 0.0):
            if on_progress:
                on_progress(msg, pct)
            logger.info(f"[{pct:.0%}] {msg}")

        def _fail(step_name: str, error: Exception) -> None:
            logger.error(f"Long-form pipeline failed at '{step_name}': {error}")
            logger.error(traceback.format_exc())
            _save_checkpoint(state, f"FAILED_{step_name}")
            raise PipelineError(step_name, state, error)

        # --- Step 1: Generate goal ---
        try:
            _progress("Generating video goal...", 0.03)
            state.goal = self.script_gen.generate_goal(
                topic=state.topic,
                purpose=state.purpose,
                target_audience=state.target_audience,
            )
            _save_checkpoint(state, "lf_after_goal")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_goal", e)

        # --- Step 2: Generate structure ---
        try:
            _progress("Generating video structure...", 0.08)
            structures = self.script_gen.generate_structure(
                topic=state.topic,
                purpose=state.purpose,
                target_audience=state.target_audience,
                tone=state.tone,
                goal=state.goal,
            )
            num_sections = len(structures)
            state.sections = [SectionState(section_structure=s) for s in structures]
            _progress(f"Structure: {num_sections} sections planned", 0.10)
            _save_checkpoint(state, "lf_after_structure")
        except PipelineError:
            raise
        except Exception as e:
            _fail("generate_structure", e)

        # --- Step 3: Process each section ---
        cumulative_script = ""
        num_sections = len(state.sections)
        per_section_weight = 0.80 / max(num_sections, 1)

        for sec_idx, section in enumerate(state.sections):
            base_pct = 0.10 + sec_idx * per_section_weight
            sec_label = f"Section {sec_idx + 1}/{num_sections}"

            # 3a: Generate section script (must be sequential for continuity)
            try:
                _progress(f"{sec_label}: Writing script...", base_pct)
                section.section_script = self.script_gen.generate_section_script(
                    topic=state.topic,
                    purpose=state.purpose,
                    target_audience=state.target_audience,
                    tone=state.tone,
                    section_info=section.section_structure,
                    cumulative_script=cumulative_script,
                    additional_instructions=state.additional_instructions,
                    style_reference=state.style_reference,
                )
                cumulative_script += section.section_script + " "
                _save_checkpoint(state, f"lf_sec{sec_idx}_script")
            except PipelineError:
                raise
            except Exception as e:
                _fail(f"section_{sec_idx}_generate_script", e)

            # 3b: Segment section script
            try:
                _progress(
                    f"{sec_label}: Segmenting...",
                    base_pct + per_section_weight * 0.10,
                )
                section.segments = self.script_gen.segment_section_script(
                    section_script=section.section_script
                )
            except PipelineError:
                raise
            except Exception as e:
                _fail(f"section_{sec_idx}_segment", e)

            # 3c: Generate audio + word-level alignment
            try:
                _progress(
                    f"{sec_label}: Generating audio...",
                    base_pct + per_section_weight * 0.20,
                )
                audio_path, words, timings = (
                    self.audio_gen.generate_and_align_section(
                        section_script=section.section_script,
                        segments=section.segments,
                        voice_actor=state.voice_actor,
                        voice_model=state.voice_model_version,
                    )
                )
                section.audio_path = audio_path
                section.word_alignments = words
                section.segment_timings = timings
                _save_checkpoint(state, f"lf_sec{sec_idx}_audio")
            except PipelineError:
                raise
            except Exception as e:
                _fail(f"section_{sec_idx}_audio", e)

            # 3d: Plan visuals
            try:
                section.segment_visual_plans = self.image_gen.plan_visuals(
                    segment_timings=section.segment_timings,
                    ideal_duration=state.ideal_image_duration,
                    min_duration=state.min_image_duration,
                    single_image_per_segment=state.single_image_per_segment,
                )
            except PipelineError:
                raise
            except Exception as e:
                _fail(f"section_{sec_idx}_plan_visuals", e)

            # 3e: Generate image descriptions
            try:
                _progress(
                    f"{sec_label}: Generating image descriptions...",
                    base_pct + per_section_weight * 0.35,
                )
                section.segment_visual_plans = (
                    await self.image_gen.generate_descriptions(
                        segments=section.segments,
                        visual_plans=section.segment_visual_plans,
                        full_script=section.section_script,
                        image_style=state.image_style,
                        topic=state.topic,
                        tone=state.tone,
                        additional_image_requests=state.additional_image_requests,
                        allow_faces=state.allow_faces,
                    )
                )
                _save_checkpoint(state, f"lf_sec{sec_idx}_img_desc")
            except PipelineError:
                raise
            except Exception as e:
                _fail(f"section_{sec_idx}_image_descriptions", e)

            # 3f: Generate REAL images (not pseudo/mock)
            try:
                _progress(
                    f"{sec_label}: Generating images...",
                    base_pct + per_section_weight * 0.50,
                )
                section.segment_visual_plans = (
                    await self.image_gen.generate_images(
                        visual_plans=section.segment_visual_plans,
                        image_provider=state.image_provider,
                        orientation=state.orientation,
                    )
                )
                _save_checkpoint(state, f"lf_sec{sec_idx}_images")
            except PipelineError:
                raise
            except Exception as e:
                _fail(f"section_{sec_idx}_generate_images", e)

            # 3g: Create video clips (zoompan OR video generation API)
            try:
                if state.visual_mode == "video_gen":
                    _progress(
                        f"{sec_label}: Generating video clips via {state.video_provider}...",
                        base_pct + per_section_weight * 0.70,
                    )
                    section.segment_visual_plans = (
                        await self.image_gen.generate_video_clips(
                            visual_plans=section.segment_visual_plans,
                            segment_timings=section.segment_timings,
                            video_provider=state.video_provider,
                            orientation=state.orientation,
                            use_base_images=bool(
                                section.segment_visual_plans
                                and section.segment_visual_plans[0].image_paths
                            ),
                        )
                    )
                else:
                    _progress(
                        f"{sec_label}: Animating clips...",
                        base_pct + per_section_weight * 0.70,
                    )
                    section.segment_visual_plans = (
                        await self.image_gen.animate_segments(
                            visual_plans=section.segment_visual_plans,
                            ideal_image_duration=state.ideal_image_duration,
                            orientation=state.orientation,
                        )
                    )
                section.clip_paths = [
                    p.video_path
                    for p in section.segment_visual_plans
                    if p.video_path
                ]
            except PipelineError:
                raise
            except Exception as e:
                _fail(f"section_{sec_idx}_animate", e)

            # 3h: Assemble section video (clips + section audio)
            try:
                _progress(
                    f"{sec_label}: Assembling section video...",
                    base_pct + per_section_weight * 0.90,
                )
                section.section_video_path = self.assembler.assemble_section(
                    visual_plans=section.segment_visual_plans,
                    audio_path=section.audio_path,
                    section_index=sec_idx,
                )
                _save_checkpoint(state, f"lf_sec{sec_idx}_complete")
            except PipelineError:
                raise
            except Exception as e:
                _fail(f"section_{sec_idx}_assemble", e)

        # Build the full concatenated script
        state.full_script = cumulative_script.strip()

        # --- Step 4: Concatenate all sections into final video ---
        try:
            _progress("Assembling final long-form video...", 0.93)
            section_paths = [
                s.section_video_path
                for s in state.sections
                if s.section_video_path
            ]
            state.final_video_path = self.assembler.assemble_long_form(
                section_video_paths=section_paths
            )
            _save_checkpoint(state, "lf_complete")
        except PipelineError:
            raise
        except Exception as e:
            _fail("assemble_final_long_form", e)

        # --- Save to video history database ---
        try:
            save_video_record(
                topic=state.topic,
                video_type="long_form",
                duration_seconds=state.duration_seconds,
                orientation=state.orientation,
                model_provider=state.model_provider,
                image_provider=state.image_provider,
                voice_actor=state.voice_actor,
                video_path=str(state.final_video_path),
                script=state.full_script,
                goal=state.goal,
            )
        except Exception as e:
            logger.warning(f"Failed to save video history: {e}")

        _progress("Long-form video generation complete!", 1.0)
        return state
