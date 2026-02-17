"""
Video generation service supporting AI video generation APIs.

Instead of generating a static image and applying zoompan motion effects,
this service generates actual video clips from text prompts using APIs like:

  - Runway Gen-3 Alpha Turbo (via their REST API)
  - Luma Dream Machine (via their REST API)
  - Kling (via their REST API)

These models produce short (3-10 second) video clips from a text or
image-to-video prompt. As costs drop, they produce far more engaging
B-roll than zoompan on static images.

Usage:
    service = VideoGenerationService()
    video_path = await service.generate_video(
        prompt="A sweeping aerial shot of a modern city at sunset",
        provider="runway",
        duration=5,
        orientation="portrait",
    )

Environment variables required (depending on provider):
    RUNWAY_API_KEY     — For Runway Gen-3
    LUMA_API_KEY       — For Luma Dream Machine
    KLING_API_KEY      — For Kling

To add a new provider:
    1. Add a _generate_<provider> async method below
    2. Add the provider name to VIDEO_PROVIDERS in config.py
    3. Add a case in the match statement in generate_video()
    4. Add the API key env var name to the docstring above
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import requests

from v2.core.config import VIDEO_DIR

logger = logging.getLogger(__name__)

# Maximum time (seconds) to wait for an async video generation job to complete
MAX_POLL_DURATION = 300  # 5 minutes


class VideoGenerationService:
    """
    Generates short video clips from text prompts using AI video models.

    Each provider follows the same pattern:
      1. Submit a generation request (returns a job/task ID)
      2. Poll until the job completes or times out
      3. Download the resulting video file
      4. Save to disk and return the path

    All methods include retry logic (3 attempts with exponential backoff).
    """

    async def generate_video(
        self,
        prompt: str,
        provider: str = "runway",
        duration: int = 5,
        orientation: str = "portrait",
        image_path: Optional[Path] = None,
    ) -> Path:
        """
        Generate a single video clip from a text prompt.

        Args:
            prompt:       Descriptive text prompt for the video content.
            provider:     Which API to use: "runway", "luma", or "kling".
            duration:     Desired clip duration in seconds (provider may round).
            orientation:  "portrait" or "landscape" — determines aspect ratio.
            image_path:   Optional base image for image-to-video generation.
                          If provided, the video will animate from this image.

        Returns:
            Path to the saved .mp4 video clip on disk.

        Raises:
            RuntimeError: If generation fails after all retry attempts.
            ValueError:   If an unknown provider is specified.
        """
        output_path = VIDEO_DIR / f"{uuid.uuid4().hex}.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        last_error = None
        for attempt in range(3):
            try:
                match provider:
                    case "runway":
                        await self._generate_runway(
                            prompt, output_path, duration, orientation, image_path
                        )
                    case "luma":
                        await self._generate_luma(
                            prompt, output_path, duration, orientation, image_path
                        )
                    case "kling":
                        await self._generate_kling(
                            prompt, output_path, duration, orientation, image_path
                        )
                    case _:
                        raise ValueError(
                            f"Unknown video provider: '{provider}'. "
                            f"Supported: runway, luma, kling"
                        )

                # Verify the file was actually written
                if output_path.exists() and output_path.stat().st_size > 0:
                    logger.info(
                        f"Video generated: {output_path.name} "
                        f"(provider={provider}, attempt={attempt + 1})"
                    )
                    return output_path
                else:
                    raise RuntimeError("Output file is missing or empty after generation")

            except ValueError:
                raise  # Don't retry config errors
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Video gen attempt {attempt + 1}/3 failed "
                    f"(provider={provider}): {e}"
                )
                if attempt < 2:
                    await asyncio.sleep(2 ** (attempt + 1))

        raise RuntimeError(
            f"Video generation failed after 3 attempts "
            f"(provider={provider}): {last_error}"
        )

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    async def _generate_runway(
        self,
        prompt: str,
        output_path: Path,
        duration: int,
        orientation: str,
        image_path: Optional[Path],
    ) -> None:
        """
        Generate a video using Runway Gen-3 Alpha Turbo API.

        API docs: https://docs.dev.runwayml.com/

        Flow:
          1. POST /v1/image_to_video or /v1/text_to_video to create a task
          2. GET /v1/tasks/{id} polling until status is SUCCEEDED
          3. Download the output video URL
        """
        api_key = os.environ.get("RUNWAY_API_KEY")
        if not api_key:
            raise RuntimeError(
                "RUNWAY_API_KEY not set. Add it to your .env file to use Runway."
            )

        def _sync_generate() -> bytes:
            base_url = "https://api.dev.runwayml.com/v1"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Runway-Version": "2024-11-06",
            }

            # Determine aspect ratio from orientation
            ratio = "9:16" if orientation.lower() == "portrait" else "16:9"

            # Submit generation task
            payload = {
                "promptText": prompt,
                "model": "gen3a_turbo",
                "duration": min(duration, 10),  # Runway max is 10s
                "ratio": ratio,
            }

            # If an image is provided, use image-to-video endpoint
            if image_path and image_path.exists():
                import base64
                with open(image_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                payload["promptImage"] = f"data:image/jpeg;base64,{img_b64}"

            resp = requests.post(
                f"{base_url}/image_to_video",
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            task_id = resp.json()["id"]

            # Poll for completion
            start = time.time()
            while time.time() - start < MAX_POLL_DURATION:
                poll_resp = requests.get(
                    f"{base_url}/tasks/{task_id}",
                    headers=headers,
                    timeout=15,
                )
                poll_resp.raise_for_status()
                result = poll_resp.json()
                status = result.get("status")

                if status == "SUCCEEDED":
                    video_url = result["output"][0]
                    video_data = requests.get(video_url, timeout=60)
                    video_data.raise_for_status()
                    return video_data.content

                elif status == "FAILED":
                    raise RuntimeError(
                        f"Runway task failed: {result.get('failure', 'unknown error')}"
                    )

                time.sleep(5)

            raise RuntimeError(
                f"Runway task timed out after {MAX_POLL_DURATION}s"
            )

        video_bytes = await asyncio.to_thread(_sync_generate)
        with open(output_path, "wb") as f:
            f.write(video_bytes)

    async def _generate_luma(
        self,
        prompt: str,
        output_path: Path,
        duration: int,
        orientation: str,
        image_path: Optional[Path],
    ) -> None:
        """
        Generate a video using Luma Dream Machine API.

        API docs: https://docs.lumalabs.ai/

        Flow:
          1. POST /dream-machine/v1/generations to create generation
          2. GET /dream-machine/v1/generations/{id} polling until complete
          3. Download the output video
        """
        api_key = os.environ.get("LUMA_API_KEY")
        if not api_key:
            raise RuntimeError(
                "LUMA_API_KEY not set. Add it to your .env file to use Luma."
            )

        def _sync_generate() -> bytes:
            base_url = "https://api.lumalabs.ai/dream-machine/v1"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            ratio = "9:16" if orientation.lower() == "portrait" else "16:9"

            payload = {
                "prompt": prompt,
                "aspect_ratio": ratio,
            }

            # Image-to-video if image provided
            if image_path and image_path.exists():
                import base64
                with open(image_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                payload["keyframes"] = {
                    "frame0": {
                        "type": "image",
                        "url": f"data:image/jpeg;base64,{img_b64}",
                    }
                }

            resp = requests.post(
                f"{base_url}/generations",
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            gen_id = resp.json()["id"]

            # Poll for completion
            start = time.time()
            while time.time() - start < MAX_POLL_DURATION:
                poll_resp = requests.get(
                    f"{base_url}/generations/{gen_id}",
                    headers=headers,
                    timeout=15,
                )
                poll_resp.raise_for_status()
                result = poll_resp.json()
                state = result.get("state")

                if state == "completed":
                    video_url = result["assets"]["video"]
                    video_data = requests.get(video_url, timeout=60)
                    video_data.raise_for_status()
                    return video_data.content

                elif state == "failed":
                    raise RuntimeError(
                        f"Luma generation failed: {result.get('failure_reason', 'unknown')}"
                    )

                time.sleep(5)

            raise RuntimeError(
                f"Luma generation timed out after {MAX_POLL_DURATION}s"
            )

        video_bytes = await asyncio.to_thread(_sync_generate)
        with open(output_path, "wb") as f:
            f.write(video_bytes)

    async def _generate_kling(
        self,
        prompt: str,
        output_path: Path,
        duration: int,
        orientation: str,
        image_path: Optional[Path],
    ) -> None:
        """
        Generate a video using Kling API.

        API docs: https://docs.qingque.cn/  (Kling by Kuaishou)

        Flow:
          1. POST /v1/videos/text2video to create generation task
          2. GET /v1/videos/text2video/{task_id} polling until complete
          3. Download the output video
        """
        api_key = os.environ.get("KLING_API_KEY")
        if not api_key:
            raise RuntimeError(
                "KLING_API_KEY not set. Add it to your .env file to use Kling."
            )

        def _sync_generate() -> bytes:
            base_url = "https://api.klingai.com/v1"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            ratio = "9:16" if orientation.lower() == "portrait" else "16:9"

            payload = {
                "prompt": prompt,
                "duration": str(min(duration, 10)),
                "aspect_ratio": ratio,
                "model_name": "kling-v1",
            }

            resp = requests.post(
                f"{base_url}/videos/text2video",
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            task_id = resp.json()["data"]["task_id"]

            # Poll for completion
            start = time.time()
            while time.time() - start < MAX_POLL_DURATION:
                poll_resp = requests.get(
                    f"{base_url}/videos/text2video/{task_id}",
                    headers=headers,
                    timeout=15,
                )
                poll_resp.raise_for_status()
                result = poll_resp.json()
                status = result["data"]["task_status"]

                if status == "succeed":
                    video_url = result["data"]["task_result"]["videos"][0]["url"]
                    video_data = requests.get(video_url, timeout=60)
                    video_data.raise_for_status()
                    return video_data.content

                elif status == "failed":
                    raise RuntimeError(
                        f"Kling task failed: {result['data'].get('task_status_msg', 'unknown')}"
                    )

                time.sleep(5)

            raise RuntimeError(
                f"Kling task timed out after {MAX_POLL_DURATION}s"
            )

        video_bytes = await asyncio.to_thread(_sync_generate)
        with open(output_path, "wb") as f:
            f.write(video_bytes)
