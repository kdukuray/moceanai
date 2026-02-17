"""
Multi-provider image generation service with rate limiting and per-image retries.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import requests
from aiolimiter import AsyncLimiter
from google import genai
from google.genai import types
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from v2.core.config import (
    IMAGE_DIR,
    RATE_LIMIT_PERIOD,
    GOOGLE_SEMAPHORE,
    OPENAI_SEMAPHORE,
    FLUX_SEMAPHORE,
)

logger = logging.getLogger(__name__)


class _RateLimiters:
    """Per-event-loop rate limiters and semaphores for image generation APIs."""

    def __init__(self):
        self._loop = None
        self.google_limiter: Optional[AsyncLimiter] = None
        self.openai_limiter: Optional[AsyncLimiter] = None
        self.flux_limiter: Optional[AsyncLimiter] = None
        self.google_sem: Optional[asyncio.Semaphore] = None
        self.openai_sem: Optional[asyncio.Semaphore] = None
        self.flux_sem: Optional[asyncio.Semaphore] = None

    def ensure(self):
        loop = asyncio.get_running_loop()
        if self._loop is loop:
            return
        self._loop = loop
        self.google_limiter = AsyncLimiter(max_rate=1, time_period=RATE_LIMIT_PERIOD)
        self.openai_limiter = AsyncLimiter(max_rate=1, time_period=RATE_LIMIT_PERIOD)
        self.flux_limiter = AsyncLimiter(max_rate=1, time_period=RATE_LIMIT_PERIOD)
        self.google_sem = asyncio.Semaphore(GOOGLE_SEMAPHORE)
        self.openai_sem = asyncio.Semaphore(OPENAI_SEMAPHORE)
        self.flux_sem = asyncio.Semaphore(FLUX_SEMAPHORE)


_limiters = _RateLimiters()


class ImageService:
    """Generates images from text prompts using multiple providers with retries."""

    async def generate_images(
        self,
        descriptions: list[str],
        provider: str = "google",
        orientation: str = "portrait",
    ) -> list[Path]:
        """
        Generate multiple images in parallel with per-image retry logic.

        Returns list of saved image file paths.
        """
        _limiters.ensure()
        tasks = []

        async with asyncio.TaskGroup() as tg:
            for desc in descriptions:
                output_path = IMAGE_DIR / f"{uuid.uuid4().hex}.jpg"
                task = tg.create_task(
                    self._generate_single(desc, output_path, provider, orientation)
                )
                tasks.append((output_path, task))

        # Verify all succeeded
        paths = []
        for path, task in tasks:
            if task.exception():
                raise task.exception()
            paths.append(path)

        return paths

    async def _generate_single(
        self,
        prompt: str,
        output_path: Path,
        provider: str,
        orientation: str,
    ) -> None:
        """Generate a single image with retries."""
        image_bytes = None
        last_error = None

        for attempt in range(3):
            try:
                match provider:
                    case "google":
                        image_bytes = await self._generate_google(prompt, orientation)
                    case "openai":
                        image_bytes = await self._generate_openai(prompt, orientation)
                    case "flux":
                        image_bytes = await self._generate_flux(prompt, orientation)
                    case _:
                        raise ValueError(f"Unknown image provider: {provider}")

                if image_bytes:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(image_bytes)
                    logger.info(f"Image saved: {output_path.name}")
                    return
                else:
                    raise RuntimeError(f"Provider {provider} returned empty bytes")

            except Exception as e:
                last_error = e
                logger.warning(f"Image gen attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** (attempt + 1))

        raise RuntimeError(
            f"Image generation failed after 3 attempts ({provider}): {last_error}"
        )

    async def _generate_google(self, prompt: str, orientation: str) -> Optional[bytes]:
        def _sync_generate():
            client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
            config = types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9" if orientation.lower() == "landscape" else "9:16",
            )
            result = client.models.generate_images(
                model="imagen-4.0-ultra-generate-001",
                prompt=prompt,
                config=config,
            )
            return result.images[0].image_bytes

        async with _limiters.google_sem:
            async with _limiters.google_limiter:
                return await asyncio.to_thread(_sync_generate)

    async def _generate_openai(self, prompt: str, orientation: str) -> Optional[bytes]:
        def _sync_generate():
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            size = "1536x1024" if orientation.lower() == "landscape" else "1024x1536"
            result = client.images.generate(
                prompt=prompt,
                model="gpt-image-1.5",
                quality="high",
                size=size,
            )
            return base64.b64decode(result.data[0].b64_json)

        async with _limiters.openai_sem:
            async with _limiters.openai_limiter:
                return await asyncio.to_thread(_sync_generate)

    async def _generate_flux(self, prompt: str, orientation: str) -> Optional[bytes]:
        def _sync_generate():
            api_key = os.environ.get("BFL_API_KEY")
            resp = requests.post(
                "https://api.bfl.ai/v1/flux-2-pro",
                headers={
                    "accept": "application/json",
                    "x-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "prompt": prompt,
                    "width": 1088 if orientation.lower() == "portrait" else 1920,
                    "height": 1920 if orientation.lower() == "portrait" else 1088,
                },
            )
            resp.raise_for_status()
            polling_url = resp.json()["polling_url"]

            while True:
                poll = requests.get(
                    polling_url,
                    headers={"accept": "application/json", "x-key": api_key},
                ).json()
                if poll["status"] == "Ready":
                    img_resp = requests.get(poll["result"]["sample"], timeout=30)
                    img_resp.raise_for_status()
                    return img_resp.content
                elif poll["status"] == "Failed":
                    raise RuntimeError(f"Flux generation failed: {poll.get('error')}")
                time.sleep(0.5)

        async with _limiters.flux_sem:
            async with _limiters.flux_limiter:
                return await asyncio.to_thread(_sync_generate)
