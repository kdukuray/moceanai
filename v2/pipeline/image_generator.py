"""
Image generation pipeline: description generation, image creation, and animation.

This module handles the visual side of video production. It supports two modes:

  1. **zoompan** (default) — Generate static images from AI image providers,
     then apply FFmpeg zoompan camera motion effects to turn them into video
     clips. This is the cheaper, faster approach. Uses the proven v1 technique
     of loop=1 input, 2x overscale, d=1 zoompan, and tmix temporal smoothing.

  2. **video_gen** — Use AI video generation APIs (Runway, Luma, Kling) to
     produce actual video clips directly from text prompts. More expensive
     but produces far more engaging and natural-looking B-roll. Can optionally
     take a base image and animate it (image-to-video).

The mode is controlled by the `visual_mode` field on the pipeline state.

Architecture:
  ImageGenerator orchestrates three sub-services:
    - ScriptGenerator (for LLM-based image description generation)
    - ImageService    (for static image generation: Google, OpenAI, Flux)
    - VideoGenerationService (for AI video generation: Runway, Luma, Kling)
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable, Optional

import ffmpeg

from v2.core.config import (
    FPS,
    PORTRAIT_SIZE,
    LANDSCAPE_SIZE,
    PORTRAIT_OVERSCALE,
    LANDSCAPE_OVERSCALE,
    DEFAULT_MOTION_PATTERN,
    VIDEO_DIR,
)
from v2.core.models import (
    ImageDescription,
    SegmentTiming,
    SegmentVisualPlan,
)
from v2.pipeline.audio_generator import compute_images_per_segment
from v2.pipeline.script_generator import ScriptGenerator
from v2.services.image_service import ImageService
from v2.services.video_service import VideoGenerationService

logger = logging.getLogger(__name__)

# Number of worker processes for CPU-bound FFmpeg animation jobs
NUM_WORKERS = os.cpu_count() or 4

ProgressCallback = Optional[Callable[[str], None]]


class ImageGenerator:
    """
    Orchestrates the visual generation pipeline for all segments.

    Responsibilities:
      - Plan how many images each segment needs (based on duration)
      - Generate image descriptions via LLM
      - Generate images via provider APIs
      - Create video clips from images (zoompan) OR from prompts (video API)
    """

    def __init__(self, script_gen: ScriptGenerator):
        self.script_gen = script_gen
        self.image_service = ImageService()
        self.video_service = VideoGenerationService()

    # ------------------------------------------------------------------
    # Step 1: Plan how many images each segment needs
    # ------------------------------------------------------------------

    def plan_visuals(
        self,
        segment_timings: list[SegmentTiming],
        ideal_duration: float = 3.0,
        min_duration: float = 2.0,
        single_image_per_segment: bool = False,
    ) -> list[SegmentVisualPlan]:
        """
        For each segment, compute how many images are needed and the
        duration of the last image in the segment.

        When using video_gen mode, each segment still gets a plan
        (typically 1 clip per segment since the AI generates a full clip),
        but the duration information is used to set the video length.

        Args:
            segment_timings: Timing data for each script segment.
            ideal_duration:  Target duration per image in seconds.
            min_duration:    Minimum acceptable duration for a standalone image.
            single_image_per_segment: If True, use exactly one image per segment
                for its full duration instead of splitting into multiple images.

        Returns:
            List of SegmentVisualPlan objects, one per segment.
        """
        plans = []
        for i, timing in enumerate(segment_timings):
            if single_image_per_segment:
                num_images = 1
                last_dur = timing.duration
            else:
                num_images, last_dur = compute_images_per_segment(
                    timing.duration, ideal_duration, min_duration
                )
            plans.append(SegmentVisualPlan(
                segment_index=i,
                num_images=num_images,
                last_image_duration=last_dur,
            ))
        return plans

    # ------------------------------------------------------------------
    # Step 2: Generate image descriptions via LLM (parallel)
    # ------------------------------------------------------------------

    async def generate_descriptions(
        self,
        segments: list,
        visual_plans: list[SegmentVisualPlan],
        full_script: str,
        image_style: str,
        topic: str,
        tone: str,
        additional_image_requests: str | None = None,
        allow_faces: bool = False,
        on_progress: ProgressCallback = None,
    ) -> list[SegmentVisualPlan]:
        """
        Generate image descriptions for all segments using parallel LLM calls.

        Each segment gets its own TaskGroup task that calls the LLM to produce
        detailed image prompts. The descriptions are stored in each plan's
        `image_descriptions` list.

        These descriptions are used both for static image generation (zoompan)
        and as text prompts for video generation APIs.

        Args:
            segments:       Script segment objects (have .script_segment attr).
            visual_plans:   Plans from plan_visuals().
            full_script:    Complete script text for context.
            image_style:    Style directive (e.g., "Cinematic").
            topic:          Video topic for context.
            tone:           Video tone for context.
            additional_image_requests: Extra visual guidance from the user.
            allow_faces:    If True, generated images may include visible faces.

        Returns:
            Updated visual_plans with image_descriptions populated.
        """
        if on_progress:
            on_progress(f"Generating image descriptions for {len(segments)} segments...")

        tasks = []
        async with asyncio.TaskGroup() as tg:
            for i, plan in enumerate(visual_plans):
                # Extract raw script text from the segment (supports multiple formats)
                seg = segments[i]
                if hasattr(seg, "script_segment"):
                    seg_text = seg.script_segment
                elif isinstance(seg, dict):
                    seg_text = seg.get("script_segment", str(seg))
                else:
                    seg_text = str(seg)

                task = tg.create_task(
                    asyncio.to_thread(
                        self.script_gen.generate_segment_image_descriptions,
                        script_segment=seg_text,
                        full_script=full_script,
                        num_images=plan.num_images,
                        image_style=image_style,
                        topic=topic,
                        tone=tone,
                        additional_image_requests=additional_image_requests,
                        allow_faces=allow_faces,
                    )
                )
                tasks.append((i, task))

        # Collect results back into visual plans
        for i, task in tasks:
            visual_plans[i].image_descriptions = task.result()

        logger.info(f"Generated descriptions for {len(visual_plans)} segments")
        return visual_plans

    # ------------------------------------------------------------------
    # Step 3: Generate static images (for zoompan mode)
    # ------------------------------------------------------------------

    async def generate_images(
        self,
        visual_plans: list[SegmentVisualPlan],
        image_provider: str = "google",
        orientation: str = "portrait",
        on_progress: ProgressCallback = None,
    ) -> list[SegmentVisualPlan]:
        """
        Generate static images for all segments using parallel API calls.

        This step is used in zoompan mode. Each image description is sent
        to the image provider (Google Imagen, OpenAI, or Flux) and the
        resulting image is saved to disk.

        Args:
            visual_plans:   Plans with image_descriptions already populated.
            image_provider: "google", "openai", or "flux".
            orientation:    "portrait" or "landscape".

        Returns:
            Updated visual_plans with image_paths populated.
        """
        total_images = sum(p.num_images for p in visual_plans)
        if on_progress:
            on_progress(f"Generating {total_images} images across {len(visual_plans)} segments...")

        tasks = []
        async with asyncio.TaskGroup() as tg:
            for plan in visual_plans:
                descs = [d.description for d in plan.image_descriptions]
                task = tg.create_task(
                    self.image_service.generate_images(
                        descriptions=descs,
                        provider=image_provider,
                        orientation=orientation.lower(),
                    )
                )
                tasks.append((plan, task))

        for plan, task in tasks:
            plan.image_paths = task.result()

        logger.info(f"Generated {total_images} images")
        return visual_plans

    # ------------------------------------------------------------------
    # Step 4a: Animate images with zoompan (default mode)
    # ------------------------------------------------------------------

    async def animate_segments(
        self,
        visual_plans: list[SegmentVisualPlan],
        ideal_image_duration: float = 3.0,
        orientation: str = "portrait",
        motion_pattern: list[str] | None = None,
        on_progress: ProgressCallback = None,
    ) -> list[SegmentVisualPlan]:
        """
        Animate each segment's static images into a video clip using
        FFmpeg zoompan motion effects.

        Each segment's images are concatenated into a single clip with
        alternating motion patterns (zoom_in, zoom_out, etc.). Uses
        ProcessPoolExecutor because FFmpeg is CPU-bound.

        Args:
            visual_plans:         Plans with image_paths populated.
            ideal_image_duration: How long each image should display (seconds).
            orientation:          "portrait" or "landscape".
            motion_pattern:       List of motion effect names to cycle through.

        Returns:
            Updated visual_plans with video_path populated on each plan.
        """
        if motion_pattern is None:
            motion_pattern = DEFAULT_MOTION_PATTERN

        if on_progress:
            on_progress(f"Animating {len(visual_plans)} segments with zoompan...")

        loop = asyncio.get_running_loop()
        pattern_start = 0
        tasks = []

        with ProcessPoolExecutor(NUM_WORKERS) as executor:
            for plan in visual_plans:
                video_path = VIDEO_DIR / f"{uuid.uuid4().hex}.mp4"
                video_path.parent.mkdir(parents=True, exist_ok=True)
                plan.video_path = video_path

                motion_start_index = pattern_start % len(motion_pattern)

                task = loop.run_in_executor(
                    executor,
                    animate_with_motion_effect,
                    plan.image_paths,
                    video_path,
                    float(ideal_image_duration),
                    plan.last_image_duration,
                    motion_pattern,
                    motion_start_index,
                    orientation.lower(),
                )
                tasks.append(task)
                pattern_start += len(plan.image_paths)

            await asyncio.gather(*tasks)

        logger.info(f"Animated {len(visual_plans)} segment clips (zoompan)")
        return visual_plans

    # ------------------------------------------------------------------
    # Step 4b: Generate video clips via AI video API (video_gen mode)
    # ------------------------------------------------------------------

    async def generate_video_clips(
        self,
        visual_plans: list[SegmentVisualPlan],
        segment_timings: list[SegmentTiming],
        video_provider: str = "runway",
        orientation: str = "portrait",
        use_base_images: bool = True,
        on_progress: ProgressCallback = None,
    ) -> list[SegmentVisualPlan]:
        """
        Generate video clips using an AI video generation API instead of
        applying zoompan to static images.

        For each segment, the first image description is used as the video
        prompt. If base images have already been generated and use_base_images
        is True, the first image is passed as a reference (image-to-video).

        This produces much more engaging B-roll than zoompan, but costs more.

        Args:
            visual_plans:    Plans with image_descriptions (and optionally image_paths).
            segment_timings: Timing data to determine clip duration per segment.
            video_provider:  "runway", "luma", or "kling".
            orientation:     "portrait" or "landscape".
            use_base_images: If True and images exist, use them for image-to-video.

        Returns:
            Updated visual_plans with video_path populated on each plan.
        """
        if on_progress:
            on_progress(f"Generating {len(visual_plans)} video clips via {video_provider}...")

        tasks = []
        async with asyncio.TaskGroup() as tg:
            for i, plan in enumerate(visual_plans):
                # Use the first image description as the video prompt
                if plan.image_descriptions:
                    prompt = plan.image_descriptions[0].description
                else:
                    prompt = f"B-roll footage, {orientation} format"

                # Determine target duration from segment timing
                duration = int(segment_timings[i].duration) if i < len(segment_timings) else 5
                duration = max(3, min(duration, 10))  # Clamp to 3-10s (API limits)

                # Optionally pass a base image for image-to-video
                base_image = None
                if use_base_images and plan.image_paths:
                    base_image = plan.image_paths[0]

                task = tg.create_task(
                    self._generate_single_video_clip(
                        plan=plan,
                        prompt=prompt,
                        provider=video_provider,
                        duration=duration,
                        orientation=orientation,
                        image_path=base_image,
                    )
                )
                tasks.append(task)

        logger.info(f"Generated {len(visual_plans)} video clips via {video_provider}")
        return visual_plans

    async def _generate_single_video_clip(
        self,
        plan: SegmentVisualPlan,
        prompt: str,
        provider: str,
        duration: int,
        orientation: str,
        image_path: Optional[Path] = None,
    ) -> None:
        """Generate a single video clip and assign it to the plan."""
        video_path = await self.video_service.generate_video(
            prompt=prompt,
            provider=provider,
            duration=duration,
            orientation=orientation,
            image_path=image_path,
        )
        plan.video_path = video_path


# ---------------------------------------------------------------------------
# FFmpeg zoompan animation (standalone function for ProcessPoolExecutor)
# ---------------------------------------------------------------------------
# This MUST be a top-level function (not a method) because
# ProcessPoolExecutor uses pickle to send work to subprocesses,
# and bound methods / closures can't be pickled.
# ---------------------------------------------------------------------------

def animate_with_motion_effect(
    image_paths: list[Path],
    video_path: Path,
    ideal_image_duration: float,
    last_image_duration: float,
    motion_pattern: list[str],
    motion_start_index: int = 0,
    orientation: str = "portrait",
) -> None:
    """
    Create a video clip from a sequence of images with zoompan motion effects.

    This is the core animation function that turns static B-roll images into
    smooth video clips. It uses the proven v1 approach:

      - **loop=1 + t=duration**: Creates exactly the right number of input
        frames for the given duration. This prevents the "jitter" problem
        that occurs when ffmpeg has to guess frame count.

      - **2x overscale**: Upscales the input image to 2x the output resolution
        before zoompan. This prevents pixelation when zooming in because there
        are real pixels to zoom into, not interpolated ones.

      - **d=1 in zoompan**: Tells zoompan to produce exactly 1 output frame per
        input frame. Since loop=1 already created the right frame count, this
        ensures the output duration matches exactly.

      - **tmix frames=3**: Temporal smoothing that blends adjacent frames,
        eliminating micro-jitter from the zoompan calculations.

      - **preset=slow**: H.264 encoding with slow preset for better compression
        (reduced v1's 150MB clips to ~11MB with no visible quality loss).

    Motion styles available:
      - zoom_in:         Gradual zoom toward center
      - zoom_out:        Gradual zoom away from center
      - pan_right/left:  Horizontal pan with slight zoom
      - pan_up/down:     Vertical pan with slight zoom
      - rock_horizontal: Sinusoidal horizontal sway
      - rock_vertical:   Sinusoidal vertical sway
      - ken_burns:       Combined zoom + diagonal drift (cinematic feel)

    Args:
        image_paths:          List of image file paths for this segment.
        video_path:           Where to save the output video clip.
        ideal_image_duration: Duration (seconds) for all images except the last.
        last_image_duration:  Duration (seconds) for the final image in the sequence.
        motion_pattern:       Ordered list of motion effect names to cycle through.
        motion_start_index:   Which index in the pattern to start at (for continuity
                              across segments).
        orientation:          "portrait" (1080x1920) or "landscape" (1920x1080).

    Raises:
        RuntimeError: If FFmpeg fails (with stderr details).
    """
    fps = FPS
    output_size = (
        f"{PORTRAIT_SIZE[0]}x{PORTRAIT_SIZE[1]}"
        if orientation == "portrait"
        else f"{LANDSCAPE_SIZE[0]}x{LANDSCAPE_SIZE[1]}"
    )
    overscale = PORTRAIT_OVERSCALE if orientation == "portrait" else LANDSCAPE_OVERSCALE

    # Speed parameters controlling the intensity of each motion effect.
    # These were tuned in v1 through experimentation:
    #   - pan_speed 0.8  = travels ~80% of the available range
    #   - zoom_speed 0.17 = subtle zoom, less jitter than the original 0.20
    #   - rock_speed 15  = pixel amplitude for sinusoidal rocking
    #   - kenburns_speed 60 = pixels/frame diagonal drift rate
    pan_speed = 0.8
    zoom_speed = 0.17
    rock_speed = 15
    kenburns_speed = 60

    pattern_index = motion_start_index
    pattern_length = len(motion_pattern)

    try:
        sub_clips = []
        for index, image_path in enumerate(image_paths):
            # Last image gets a different duration (may be longer to absorb excess)
            duration = (
                ideal_image_duration
                if image_path != image_paths[-1]
                else last_image_duration
            )
            total_frames = int(duration * fps)
            current_pattern = motion_pattern[pattern_index % pattern_length]

            # Build the motion formula strings for FFmpeg's zoompan filter.
            # These are mathematical expressions that FFmpeg evaluates per-frame.
            # 'on' = output frame number (0-indexed), 'iw'/'ih' = input dimensions.
            styles = {
                "pan_right": {
                    "z": "1.1",
                    "x": f"(iw - iw/zoom) * {pan_speed} * (on / {total_frames})",
                    "y": "ih/2 - (ih/zoom/2)",
                },
                "pan_left": {
                    "z": "1.1",
                    "x": f"(iw - iw/zoom) * {pan_speed} * (1 - on / {total_frames})",
                    "y": "ih/2 - (ih/zoom/2)",
                },
                "pan_down": {
                    "z": "1.1",
                    "x": "iw/2 - (iw/zoom/2)",
                    "y": f"(ih - ih/zoom) * {pan_speed} * (on / {total_frames})",
                },
                "pan_up": {
                    "z": "1.1",
                    "x": "iw/2 - (iw/zoom/2)",
                    "y": f"(ih - ih/zoom) * {pan_speed} * (1 - on / {total_frames})",
                },
                "zoom_in": {
                    "z": f"min(1 + on/{total_frames} * {zoom_speed}, 1 + {zoom_speed})",
                    "x": "iw/2 - (iw/zoom/2)",
                    "y": "ih/2 - (ih/zoom/2)",
                },
                "zoom_out": {
                    "z": f"max(1 + {zoom_speed} - on/{total_frames} * {zoom_speed}, 1)",
                    "x": "iw/2 - (iw/zoom/2)",
                    "y": "ih/2 - (ih/zoom/2)",
                },
                "rock_horizontal": {
                    "z": "1.05",
                    "x": f"iw/2-(iw/zoom/2) + sin(on*PI/{fps}*0.5) * {rock_speed}",
                    "y": "ih/2-(ih/zoom/2)",
                },
                "rock_vertical": {
                    "z": "1.05",
                    "x": "iw/2-(iw/zoom/2)",
                    "y": f"ih/2-(ih/zoom/2) + sin(on*PI/{fps}*0.5) * {rock_speed}",
                },
                "ken_burns": {
                    "z": f"1 + on/{total_frames} * {zoom_speed}",
                    "x": f"iw/2-(iw/zoom/2) + on*({kenburns_speed} / {fps})",
                    "y": f"ih/2-(ih/zoom/2) + on*({kenburns_speed} / {fps})",
                },
            }

            style = styles[current_pattern]

            # Build the FFmpeg filter chain for this image:
            # input(loop) -> scale(2x) -> zoompan -> setsar -> tmix
            clip = ffmpeg.input(str(image_path), loop=1, t=duration, framerate=fps)
            clip = clip.filter("scale", overscale[0], overscale[1], flags="lanczos")
            clip = clip.filter(
                "zoompan",
                z=style["z"],
                x=style["x"],
                y=style["y"],
                d=1,          # 1 output frame per input frame (critical for timing)
                fps=fps,
                s=output_size,
            )
            clip = clip.filter("setsar", "1")     # Force square pixels
            clip = clip.filter("tmix", frames=3)   # Temporal smoothing

            pattern_index += 1
            sub_clips.append(clip)

        # Concatenate all sub-clips into one video stream (no audio)
        animated = ffmpeg.concat(*sub_clips, v=1, a=0).node[0]

        # Encode to H.264 with slow preset for quality/compression balance
        outfile = ffmpeg.output(
            animated,
            str(video_path),
            vcodec="libx264",
            pix_fmt="yuv420p",
            r=fps,
            preset="slow",
        )
        outfile.run(overwrite_output=True, quiet=True)

        # Log duration verification
        probe_dur = ffmpeg.probe(str(video_path))["format"]["duration"]
        expected = (len(image_paths) - 1) * ideal_image_duration + last_image_duration
        logger.info(
            f"Clip: {video_path.name} duration={probe_dur}s (expected {expected:.1f}s)"
        )

    except ffmpeg.Error as e:
        err_msg = e.stderr.decode() if e.stderr else str(e)
        raise RuntimeError(f"FFmpeg animation error: {err_msg}")
