"""
Pydantic models for the UGC (User-Generated Content) product video pipeline.

This pipeline generates realistic product review videos from:
  - Product images (multiple angles)
  - Product description (as it appears on Amazon/TikTok)
  - Optional reference videos for style inspiration
  - Optional script guidance

Models defined here:

  1. **ReferenceVideoAnalysis** -- Structured data extracted from a reference
     video by Gemini multimodal (hook style, pacing, tone, shot types, etc.)

  2. **UGCSceneDescription** -- One scene/shot in the video, with both an
     image_prompt (for image generation) and a video_prompt (for video gen)

  3. **UGCConfig** -- All user-provided inputs for the pipeline

  4. **UGCState** -- Full pipeline state that accumulates data step-by-step.
     On failure, all previously completed fields are preserved in PipelineError.

  5. **LLM output containers** -- Pydantic models for structured LLM responses

To extend:
  - Add new user inputs to UGCConfig, then read them in ugc_pipeline.py
  - Add new scene types by extending UGCSceneDescription.scene_type options
  - Add new reference video analysis fields to ReferenceVideoAnalysis
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

# Reuse existing models from the video pipeline for audio/segment data
from v2.core.models import ScriptSegment, WordAlignment, SegmentTiming, SegmentVisualPlan


# ═══════════════════════════════════════════════════════════════════════════
# REFERENCE VIDEO ANALYSIS (extracted by Gemini multimodal)
# ═══════════════════════════════════════════════════════════════════════════

class ReferenceVideoAnalysis(BaseModel):
    """
    Structured data extracted from a reference/inspiration video.

    Gemini multimodal analyzes the uploaded video and fills these fields
    so the script writer can mirror what's working in existing viral content.
    """
    hook_style: str = Field(
        ...,
        description="How the video opens (e.g., 'direct address to camera', 'product reveal', 'before/after').",
    )
    pacing: str = Field(
        ...,
        description="Overall pacing: fast/medium/slow, approximate cut frequency.",
    )
    tone: str = Field(
        ...,
        description="Emotional tone: casual, enthusiastic, skeptical, humorous, etc.",
    )
    cta_style: str = Field(
        ...,
        description="How the call-to-action is delivered (e.g., 'link in bio mention', 'discount code', 'soft recommendation').",
    )
    shot_types: list[str] = Field(
        ...,
        description="Types of shots used: close-up, overhead, POV, unboxing, in-use, comparison, etc.",
    )
    structure_summary: str = Field(
        ...,
        description="Overall flow/structure of the video in 2-3 sentences.",
    )
    key_phrases: list[str] = Field(
        default_factory=list,
        description="Notable phrases, hooks, or recurring language patterns used in the video.",
    )
    estimated_duration_seconds: int = Field(
        30,
        description="Approximate duration of the reference video in seconds.",
    )


class ReferenceVideoAnalysisContainer(BaseModel):
    """LLM output wrapper for reference video analysis."""
    analysis: ReferenceVideoAnalysis


# ═══════════════════════════════════════════════════════════════════════════
# SCENE DESCRIPTIONS
# ═══════════════════════════════════════════════════════════════════════════

class UGCSceneDescription(BaseModel):
    """
    One scene/shot in the UGC video.

    Each scene has two prompt variants:
      - image_prompt: Detailed description for generating a still image of the
        product in an environment. References the product's visual appearance.
      - video_prompt: Motion-focused description for video generation APIs.
        Kept simple if the simple_scenes toggle is on.
    """
    scene_index: int = Field(..., description="0-indexed position in the scene sequence.")
    scene_type: str = Field(
        ...,
        description=(
            "Type of shot: 'product_closeup', 'in_use', 'environment', "
            "'unboxing', 'comparison', 'detail', 'lifestyle'."
        ),
    )
    image_prompt: str = Field(
        ...,
        description="Detailed photorealistic image generation prompt referencing the product's appearance.",
    )
    video_prompt: str = Field(
        ...,
        description="Motion/camera description for video generation (e.g., 'slow push-in', 'hand picks up product').",
    )
    duration_seconds: float = Field(
        3.0,
        description="Target duration of this scene in seconds.",
    )


class UGCScenePlanContainer(BaseModel):
    """LLM output wrapper for the full scene plan."""
    scenes: list[UGCSceneDescription]


class ProductVisualDescriptionContainer(BaseModel):
    """LLM output: detailed visual description of the product from uploaded images."""
    product_visual_description: str = Field(
        ...,
        description=(
            "Exhaustive visual description of the product: shape, dimensions, colors, "
            "materials, textures, branding, logos, buttons, labels, and any distinguishing "
            "features visible from the uploaded images."
        ),
    )


class UGCScriptContainer(BaseModel):
    """LLM output: the UGC reviewer script."""
    script: str = Field(
        ...,
        description="Natural-sounding product review script written as spoken narration.",
    )


# ═══════════════════════════════════════════════════════════════════════════
# USER CONFIG
# ═══════════════════════════════════════════════════════════════════════════

class UGCConfig(BaseModel):
    """
    All user-provided settings for UGC video generation.

    Populated from the Streamlit UI form before the pipeline starts.
    """
    # --- Product info ---
    product_name: str = Field(..., description="Name of the product being reviewed.")
    product_description: str = Field(
        ...,
        description="Product listing description (as it appears on Amazon/TikTok/website).",
    )
    product_image_paths: list[Path] = Field(
        default_factory=list,
        description="Paths to uploaded product photos (multiple angles).",
    )

    # --- Optional reference content ---
    reference_video_paths: list[Path] = Field(
        default_factory=list,
        description="Paths to uploaded reference/inspiration videos (max 3).",
    )
    script_guidance: str = Field(
        "",
        description="Optional user direction for what the script should cover or emphasize.",
    )

    # --- Video settings ---
    voice_actor: str = Field("american_female_media_influencer", description="Voice for the review narration.")
    tone: str = Field("Conversational", description="Tone of the review.")
    platform: str = Field("TikTok", description="Target platform.")
    duration_seconds: int = Field(30, ge=15, le=120, description="Target video duration in seconds.")
    orientation: str = Field("Portrait", description="Portrait or Landscape.")

    # --- Model settings ---
    model_provider: str = Field("google", description="LLM provider for script/scene generation.")
    image_provider: str = Field("google", description="Image generation provider.")
    video_provider: str = Field("runway", description="Video generation provider (when visual_mode is video_gen).")
    visual_mode: str = Field("zoompan", description="'zoompan' or 'video_gen'.")

    # --- Toggles ---
    allow_faces: bool = Field(False, description="Whether generated images may include visible human faces.")
    simple_scenes: bool = Field(
        True,
        description=(
            "When True, scene descriptions are constrained to static or minimal-movement "
            "shots to avoid artifacts from video generation models."
        ),
    )
    enhance_for_tts: bool = Field(True, description="Whether to add ElevenLabs audio tags to the script.")


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE STATE
# ═══════════════════════════════════════════════════════════════════════════

class UGCState(BaseModel):
    """
    Full pipeline state for UGC video generation.

    Populated incrementally as each pipeline step completes.
    If the pipeline fails, all previously completed fields are preserved
    and attached to PipelineError for the UI to display.
    """
    # --- Configuration (set before pipeline starts) ---
    config: UGCConfig

    # --- Step 0: Reference video analysis (optional) ---
    reference_analyses: list[ReferenceVideoAnalysis] = Field(default_factory=list)

    # --- Step 1: Product visual description ---
    product_visual_description: Optional[str] = None

    # --- Step 2: Script ---
    script: Optional[str] = None

    # --- Step 3: Enhanced script ---
    enhanced_script: Optional[str] = None

    # --- Step 4: Script segments ---
    segments: list[ScriptSegment] = Field(default_factory=list)

    # --- Step 5: Audio + timing ---
    audio_path: Optional[Path] = None
    word_alignments: list[WordAlignment] = Field(default_factory=list)
    segment_timings: list[SegmentTiming] = Field(default_factory=list)

    # --- Step 6: Scene descriptions ---
    scene_descriptions: list[UGCSceneDescription] = Field(default_factory=list)

    # --- Step 7: Generated scene images ---
    scene_image_paths: list[Path] = Field(default_factory=list)

    # --- Step 8: Video clips ---
    segment_visual_plans: list[SegmentVisualPlan] = Field(default_factory=list)
    clip_paths: list[Path] = Field(default_factory=list)

    # --- Step 9: Final output ---
    final_video_path: Optional[Path] = None
