"""
Audio generation pipeline with word-level alignment for precise visual sync.
Replaces v1's fragile character-index + offset approach.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from v2.core.models import (
    ScriptSegment,
    SectionScriptSegmentItem,
    WordAlignment,
    SegmentTiming,
)
from v2.services.elevenlabs_service import ElevenLabsService

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str], None]]


class AudioGenerator:
    """Generates audio and computes segment timings using word-level alignment."""

    def __init__(self):
        self.tts = ElevenLabsService()

    def generate_and_align_short_form(
        self,
        script: str,
        enhanced_script: str | None,
        segments: list[ScriptSegment],
        voice_actor: str,
        voice_model: str = "eleven_v3",
        use_enhanced: bool = True,
        on_progress: ProgressCallback = None,
    ) -> tuple[Path, list[WordAlignment], list[SegmentTiming]]:
        """
        Generate audio for the full script and compute per-segment timing.

        Strategy:
        1. Generate audio from enhanced_script (or raw script if not enhanced)
        2. Extract word-level alignment from ElevenLabs response
        3. Use word alignment to map each segment to its precise start/end time

        This eliminates the character-index + offset hack from v1.
        """
        if on_progress:
            on_progress("Generating voice-over audio...")

        # Choose which version to send to TTS
        tts_text = enhanced_script if (use_enhanced and enhanced_script) else script

        # Generate audio with word-level timestamps
        audio_path, word_alignments = self.tts.generate_audio(
            text=tts_text,
            voice_actor=voice_actor,
            voice_model=voice_model,
        )

        if on_progress:
            on_progress("Aligning audio to script segments...")

        # Extract the text versions we need for alignment
        # We align against the version that was actually sent to TTS
        if use_enhanced and enhanced_script:
            segment_texts = [seg.enhanced_script_segment for seg in segments]
        else:
            segment_texts = [seg.script_segment for seg in segments]

        # Use word-level alignment instead of character indexing
        segment_timings = ElevenLabsService.align_segments_to_words(
            segments=segment_texts,
            word_alignments=word_alignments,
        )

        logger.info(
            f"Audio generated: {audio_path.name}, "
            f"{len(word_alignments)} words, "
            f"{len(segment_timings)} segment timings"
        )

        return audio_path, word_alignments, segment_timings

    def generate_and_align_section(
        self,
        section_script: str,
        segments: list[SectionScriptSegmentItem],
        voice_actor: str,
        voice_model: str = "eleven_v3",
        on_progress: ProgressCallback = None,
    ) -> tuple[Path, list[WordAlignment], list[SegmentTiming]]:
        """
        Generate audio for a single long-form section and compute segment timing.
        Same word-level alignment strategy as short-form.
        """
        if on_progress:
            on_progress("Generating section audio...")

        audio_path, word_alignments = self.tts.generate_audio(
            text=section_script,
            voice_actor=voice_actor,
            voice_model=voice_model,
        )

        segment_texts = [seg.script_segment for seg in segments]

        segment_timings = ElevenLabsService.align_segments_to_words(
            segments=segment_texts,
            word_alignments=word_alignments,
        )

        logger.info(
            f"Section audio: {audio_path.name}, "
            f"{len(segment_timings)} segment timings"
        )

        return audio_path, word_alignments, segment_timings


def compute_images_per_segment(
    segment_duration: float,
    ideal_duration: float = 3.0,
    min_duration: float = 2.0,
) -> tuple[int, float]:
    """
    Determine how many B-roll images a segment needs and the last image's duration.

    Logic:
    - Divide segment into chunks of ideal_duration.
    - If leftover > min_duration, make it a separate image.
    - Otherwise, absorb leftover into the last image.
    - Always at least 1 image.
    """
    if segment_duration <= ideal_duration:
        return 1, segment_duration

    full_images, excess = divmod(segment_duration, ideal_duration)

    if excess > min_duration:
        return int(full_images + 1), excess
    else:
        return int(full_images), ideal_duration + excess
