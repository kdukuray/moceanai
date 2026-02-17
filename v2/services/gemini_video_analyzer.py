"""
Gemini multimodal video analysis service.

Uses Google's Gemini 2.5 Flash model via the google-genai SDK to analyze
uploaded reference videos and extract structured data about their style,
pacing, hooks, shot types, and overall approach.

This service is used by the UGC pipeline to:
  1. Analyze reference/inspiration videos uploaded by the user
  2. Extract structured cues (ReferenceVideoAnalysis) that the script
     writer agent can use to mirror what's working in viral content
  3. Describe product appearance from uploaded product photos

The Gemini Files API is used for video uploads (supports files >20MB),
and the model processes both the visual frames and audio track.

Usage:
    analyzer = GeminiVideoAnalyzer()
    analysis = await analyzer.analyze_video(Path("reference.mp4"))
    print(analysis.hook_style, analysis.pacing)

Environment variables required:
    GOOGLE_API_KEY -- Google AI API key for Gemini access
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from v2.core.ugc_models import (
    ReferenceVideoAnalysis,
    ReferenceVideoAnalysisContainer,
    ProductVisualDescriptionContainer,
)
from v2.core.ugc_prompts import (
    UGC_REFERENCE_VIDEO_ANALYSIS_PROMPT,
    UGC_PRODUCT_IMAGE_DESCRIPTION_PROMPT,
)

logger = logging.getLogger(__name__)

# Gemini model to use for multimodal analysis
# Flash is cheaper and faster; sufficient for structured extraction
GEMINI_ANALYSIS_MODEL = "gemini-2.5-flash"


class GeminiVideoAnalyzer:
    """
    Analyzes videos and images using Gemini's multimodal capabilities.

    Methods:
        analyze_video()    -- Extract structured data from one reference video
        analyze_multiple() -- Analyze up to 3 videos in parallel
        describe_product() -- Describe a product's appearance from photos
    """

    def __init__(self):
        """Initialize the Gemini client with the Google API key."""
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set in environment")
        self._client = genai.Client(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=3, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def analyze_video(self, video_path: Path) -> ReferenceVideoAnalysis:
        """
        Analyze a single reference video using Gemini multimodal.

        Uploads the video via the Gemini Files API, then sends it with the
        analysis prompt. Parses the structured JSON response into a
        ReferenceVideoAnalysis object.

        Args:
            video_path: Path to the video file on disk (.mp4, .mov, .webm).

        Returns:
            ReferenceVideoAnalysis with extracted cues (hook, pacing, tone, etc.)

        Raises:
            RuntimeError: If the video can't be processed or the response is invalid.
            FileNotFoundError: If the video file doesn't exist.
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Reference video not found: {video_path}")

        logger.info(f"Analyzing reference video: {video_path.name}")

        def _sync_analyze() -> ReferenceVideoAnalysis:
            # Upload the video to Gemini's Files API for processing
            uploaded_file = self._client.files.upload(file=str(video_path))
            logger.info(f"Video uploaded to Gemini: {uploaded_file.name}")

            # Send the video + analysis prompt to Gemini
            response = self._client.models.generate_content(
                model=GEMINI_ANALYSIS_MODEL,
                contents=[uploaded_file, UGC_REFERENCE_VIDEO_ANALYSIS_PROMPT],
            )

            # Parse the JSON response
            response_text = response.text.strip()
            # Strip markdown code fences if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            parsed = json.loads(response_text)
            container = ReferenceVideoAnalysisContainer(**parsed)
            return container.analysis

        return await asyncio.to_thread(_sync_analyze)

    async def analyze_multiple(
        self, video_paths: list[Path]
    ) -> list[ReferenceVideoAnalysis]:
        """
        Analyze multiple reference videos in parallel.

        Args:
            video_paths: List of video file paths (max 3 recommended).

        Returns:
            List of ReferenceVideoAnalysis, one per video.
            Failed analyses are logged and skipped (not raised).
        """
        results: list[ReferenceVideoAnalysis] = []

        if not video_paths:
            return results

        tasks = []
        async with asyncio.TaskGroup() as tg:
            for path in video_paths[:3]:  # Cap at 3 videos
                task = tg.create_task(self._safe_analyze(path))
                tasks.append(task)

        for task in tasks:
            result = task.result()
            if result is not None:
                results.append(result)

        logger.info(f"Analyzed {len(results)}/{len(video_paths)} reference videos")
        return results

    async def _safe_analyze(self, video_path: Path) -> Optional[ReferenceVideoAnalysis]:
        """Analyze a video, returning None instead of raising on failure."""
        try:
            return await self.analyze_video(video_path)
        except Exception as e:
            logger.warning(f"Failed to analyze reference video {video_path.name}: {e}")
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=3, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def describe_product(self, image_paths: list[Path]) -> str:
        """
        Describe a product's visual appearance from uploaded photos.

        Sends multiple product images to Gemini multimodal and gets back
        a detailed text description that can be embedded into image generation
        prompts so the AI knows exactly what the product looks like.

        Args:
            image_paths: Paths to product photos (ideally from multiple angles).

        Returns:
            Exhaustive text description of the product's visual appearance.
        """
        if not image_paths:
            return "No product images provided."

        logger.info(f"Describing product from {len(image_paths)} images")

        def _sync_describe() -> str:
            # Build the content parts: images + prompt
            content_parts = []

            for img_path in image_paths:
                if not img_path.exists():
                    continue
                # Upload each image to Gemini Files API
                uploaded = self._client.files.upload(file=str(img_path))
                content_parts.append(uploaded)

            if not content_parts:
                return "No valid product images found."

            # Add the prompt after the images
            content_parts.append(UGC_PRODUCT_IMAGE_DESCRIPTION_PROMPT)

            response = self._client.models.generate_content(
                model=GEMINI_ANALYSIS_MODEL,
                contents=content_parts,
            )

            # Parse the JSON response
            response_text = response.text.strip()
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            parsed = json.loads(response_text)
            container = ProductVisualDescriptionContainer(**parsed)
            return container.product_visual_description

        return await asyncio.to_thread(_sync_describe)
