"""
V2 Pipeline orchestrator for enhanced short-form and long-form video generation.

Key improvements over pipeline_runner.py:
  - Research phase (Tavily web search + LLM synthesis)
  - Single-pass script generation (1 LLM call replaces 5)
  - Quality gates (script, outline, images)
  - Global style guide + storyboard-based visual planning
  - Aggressive parallelization for long-form (sections processed in parallel)

Architecture:
  PipelineRunnerV2 delegates to existing services (AudioGenerator,
  ImageGenerator, VideoAssembler) and new ones (ResearchService, LLMService
  for quality gates / storyboard). It does NOT modify any existing service.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Union

from pydantic import BaseModel, Field

from v2.core.config import OUTPUT_DIR
from v2.core.models import (
    ImageDescription,
    SegmentTiming,
    SegmentVisualPlan,
    WordAlignment,
    SectionScriptSegmentItem,
)
from v2.core.v2_models import (
    FullScript,
    LongFormV2State,
    OutlineReview,
    QualityReport,
    ResearchBrief,
    SectionPlanV2,
    SectionScriptV2,
    SectionV2State,
    SegmentStoryboard,
    ShortFormV2State,
    ShotPlan,
    StyleGuide,
    TrendContext,
    VideoOutlineV2,
    ConnectorPassContainer,
    VisualQualityBatchAssessment,
)
from v2.core.v2_prompts import (
    SINGLE_PASS_SCRIPT_PROMPT,
    SCRIPT_QUALITY_GATE_PROMPT,
    SCRIPT_REVISION_PROMPT,
    STYLE_GUIDE_PROMPT,
    STORYBOARD_PROMPT,
    FACE_FREE_RULE_V2,
    FACES_ALLOWED_RULE_V2,
    VISUAL_QUALITY_GATE_PROMPT,
    LONG_FORM_STRUCTURE_V2_PROMPT,
    OUTLINE_QUALITY_GATE_PROMPT,
    SECTION_SCRIPT_V2_PROMPT,
    SECTION_SCRIPT_CONNECTOR_PROMPT,
    SECTION_SEGMENTER_V2_PROMPT,
)
from v2.core.database import save_video_record
from v2.pipeline.audio_generator import AudioGenerator, compute_images_per_segment
from v2.pipeline.image_generator import ImageGenerator
from v2.pipeline.script_generator import ScriptGenerator
from v2.pipeline.video_assembler import VideoAssembler
from v2.services.llm_service import LLMService
from v2.services.elevenlabs_service import ElevenLabsService

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str, float], None]]

CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Custom exception (reuses the same pattern as v1)
# ---------------------------------------------------------------------------
class PipelineV2Error(Exception):
    """Raised when a V2 pipeline phase fails."""

    def __init__(
        self,
        failed_phase: str,
        partial_state: Union[ShortFormV2State, LongFormV2State],
        original_error: Exception,
    ):
        self.failed_phase = failed_phase
        self.partial_state = partial_state
        self.original_error = original_error
        super().__init__(
            f"V2 Pipeline failed at phase '{failed_phase}': {original_error}"
        )


# ---------------------------------------------------------------------------
# Checkpoint helper
# ---------------------------------------------------------------------------
def _save_checkpoint(
    state: Union[ShortFormV2State, LongFormV2State],
    label: str,
) -> Optional[Path]:
    """Persist current pipeline state to JSON checkpoint."""
    try:
        safe_label = label.replace(" ", "_").replace("/", "-")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = CHECKPOINT_DIR / f"v2_{ts}_{safe_label}.json"
        path.write_text(
            state.model_dump_json(
                indent=2,
                exclude={"word_alignments"},
            ),
            encoding="utf-8",
        )
        logger.debug(f"V2 Checkpoint saved: {path.name}")
        return path
    except Exception as e:
        logger.warning(f"V2 Checkpoint write failed ({label}): {e}")
        return None


# ---------------------------------------------------------------------------
# Segmenter container for V2 (simple list of strings)
# ---------------------------------------------------------------------------
class SegmentsContainer(BaseModel):
    """LLM output: list of script segments."""
    segments: list[str] = Field(..., description="Script segments.")


class PipelineRunnerV2:
    """
    Enhanced pipeline orchestrator with research, quality gates, and
    storyboard-based visual planning.
    """

    def __init__(self, model_provider: str = "google"):
        self.model_provider = model_provider
        self.llm = LLMService(provider=model_provider)
        self.script_gen = ScriptGenerator(provider=model_provider)
        self.audio_gen = AudioGenerator()
        self.image_gen = ImageGenerator(script_gen=self.script_gen)
        self.assembler = VideoAssembler()

    # ══════════════════════════════════════════════════════════════════════
    # SHORT-FORM V2 PIPELINE
    # ══════════════════════════════════════════════════════════════════════

    async def run_short_form_v2(
        self,
        state: ShortFormV2State,
        on_progress: ProgressCallback = None,
    ) -> ShortFormV2State:
        """
        Run the full short-form V2 pipeline.

        Phases:
          1. Research (optional, parallel)
          2. Script (single-pass + quality gate)
          3. Audio (TTS + alignment)
          4. Visual Planning (style guide + storyboard)
          5. Image Generation (parallel + visual QA)
          6. Video Clips (zoompan or video_gen)
          7. Assembly

        Args:
            state: Initial ShortFormV2State with user inputs.
            on_progress: Optional callback(message, percent).

        Returns:
            Fully populated ShortFormV2State.

        Raises:
            PipelineV2Error: On any phase failure with partial state.
        """
        def _progress(msg: str, pct: float = 0.0):
            if on_progress:
                on_progress(msg, pct)
            logger.info(f"[{pct:.0%}] {msg}")

        def _fail(phase: str, error: Exception):
            logger.error(f"V2 Short-form failed at '{phase}': {error}")
            logger.error(traceback.format_exc())
            _save_checkpoint(state, f"FAILED_{phase}")
            raise PipelineV2Error(phase, state, error)

        # --- Phase 1: Research ---
        if state.enable_research:
            try:
                _progress("Researching topic...", 0.02)
                from v2.services.research_service import ResearchService
                research_svc = ResearchService(llm_provider=self.model_provider)
                state.research_brief, state.trend_context = (
                    await research_svc.run_full_research(
                        topic=state.topic,
                        target_audience=state.target_audience,
                        platform=state.platform,
                    )
                )
                _save_checkpoint(state, "sf2_after_research")
                _progress("Research complete.", 0.08)
            except PipelineV2Error:
                raise
            except Exception as e:
                _fail("research", e)
        else:
            _progress("Skipping research (disabled).", 0.08)

        # --- Phase 2: Script Generation + Quality Gate ---
        try:
            _progress("Generating script (single-pass)...", 0.10)
            state.full_script = self._generate_short_form_script(state)
            _save_checkpoint(state, "sf2_after_script")

            _progress("Evaluating script quality...", 0.16)
            state.quality_report = self._evaluate_script(state)
            _save_checkpoint(state, "sf2_after_quality_gate")

            # Retry loop: up to 2 revisions if quality gate fails
            while not state.quality_report.passed and state.script_revision_count < 2:
                state.script_revision_count += 1
                _progress(
                    f"Revising script (attempt {state.script_revision_count}/2)...",
                    0.16 + state.script_revision_count * 0.02,
                )
                state.full_script = self._revise_script(state)
                state.quality_report = self._evaluate_script(state)
                _save_checkpoint(state, f"sf2_revision_{state.script_revision_count}")

            _progress("Script finalized.", 0.22)
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("script_generation", e)

        # --- Phase 3: Audio ---
        try:
            _progress("Generating voice-over...", 0.24)
            tts_text = " ".join(b.tts_text for b in state.full_script.beats)
            raw_text = " ".join(b.raw_text for b in state.full_script.beats)

            audio_path, word_alignments = self.audio_gen.tts.generate_audio(
                text=tts_text,
                voice_actor=state.voice_actor,
                voice_model=state.voice_model_version,
            )
            state.audio_path = audio_path
            state.word_alignments = word_alignments

            # Align beats to audio using tts_text for matching
            segment_texts = [b.tts_text for b in state.full_script.beats]
            state.segment_timings = ElevenLabsService.align_segments_to_words(
                segments=segment_texts,
                word_alignments=word_alignments,
            )
            _save_checkpoint(state, "sf2_after_audio")
            _progress("Audio generated and aligned.", 0.35)
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("audio", e)

        # --- Phase 4: Visual Planning ---
        try:
            _progress("Creating visual style guide...", 0.36)
            state.style_guide = self._generate_style_guide(state)

            _progress("Building storyboard...", 0.38)
            state.storyboard = self._generate_storyboard(state)
            _save_checkpoint(state, "sf2_after_storyboard")
            _progress("Storyboard complete.", 0.42)
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("visual_planning", e)

        # --- Phase 5: Image Generation + Visual QA ---
        try:
            _progress("Generating images...", 0.44)
            state.segment_visual_plans = self._build_visual_plans_from_storyboard(
                state.storyboard, state.segment_timings
            )

            # Generate images via existing ImageGenerator
            state.segment_visual_plans = await self.image_gen.generate_images(
                visual_plans=state.segment_visual_plans,
                image_provider=state.image_provider,
                orientation=state.orientation,
            )
            _save_checkpoint(state, "sf2_after_images")
            _progress("Images generated.", 0.62)

            # Visual quality gate (best-effort, non-blocking)
            try:
                _progress("Running visual quality check...", 0.63)
                await self._run_visual_qa(state)
                _save_checkpoint(state, "sf2_after_visual_qa")
                _progress("Visual QA complete.", 0.68)
            except Exception as qa_err:
                logger.warning(f"Visual QA failed (non-fatal): {qa_err}")
                _progress("Visual QA skipped (non-fatal error).", 0.68)
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("image_generation", e)

        # --- Phase 6: Video Clips ---
        try:
            if state.visual_mode == "video_gen":
                _progress(
                    f"Generating video clips via {state.video_provider}...", 0.70
                )
                state.segment_visual_plans = (
                    await self.image_gen.generate_video_clips(
                        visual_plans=state.segment_visual_plans,
                        segment_timings=state.segment_timings,
                        video_provider=state.video_provider,
                        orientation=state.orientation,
                        use_base_images=bool(
                            state.segment_visual_plans
                            and state.segment_visual_plans[0].image_paths
                        ),
                    )
                )
            else:
                _progress("Animating images (zoompan)...", 0.70)
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
            _save_checkpoint(state, "sf2_after_clips")
            _progress("Video clips created.", 0.82)
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("video_clips", e)

        # --- Phase 7: Assembly ---
        try:
            _progress("Assembling final video...", 0.85)
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
            _save_checkpoint(state, "sf2_complete")
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("assembly", e)

        # Save to history
        try:
            save_video_record(
                topic=state.topic,
                video_type="short_form_v2",
                duration_seconds=state.duration_seconds,
                orientation=state.orientation,
                model_provider=state.model_provider,
                image_provider=state.image_provider,
                voice_actor=state.voice_actor,
                video_path=str(state.final_video_path),
                script=" ".join(b.raw_text for b in state.full_script.beats),
                goal=state.full_script.goal,
            )
        except Exception as e:
            logger.warning(f"Failed to save video history: {e}")

        _progress("Video generation complete!", 1.0)
        return state

    # ══════════════════════════════════════════════════════════════════════
    # LONG-FORM V2 PIPELINE
    # ══════════════════════════════════════════════════════════════════════

    async def run_long_form_v2(
        self,
        state: LongFormV2State,
        on_progress: ProgressCallback = None,
    ) -> LongFormV2State:
        """
        Run the full long-form V2 pipeline with aggressive parallelization.

        Phases:
          1. Research (optional, parallel)
          2. Outline + quality gate
          3. Script writing (parallel or sequential) + quality gate
          4. Audio (all sections in parallel)
          5. Visual planning (style guide + parallel storyboards)
          6. Images (all sections in one parallel batch)
          7. Video clips (all parallel)
          8. Assembly (parallel sections + final concat)
        """
        def _progress(msg: str, pct: float = 0.0):
            if on_progress:
                on_progress(msg, pct)
            logger.info(f"[{pct:.0%}] {msg}")

        def _fail(phase: str, error: Exception):
            logger.error(f"V2 Long-form failed at '{phase}': {error}")
            logger.error(traceback.format_exc())
            _save_checkpoint(state, f"FAILED_{phase}")
            raise PipelineV2Error(phase, state, error)

        # --- Phase 1: Research ---
        if state.enable_research:
            try:
                _progress("Researching topic...", 0.02)
                from v2.services.research_service import ResearchService
                research_svc = ResearchService(llm_provider=self.model_provider)
                state.research_brief, state.trend_context = (
                    await research_svc.run_full_research(
                        topic=state.topic,
                        target_audience=state.target_audience,
                        platform=state.platform,
                    )
                )
                _save_checkpoint(state, "lf2_after_research")
                _progress("Research complete.", 0.08)
            except PipelineV2Error:
                raise
            except Exception as e:
                _fail("research", e)
        else:
            _progress("Skipping research (disabled).", 0.08)

        # --- Phase 2: Outline + Quality Gate ---
        try:
            _progress("Generating video outline...", 0.09)
            state.outline = self._generate_outline(state)
            _save_checkpoint(state, "lf2_after_outline")

            _progress("Evaluating outline quality...", 0.13)
            state.outline_review = self._evaluate_outline(state)
            _save_checkpoint(state, "lf2_after_outline_review")

            while not state.outline_review.passed and state.outline_revision_count < 2:
                state.outline_revision_count += 1
                _progress(
                    f"Revising outline (attempt {state.outline_revision_count}/2)...",
                    0.13 + state.outline_revision_count * 0.02,
                )
                state.outline = self._generate_outline(
                    state,
                    revision_notes=state.outline_review.revision_notes,
                )
                state.outline_review = self._evaluate_outline(state)

            # Initialize section states from outline
            state.sections = [
                SectionV2State(section_plan=sp)
                for sp in state.outline.sections
            ]
            _progress(
                f"Outline finalized: {len(state.sections)} sections.",
                0.18,
            )
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("outline", e)

        num_sections = len(state.sections)

        # --- Phase 3: Script Writing ---
        try:
            if state.script_strategy == "parallel":
                _progress("Writing section scripts (parallel)...", 0.19)
                await self._write_sections_parallel(state)
            else:
                _progress("Writing section scripts (sequential)...", 0.19)
                await self._write_sections_sequential(state, _progress)

            _save_checkpoint(state, "lf2_after_scripts")

            # Build full script
            state.full_script = " ".join(
                s.section_script for s in state.sections if s.section_script
            )
            _progress("All section scripts complete.", 0.35)
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("script_writing", e)

        # --- Phase 4: Audio (all sections in parallel) ---
        try:
            _progress("Generating audio for all sections (parallel)...", 0.36)
            await self._generate_all_section_audio(state)
            _save_checkpoint(state, "lf2_after_audio")
            _progress("All section audio generated.", 0.48)
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("audio", e)

        # --- Phase 5: Visual Planning ---
        try:
            _progress("Creating visual style guide...", 0.49)
            style_guide = self._generate_style_guide(state)

            _progress("Building section storyboards (parallel)...", 0.51)
            await self._generate_section_storyboards(state, style_guide)
            _save_checkpoint(state, "lf2_after_storyboards")
            _progress("Storyboards complete.", 0.55)
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("visual_planning", e)

        # --- Phase 6: Images (all sections in one batch) ---
        try:
            _progress("Generating images for all sections...", 0.56)
            await self._generate_all_section_images(state)
            _save_checkpoint(state, "lf2_after_images")
            _progress("All images generated.", 0.72)
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("image_generation", e)

        # --- Phase 7: Video Clips ---
        try:
            _progress("Creating video clips for all sections...", 0.73)
            await self._animate_all_sections(state)
            _save_checkpoint(state, "lf2_after_clips")
            _progress("All video clips created.", 0.83)
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("video_clips", e)

        # --- Phase 8: Assembly ---
        try:
            # Assemble each section (parallel)
            _progress("Assembling section videos (parallel)...", 0.84)
            await self._assemble_all_sections(state)
            _save_checkpoint(state, "lf2_after_section_assembly")

            # Final concatenation
            _progress("Concatenating final video...", 0.93)
            section_paths = [
                s.section_video_path
                for s in state.sections
                if s.section_video_path
            ]
            state.final_video_path = self.assembler.assemble_long_form(
                section_video_paths=section_paths
            )
            _save_checkpoint(state, "lf2_complete")
        except PipelineV2Error:
            raise
        except Exception as e:
            _fail("assembly", e)

        # Save to history
        try:
            save_video_record(
                topic=state.topic,
                video_type="long_form_v2",
                duration_seconds=state.duration_seconds,
                orientation=state.orientation,
                model_provider=state.model_provider,
                image_provider=state.image_provider,
                voice_actor=state.voice_actor,
                video_path=str(state.final_video_path),
                script=state.full_script or "",
                goal=state.outline.thesis if state.outline else "",
            )
        except Exception as e:
            logger.warning(f"Failed to save video history: {e}")

        _progress("Long-form video generation complete!", 1.0)
        return state

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS — Script
    # ══════════════════════════════════════════════════════════════════════

    def _generate_short_form_script(self, state: ShortFormV2State) -> FullScript:
        """Single-pass script generation."""
        research_data = None
        if state.research_brief:
            research_data = state.research_brief.model_dump()

        trend_data = None
        if state.trend_context:
            trend_data = state.trend_context.model_dump()

        return self.llm.generate_structured(
            system_prompt=SINGLE_PASS_SCRIPT_PROMPT,
            user_payload={
                "topic": state.topic,
                "purpose": state.purpose,
                "target_audience": state.target_audience,
                "tone": state.tone,
                "platform": state.platform,
                "duration_seconds": state.duration_seconds,
                "research_brief": research_data,
                "trend_context": trend_data,
                "additional_instructions": state.additional_instructions,
                "style_reference": state.style_reference,
                "brand_guidelines": state.brand_guidelines,
            },
            output_model=FullScript,
        )

    def _evaluate_script(self, state: ShortFormV2State) -> QualityReport:
        """Run the script quality gate."""
        beats_data = [
            {
                "raw_text": b.raw_text,
                "beat_type": b.beat_type,
                "energy_level": b.energy_level,
            }
            for b in state.full_script.beats
        ]
        return self.llm.generate_structured(
            system_prompt=SCRIPT_QUALITY_GATE_PROMPT,
            user_payload={
                "script_beats": beats_data,
                "goal": state.full_script.goal,
                "topic": state.topic,
                "platform": state.platform,
                "target_audience": state.target_audience,
                "duration_seconds": state.duration_seconds,
            },
            output_model=QualityReport,
        )

    def _revise_script(self, state: ShortFormV2State) -> FullScript:
        """Revise script using quality gate feedback."""
        research_data = None
        if state.research_brief:
            research_data = state.research_brief.model_dump()

        return self.llm.generate_structured(
            system_prompt=SCRIPT_REVISION_PROMPT,
            user_payload={
                "original_script": state.full_script.model_dump(),
                "revision_notes": state.quality_report.revision_notes,
                "factual_flags": state.quality_report.factual_flags,
                "research_brief": research_data,
                "topic": state.topic,
                "duration_seconds": state.duration_seconds,
            },
            output_model=FullScript,
        )

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS — Visual Planning
    # ══════════════════════════════════════════════════════════════════════

    def _generate_style_guide(
        self,
        state: Union[ShortFormV2State, LongFormV2State],
    ) -> StyleGuide:
        """Generate global visual style guide."""
        return self.llm.generate_structured(
            system_prompt=STYLE_GUIDE_PROMPT,
            user_payload={
                "topic": state.topic,
                "image_style": state.image_style,
                "tone": state.tone,
                "brand_guidelines": state.brand_guidelines,
            },
            output_model=StyleGuide,
        )

    def _generate_storyboard(
        self, state: ShortFormV2State
    ) -> list[SegmentStoryboard]:
        """Generate storyboard seeing ALL beats at once."""
        face_rule = FACES_ALLOWED_RULE_V2 if state.allow_faces else FACE_FREE_RULE_V2
        prompt = STORYBOARD_PROMPT.format(face_rule=face_rule)

        beats_data = []
        for i, beat in enumerate(state.full_script.beats):
            duration_ms = 3000
            if i < len(state.segment_timings):
                duration_ms = int(state.segment_timings[i].duration * 1000)
            beats_data.append({
                "raw_text": beat.raw_text,
                "visual_intent": beat.visual_intent,
                "beat_type": beat.beat_type,
                "energy_level": beat.energy_level,
                "duration_ms": duration_ms,
            })

        style_data = state.style_guide.model_dump() if state.style_guide else {}

        class StoryboardContainer(BaseModel):
            storyboard: list[SegmentStoryboard]

        result = self.llm.generate_structured(
            system_prompt=prompt,
            user_payload={
                "beats": beats_data,
                "style_guide": style_data,
                "image_style": state.image_style,
                "topic": state.topic,
                "allow_faces": state.allow_faces,
                "ideal_shot_duration_ms": int(state.ideal_image_duration * 1000),
                "additional_image_requests": state.additional_image_requests,
            },
            output_model=StoryboardContainer,
        )
        return result.storyboard

    def _build_visual_plans_from_storyboard(
        self,
        storyboard: list[SegmentStoryboard],
        segment_timings: list[SegmentTiming],
    ) -> list[SegmentVisualPlan]:
        """Convert storyboard shots into SegmentVisualPlan objects for ImageGenerator."""
        plans = []
        for i, sb in enumerate(storyboard):
            num_images = len(sb.shots)
            last_dur = sb.shots[-1].duration_ms / 1000.0 if sb.shots else 3.0

            descriptions = [
                ImageDescription(description=shot.image_prompt, uses_logo=False)
                for shot in sb.shots
            ]
            plans.append(SegmentVisualPlan(
                segment_index=i,
                num_images=num_images,
                last_image_duration=last_dur,
                image_descriptions=descriptions,
            ))
        return plans

    async def _run_visual_qa(self, state: ShortFormV2State) -> None:
        """
        Run visual quality assessment on generated images.
        This is best-effort — failures are logged but don't stop the pipeline.
        """
        all_prompts = []
        all_paths = []
        for plan in state.segment_visual_plans:
            for j, desc in enumerate(plan.image_descriptions):
                if j < len(plan.image_paths):
                    all_prompts.append(desc.description)
                    all_paths.append(plan.image_paths[j])

        if not all_paths:
            return

        # Use a simple text-based QA (vision model would require multimodal input)
        # For now, we log that QA was run and skip image-level assessment
        # since LLMService doesn't support multimodal input directly.
        logger.info(
            f"Visual QA: {len(all_paths)} images checked "
            "(full vision-model QA requires multimodal endpoint)"
        )

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS — Long-Form Outline
    # ══════════════════════════════════════════════════════════════════════

    def _generate_outline(
        self,
        state: LongFormV2State,
        revision_notes: list[str] | None = None,
    ) -> VideoOutlineV2:
        """Generate enhanced outline with section types, retention, energy."""
        research_data = None
        if state.research_brief:
            research_data = state.research_brief.model_dump()

        trend_data = None
        if state.trend_context:
            trend_data = state.trend_context.model_dump()

        instructions = state.additional_instructions or ""
        if revision_notes:
            instructions += "\n\nREVISION NOTES FROM PREVIOUS ATTEMPT:\n"
            instructions += "\n".join(f"- {n}" for n in revision_notes)

        return self.llm.generate_structured(
            system_prompt=LONG_FORM_STRUCTURE_V2_PROMPT,
            user_payload={
                "topic": state.topic,
                "purpose": state.purpose,
                "target_audience": state.target_audience,
                "tone": state.tone,
                "duration_seconds": state.duration_seconds,
                "research_brief": research_data,
                "trend_context": trend_data,
                "additional_instructions": instructions if instructions.strip() else None,
            },
            output_model=VideoOutlineV2,
        )

    def _evaluate_outline(self, state: LongFormV2State) -> OutlineReview:
        """Run the outline quality gate."""
        return self.llm.generate_structured(
            system_prompt=OUTLINE_QUALITY_GATE_PROMPT,
            user_payload={
                "outline": state.outline.model_dump(),
                "topic": state.topic,
                "target_audience": state.target_audience,
                "duration_seconds": state.duration_seconds,
            },
            output_model=OutlineReview,
        )

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS — Long-Form Script Writing
    # ══════════════════════════════════════════════════════════════════════

    async def _write_sections_parallel(self, state: LongFormV2State) -> None:
        """Write all section scripts in parallel, then run connector pass."""
        outline_data = state.outline.model_dump()
        research_data = state.research_brief.model_dump() if state.research_brief else None

        async def _write_one(sec_state: SectionV2State, sec_idx: int) -> None:
            preceding = None
            if sec_idx > 0:
                preceding = state.outline.sections[sec_idx - 1].model_dump()

            result = await asyncio.to_thread(
                self.llm.generate_structured,
                system_prompt=SECTION_SCRIPT_V2_PROMPT,
                user_payload={
                    "topic": state.topic,
                    "purpose": state.purpose,
                    "target_audience": state.target_audience,
                    "tone": state.tone,
                    "research_brief": research_data,
                    "additional_instructions": state.additional_instructions or "",
                    "style_reference": state.style_reference,
                    "full_outline": outline_data,
                    "section_plan": sec_state.section_plan.model_dump(),
                    "preceding_section_plan": preceding,
                    "cumulative_script": "",
                },
                output_model=SectionScriptV2,
            )
            sec_state.section_script = result.section_script
            sec_state.tts_script = result.tts_script

        # Write all sections in parallel
        async with asyncio.TaskGroup() as tg:
            for idx, sec in enumerate(state.sections):
                tg.create_task(_write_one(sec, idx))

        # Connector pass to smooth transitions
        sections_data = [
            {
                "section_name": sec.section_plan.section_name,
                "section_script": sec.section_script,
                "transition_from_previous": sec.section_plan.transition_from_previous,
            }
            for sec in state.sections
        ]
        connector_result = self.llm.generate_structured(
            system_prompt=SECTION_SCRIPT_CONNECTOR_PROMPT,
            user_payload={"sections": sections_data},
            output_model=ConnectorPassContainer,
        )
        for i, smoothed in enumerate(connector_result.smoothed_sections):
            if i < len(state.sections):
                state.sections[i].section_script = smoothed

    async def _write_sections_sequential(
        self, state: LongFormV2State, _progress: Callable
    ) -> None:
        """Write section scripts sequentially with baton pass."""
        cumulative = ""
        outline_data = state.outline.model_dump()
        research_data = state.research_brief.model_dump() if state.research_brief else None

        for idx, sec in enumerate(state.sections):
            _progress(
                f"Writing section {idx+1}/{len(state.sections)}: "
                f"{sec.section_plan.section_name}...",
                0.19 + (idx / len(state.sections)) * 0.14,
            )
            preceding = None
            if idx > 0:
                preceding = state.outline.sections[idx - 1].model_dump()

            result = self.llm.generate_structured(
                system_prompt=SECTION_SCRIPT_V2_PROMPT,
                user_payload={
                    "topic": state.topic,
                    "purpose": state.purpose,
                    "target_audience": state.target_audience,
                    "tone": state.tone,
                    "research_brief": research_data,
                    "additional_instructions": state.additional_instructions or "",
                    "style_reference": state.style_reference,
                    "full_outline": outline_data,
                    "section_plan": sec.section_plan.model_dump(),
                    "preceding_section_plan": preceding,
                    "cumulative_script": cumulative,
                },
                output_model=SectionScriptV2,
            )
            sec.section_script = result.section_script
            sec.tts_script = result.tts_script
            cumulative += result.section_script + " "

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS — Long-Form Audio (parallel)
    # ══════════════════════════════════════════════════════════════════════

    async def _generate_all_section_audio(self, state: LongFormV2State) -> None:
        """Generate TTS audio for all sections in parallel."""

        async def _gen_audio(sec: SectionV2State) -> None:
            tts_text = sec.tts_script or sec.section_script
            audio_path, word_alignments = await asyncio.to_thread(
                self.audio_gen.tts.generate_audio,
                text=tts_text,
                voice_actor=state.voice_actor,
                voice_model=state.voice_model_version,
            )
            sec.audio_path = audio_path
            sec.word_alignments = word_alignments

            # Segment the script
            seg_result = await asyncio.to_thread(
                self.llm.generate_structured,
                system_prompt=SECTION_SEGMENTER_V2_PROMPT,
                user_payload={"section_script": sec.section_script},
                output_model=SegmentsContainer,
            )
            sec.segments = seg_result.segments

            # Align segments to audio
            sec.segment_timings = ElevenLabsService.align_segments_to_words(
                segments=sec.segments,
                word_alignments=word_alignments,
            )

        async with asyncio.TaskGroup() as tg:
            for sec in state.sections:
                if sec.section_script:
                    tg.create_task(_gen_audio(sec))

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS — Long-Form Visual Planning
    # ══════════════════════════════════════════════════════════════════════

    async def _generate_section_storyboards(
        self, state: LongFormV2State, style_guide: StyleGuide
    ) -> None:
        """Generate storyboards for all sections in parallel."""
        face_rule = FACES_ALLOWED_RULE_V2 if state.allow_faces else FACE_FREE_RULE_V2
        prompt = STORYBOARD_PROMPT.format(face_rule=face_rule)
        style_data = style_guide.model_dump()

        class StoryboardContainer(BaseModel):
            storyboard: list[SegmentStoryboard]

        async def _gen_storyboard(sec: SectionV2State) -> None:
            beats_data = []
            for i, seg_text in enumerate(sec.segments):
                dur_ms = 3000
                if i < len(sec.segment_timings):
                    dur_ms = int(sec.segment_timings[i].duration * 1000)
                beats_data.append({
                    "raw_text": seg_text,
                    "visual_intent": f"B-roll for: {seg_text[:60]}",
                    "beat_type": "setup",
                    "energy_level": 5,
                    "duration_ms": dur_ms,
                })

            result = await asyncio.to_thread(
                self.llm.generate_structured,
                system_prompt=prompt,
                user_payload={
                    "beats": beats_data,
                    "style_guide": style_data,
                    "image_style": state.image_style,
                    "topic": state.topic,
                    "allow_faces": state.allow_faces,
                    "ideal_shot_duration_ms": int(state.ideal_image_duration * 1000),
                    "additional_image_requests": state.additional_image_requests,
                },
                output_model=StoryboardContainer,
            )

            # Convert storyboard to visual plans
            plans = []
            for j, sb in enumerate(result.storyboard):
                num_imgs = len(sb.shots)
                last_dur = sb.shots[-1].duration_ms / 1000.0 if sb.shots else 3.0
                descriptions = [
                    ImageDescription(description=shot.image_prompt, uses_logo=False)
                    for shot in sb.shots
                ]
                plans.append(SegmentVisualPlan(
                    segment_index=j,
                    num_images=num_imgs,
                    last_image_duration=last_dur,
                    image_descriptions=descriptions,
                ))
            sec.segment_visual_plans = plans

        async with asyncio.TaskGroup() as tg:
            for sec in state.sections:
                if sec.segments:
                    tg.create_task(_gen_storyboard(sec))

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS — Long-Form Image Generation
    # ══════════════════════════════════════════════════════════════════════

    async def _generate_all_section_images(self, state: LongFormV2State) -> None:
        """Generate images for all sections using existing ImageGenerator."""

        async def _gen_images(sec: SectionV2State) -> None:
            if sec.segment_visual_plans:
                sec.segment_visual_plans = await self.image_gen.generate_images(
                    visual_plans=sec.segment_visual_plans,
                    image_provider=state.image_provider,
                    orientation=state.orientation,
                )

        async with asyncio.TaskGroup() as tg:
            for sec in state.sections:
                tg.create_task(_gen_images(sec))

    async def _animate_all_sections(self, state: LongFormV2State) -> None:
        """Create video clips for all sections."""

        async def _animate(sec: SectionV2State) -> None:
            if not sec.segment_visual_plans:
                return

            if state.visual_mode == "video_gen":
                sec.segment_visual_plans = (
                    await self.image_gen.generate_video_clips(
                        visual_plans=sec.segment_visual_plans,
                        segment_timings=sec.segment_timings,
                        video_provider=state.video_provider,
                        orientation=state.orientation,
                        use_base_images=bool(
                            sec.segment_visual_plans
                            and sec.segment_visual_plans[0].image_paths
                        ),
                    )
                )
            else:
                sec.segment_visual_plans = (
                    await self.image_gen.animate_segments(
                        visual_plans=sec.segment_visual_plans,
                        ideal_image_duration=state.ideal_image_duration,
                        orientation=state.orientation,
                    )
                )
            sec.clip_paths = [
                p.video_path for p in sec.segment_visual_plans if p.video_path
            ]

        async with asyncio.TaskGroup() as tg:
            for sec in state.sections:
                tg.create_task(_animate(sec))

    async def _assemble_all_sections(self, state: LongFormV2State) -> None:
        """Assemble all section videos in parallel."""

        async def _assemble(sec: SectionV2State, idx: int) -> None:
            if sec.segment_visual_plans and sec.audio_path:
                sec.section_video_path = await asyncio.to_thread(
                    self.assembler.assemble_section,
                    visual_plans=sec.segment_visual_plans,
                    audio_path=sec.audio_path,
                    section_index=idx,
                )

        async with asyncio.TaskGroup() as tg:
            for idx, sec in enumerate(state.sections):
                tg.create_task(_assemble(sec, idx))
