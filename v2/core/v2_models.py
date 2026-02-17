"""
Pydantic models for MoceanAI V2 enhanced pipelines.

This module defines all data structures for the improved short-form and
long-form pipelines. Kept separate from core/models.py to avoid
bloating the original file or breaking existing imports.

Model groups:
  1. Research models       -- Output of the Tavily research + LLM synthesis phase
  2. Script models         -- Single-pass script generation replacing the 5-step chain
  3. Quality gate models   -- LLM-as-judge evaluation outputs
  4. Visual planning       -- Style guide, storyboard, shot plans, visual QA
  5. Long-form specific    -- Enhanced outline with retention, energy, section types
  6. Pipeline state models -- Full state accumulators for short-form and long-form V2
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from v2.core.models import (
    WordAlignment,
    SegmentTiming,
    SegmentVisualPlan,
)


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class BeatType(str, Enum):
    """Narrative function of a script beat."""
    hook = "hook"
    setup = "setup"
    tension = "tension"
    evidence = "evidence"
    story = "story"
    payoff = "payoff"
    callback = "callback"
    cta = "cta"
    transition = "transition"


class SectionType(str, Enum):
    """Structural role of a long-form section."""
    hook = "hook"
    context = "context"
    argument = "argument"
    evidence = "evidence"
    counterargument = "counterargument"
    story = "story"
    demonstration = "demonstration"
    synthesis = "synthesis"
    callback = "callback"
    cta = "cta"


class EnergyTarget(str, Enum):
    """Pacing energy for a section or beat."""
    calm = "calm"
    building = "building"
    peak = "peak"
    resolving = "resolving"


class MotionType(str, Enum):
    """Camera motion type for a visual shot."""
    zoom_in = "zoom_in"
    zoom_out = "zoom_out"
    pan_left = "pan_left"
    pan_right = "pan_right"
    pan_up = "pan_up"
    pan_down = "pan_down"
    static = "static"
    ken_burns = "ken_burns"
    dolly_in = "dolly_in"


class MotionSpeed(str, Enum):
    """Speed of camera motion."""
    slow = "slow"
    medium = "medium"
    fast = "fast"


class TransitionType(str, Enum):
    """Visual transition between shots."""
    cut = "cut"
    dissolve = "dissolve"
    wipe = "wipe"
    dip_black = "dip_black"
    none = "none"


# ═══════════════════════════════════════════════════════════════════════════
# RESEARCH MODELS
# ═══════════════════════════════════════════════════════════════════════════

class ResearchQueriesContainer(BaseModel):
    """LLM output: search queries derived from a topic."""
    queries: list[str] = Field(..., description="3-5 search queries to research the topic.")


class ResearchBrief(BaseModel):
    """Synthesized research output from web search + LLM distillation."""
    key_facts: list[str] = Field(default_factory=list, description="Verified, citable facts.")
    statistics: list[str] = Field(default_factory=list, description="Numbers that tell a story.")
    expert_perspectives: list[str] = Field(default_factory=list, description="Notable quotes or positions.")
    counterarguments: list[str] = Field(default_factory=list, description="Opposing views to address.")
    knowledge_gaps: list[str] = Field(default_factory=list, description="What we don't know.")
    angle_recommendation: str = Field("", description="Unique perspective suggestion.")


class TrendContext(BaseModel):
    """Trend analysis output for content gap identification."""
    working_hooks: list[str] = Field(default_factory=list, description="Hook patterns performing well.")
    saturated_angles: list[str] = Field(default_factory=list, description="Angles that are overdone.")
    content_gaps: list[str] = Field(default_factory=list, description="Underserved angles with opportunity.")


# ═══════════════════════════════════════════════════════════════════════════
# SCRIPT MODELS (SINGLE-PASS)
# ═══════════════════════════════════════════════════════════════════════════

class ScriptBeat(BaseModel):
    """One narrative beat of a script with both text tracks and visual intent."""
    raw_text: str = Field(..., description="Clean narration text (no TTS tags).")
    tts_text: str = Field(..., description="Text with ElevenLabs audio tags for TTS.")
    visual_intent: str = Field(..., description="What the viewer should SEE during this beat.")
    beat_type: str = Field("setup", description="Narrative function: hook, setup, tension, evidence, story, payoff, callback, cta, transition.")
    energy_level: int = Field(5, ge=1, le=10, description="Pacing energy 1-10.")


class FullScript(BaseModel):
    """Single-pass script generation output containing everything."""
    goal: str = Field(..., description="Strategic CTA goal for the video.")
    hook: str = Field(..., description="Opening hook (first 3 seconds).")
    beats: list[ScriptBeat] = Field(..., description="Script split into narrative beats.")
    cta: str = Field(..., description="Closing call-to-action.")


# ═══════════════════════════════════════════════════════════════════════════
# QUALITY GATE MODELS
# ═══════════════════════════════════════════════════════════════════════════

class QualityReport(BaseModel):
    """LLM-as-judge evaluation of a script."""
    hook_score: int = Field(..., ge=1, le=10, description="Does the hook stop the scroll?")
    clarity_score: int = Field(..., ge=1, le=10, description="Easy to follow?")
    engagement_score: int = Field(..., ge=1, le=10, description="Holds attention throughout?")
    cta_score: int = Field(..., ge=1, le=10, description="Motivates action?")
    pacing_score: int = Field(..., ge=1, le=10, description="Right speed for format?")
    factual_flags: list[str] = Field(default_factory=list, description="Claims that seem unverified.")
    revision_notes: list[str] = Field(default_factory=list, description="Specific improvement suggestions.")
    passed: bool = Field(..., description="True if all scores >= 7.")


class OutlineReview(BaseModel):
    """LLM-as-judge evaluation of a long-form outline."""
    structure_score: int = Field(..., ge=1, le=10, description="Logical flow?")
    variety_score: int = Field(..., ge=1, le=10, description="Section types diverse enough?")
    retention_score: int = Field(..., ge=1, le=10, description="Re-hooks well-placed?")
    depth_score: int = Field(..., ge=1, le=10, description="Substance over fluff?")
    pacing_score: int = Field(..., ge=1, le=10, description="Duration allocation makes sense?")
    revision_notes: list[str] = Field(default_factory=list, description="Specific suggestions.")
    passed: bool = Field(..., description="True if all scores >= 7.")


# ═══════════════════════════════════════════════════════════════════════════
# VISUAL PLANNING MODELS
# ═══════════════════════════════════════════════════════════════════════════

class StyleGuide(BaseModel):
    """Global visual style guide governing all image generation."""
    color_palette: list[str] = Field(..., description="Primary, secondary, accent colors.")
    lighting_direction: str = Field(..., description="Warm, cool, dramatic, natural, etc.")
    composition_rules: list[str] = Field(..., description="Rule of thirds, centered, etc.")
    texture_notes: str = Field("", description="Matte, glossy, grainy, clean, etc.")
    banned_elements: list[str] = Field(default_factory=list, description="Things to avoid.")
    style_keywords: list[str] = Field(..., description="Keywords appended to every prompt.")


class ShotPlan(BaseModel):
    """Plan for one visual shot within a segment."""
    image_prompt: str = Field(..., description="Detailed image generation prompt.")
    duration_ms: int = Field(3000, description="How long this shot holds in milliseconds.")
    motion_type: str = Field("zoom_in", description="Camera motion type.")
    motion_speed: str = Field("medium", description="Slow, medium, or fast.")
    transition_in: str = Field("cut", description="Transition from previous shot.")


class SegmentStoryboard(BaseModel):
    """Visual storyboard for one script segment."""
    shots: list[ShotPlan] = Field(..., description="Ordered list of shots for this segment.")
    segment_energy: int = Field(5, ge=1, le=10, description="Energy level driving motion speed.")


class VisualQualityAssessment(BaseModel):
    """Vision model assessment of a generated image."""
    relevance: int = Field(..., ge=1, le=10, description="Does it match the prompt?")
    quality: int = Field(..., ge=1, le=10, description="Artifacts, blur, distortion?")
    style_match: int = Field(..., ge=1, le=10, description="Consistent with style guide?")
    reject: bool = Field(..., description="True if any score < 6.")
    rejection_reason: str = Field("", description="Why rejected, for retry prompt.")


class VisualQualityBatchAssessment(BaseModel):
    """Container for batch visual QA results."""
    assessments: list[VisualQualityAssessment]


# ═══════════════════════════════════════════════════════════════════════════
# LONG-FORM SPECIFIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class SectionPlanV2(BaseModel):
    """Enhanced section blueprint with retention and energy planning."""
    section_name: str = Field(..., description="Descriptive title for the section.")
    section_purpose: str = Field(..., description="Strategic function of this section.")
    section_directives: list[str] = Field(default_factory=list, description="Meta-instructions for execution.")
    section_talking_points: list[str] = Field(default_factory=list, description="Content elements to cover.")
    section_type: str = Field("context", description="Structural role: hook, context, argument, evidence, counterargument, story, demonstration, synthesis, callback, cta.")
    energy_target: str = Field("building", description="Pacing energy: calm, building, peak, resolving.")
    retention_device: str = Field("", description="What keeps viewers watching into next section.")
    transition_from_previous: str = Field("", description="How to bridge from previous section.")
    target_duration_seconds: int = Field(120, description="Target duration for this section.")
    facts_to_use: list[str] = Field(default_factory=list, description="References into research brief.")


class VideoOutlineV2(BaseModel):
    """LLM output: enhanced long-form video outline."""
    thesis: str = Field(..., description="One-sentence core argument or promise.")
    sections: list[SectionPlanV2] = Field(..., description="Ordered list of sections.")
    retention_map: list[str] = Field(default_factory=list, description="Planned re-hook points.")
    emotional_arc: str = Field("", description="Overall emotional journey description.")


class SectionScriptV2(BaseModel):
    """LLM output: section script with beat-level metadata."""
    section_script: str = Field(..., description="Full narration for this section.")
    tts_script: str = Field(..., description="TTS-enhanced version with audio tags.")


class ConnectorPassContainer(BaseModel):
    """LLM output: smoothed transition sentences for parallel-written sections."""
    smoothed_sections: list[str] = Field(..., description="Rewritten scripts with smooth transitions.")


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE STATE — SHORT-FORM V2
# ═══════════════════════════════════════════════════════════════════════════

class ShortFormV2State(BaseModel):
    """Tracks all data through the short-form V2 pipeline."""

    # --- User inputs ---
    topic: str
    purpose: str
    target_audience: str
    tone: str
    platform: str
    duration_seconds: int
    orientation: str = "Portrait"
    model_provider: str = "google"
    image_provider: str = "google"
    image_style: str = "Isometric Illustrations"
    voice_actor: str = "american_female_conversationalist"
    voice_model_version: str = "eleven_v3"
    additional_instructions: Optional[str] = None
    additional_image_requests: Optional[str] = None
    style_reference: str = ""
    visual_mode: str = "zoompan"
    video_provider: str = "runway"
    allow_faces: bool = False
    add_subtitles: bool = False
    add_end_buffer: bool = True

    # V2-specific user inputs
    enable_research: bool = True
    reference_urls: Optional[str] = None
    brand_guidelines: Optional[str] = None

    # --- Research phase ---
    research_brief: Optional[ResearchBrief] = None
    trend_context: Optional[TrendContext] = None

    # --- Script phase ---
    full_script: Optional[FullScript] = None
    quality_report: Optional[QualityReport] = None
    script_revision_count: int = 0

    # --- Audio phase ---
    audio_path: Optional[Path] = None
    word_alignments: list[WordAlignment] = Field(default_factory=list)
    segment_timings: list[SegmentTiming] = Field(default_factory=list)

    # --- Visual planning phase ---
    style_guide: Optional[StyleGuide] = None
    storyboard: list[SegmentStoryboard] = Field(default_factory=list)

    # --- Image generation phase ---
    segment_visual_plans: list[SegmentVisualPlan] = Field(default_factory=list)
    visual_qa_results: list[VisualQualityAssessment] = Field(default_factory=list)

    # --- Final output ---
    clip_paths: list[Path] = Field(default_factory=list)
    final_video_path: Optional[Path] = None

    # --- Tuning ---
    ideal_image_duration: float = 3.0
    min_image_duration: float = 2.0
    single_image_per_segment: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# LONG-FORM V2 SECTION STATE
# ═══════════════════════════════════════════════════════════════════════════

class SectionV2State(BaseModel):
    """Tracks all data for one section in the long-form V2 pipeline."""
    section_plan: SectionPlanV2
    section_script: Optional[str] = None
    tts_script: Optional[str] = None
    audio_path: Optional[Path] = None
    word_alignments: list[WordAlignment] = Field(default_factory=list)
    segments: list[str] = Field(default_factory=list)
    segment_timings: list[SegmentTiming] = Field(default_factory=list)
    storyboard: Optional[SegmentStoryboard] = None
    segment_visual_plans: list[SegmentVisualPlan] = Field(default_factory=list)
    clip_paths: list[Path] = Field(default_factory=list)
    section_video_path: Optional[Path] = None
    quality_report: Optional[QualityReport] = None


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE STATE — LONG-FORM V2
# ═══════════════════════════════════════════════════════════════════════════

class LongFormV2State(BaseModel):
    """Tracks all data through the long-form V2 pipeline."""

    # --- User inputs ---
    topic: str
    purpose: str
    target_audience: str
    tone: str
    platform: str = "YouTube"
    duration_seconds: int = 600
    orientation: str = "Landscape"
    model_provider: str = "google"
    image_provider: str = "google"
    image_style: str = "Cinematic"
    voice_actor: str = "american_female_conversationalist"
    voice_model_version: str = "eleven_v3"
    additional_instructions: Optional[str] = None
    additional_image_requests: Optional[str] = None
    style_reference: str = ""
    visual_mode: str = "zoompan"
    video_provider: str = "runway"
    allow_faces: bool = False
    add_subtitles: bool = False

    # V2-specific user inputs
    enable_research: bool = True
    reference_urls: Optional[str] = None
    brand_guidelines: Optional[str] = None
    script_strategy: str = "parallel"  # "parallel" or "sequential"

    # --- Research phase ---
    research_brief: Optional[ResearchBrief] = None
    trend_context: Optional[TrendContext] = None

    # --- Outline phase ---
    outline: Optional[VideoOutlineV2] = None
    outline_review: Optional[OutlineReview] = None
    outline_revision_count: int = 0

    # --- Section processing ---
    sections: list[SectionV2State] = Field(default_factory=list)
    full_script: Optional[str] = None

    # --- Final output ---
    final_video_path: Optional[Path] = None

    # --- Tuning ---
    ideal_image_duration: float = 3.0
    min_image_duration: float = 2.0
    single_image_per_segment: bool = False
