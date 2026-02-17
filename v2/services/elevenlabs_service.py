"""
ElevenLabs TTS service with word-level alignment for precise audio-visual sync.

This is the key improvement over v1's character-level indexing approach.

v1 Problem:
    v1 used character-level arrays from ElevenLabs (characters[], start_times[],
    end_times[]) and walked through them with manual index offsets (+1 for spaces,
    +2 for gaps). This was brittle — a single character mismatch between the
    script and the TTS output would break all downstream timing.

v2 Solution:
    This service extracts word-level timing from ElevenLabs' character data,
    then uses string matching (exact first, fuzzy fallback) to map each script
    segment to its precise start/end time in the audio. This is robust to:
      - Minor wording differences between script and TTS output
      - Whitespace variations
      - Punctuation changes made by the TTS engine

Key functions:
    generate_audio()           — Generate audio file + word-level timestamps
    align_segments_to_words()  — Map script segments to audio timestamps
    _fuzzy_find()              — Fallback string matching for alignment

Usage:
    service = ElevenLabsService()
    audio_path, words = service.generate_audio("Hello world", "american_female_conversationalist")
    timings = ElevenLabsService.align_segments_to_words(["Hello", "world"], words)
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from difflib import SequenceMatcher
from pathlib import Path

from elevenlabs import ElevenLabs
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from v2.core.config import AUDIO_DIR, VOICE_ACTORS
from v2.core.models import WordAlignment, SegmentTiming

logger = logging.getLogger(__name__)


class ElevenLabsService:
    """
    Generates audio with word-level timestamps and aligns script segments.

    This service wraps the ElevenLabs API to:
      1. Generate speech from text with character-level timing data
      2. Reconstruct word-level timing from the character data
      3. Map script segments to audio timestamps using string matching
    """

    def __init__(self):
        api_key = os.getenv("ELEVEN_LABS_API_KEY")
        if not api_key:
            raise ValueError("ELEVEN_LABS_API_KEY not set in environment")
        self._client = ElevenLabs(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=3, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def generate_audio(
        self,
        text: str,
        voice_actor: str,
        voice_model: str = "eleven_v3",
        output_format: str = "mp3_44100_128",
    ) -> tuple[Path, list[WordAlignment]]:
        """
        Generate audio from text with word-level alignment data.

        Args:
            text:          The script text to convert to speech.
            voice_actor:   Friendly name (looked up in VOICE_ACTORS config).
            voice_model:   ElevenLabs model ID (default: "eleven_v3").
            output_format: Audio format (default: "mp3_44100_128").

        Returns:
            Tuple of:
              - Path to the saved .mp3 audio file
              - List of WordAlignment objects with per-word start/end times

        Raises:
            ValueError:  If voice_actor is not in VOICE_ACTORS config.
            Exception:   After 3 failed API attempts.
        """
        voice_id = VOICE_ACTORS.get(voice_actor)
        if not voice_id:
            raise ValueError(f"Unknown voice actor: {voice_actor}")

        logger.info(f"Generating audio: voice={voice_actor}, model={voice_model}")

        # Call ElevenLabs API with timestamp data
        result = self._client.text_to_speech.convert_with_timestamps(
            text=text,
            model_id=voice_model,
            voice_id=voice_id,
            output_format=output_format,
        )

        # Save the audio file to disk
        audio_path = AUDIO_DIR / f"{uuid.uuid4().hex}.mp3"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audio_path, "wb") as f:
            f.write(base64.b64decode(result.audio_base_64))

        # Extract word-level alignment from character-level data
        word_alignments = self._extract_word_alignments(result)

        logger.info(f"Audio saved: {audio_path} ({len(word_alignments)} words)")
        return audio_path, word_alignments

    def _extract_word_alignments(self, result) -> list[WordAlignment]:
        """
        Reconstruct word-level timing from ElevenLabs' character-level data.

        ElevenLabs returns three parallel arrays:
          - characters:                  ['H', 'e', 'l', 'l', 'o', ' ', 'w', ...]
          - character_start_times_seconds: [0.0, 0.05, 0.1, ...]
          - character_end_times_seconds:   [0.05, 0.1, 0.15, ...]

        We group non-space characters into words and use the first character's
        start_time and last character's end_time as the word's timing.

        Returns:
            List of WordAlignment objects, one per word in the audio.
        """
        alignment = result.normalized_alignment
        if not alignment or not alignment.characters:
            return []

        chars = alignment.characters
        starts = alignment.character_start_times_seconds
        ends = alignment.character_end_times_seconds

        words: list[WordAlignment] = []
        current_word = ""
        word_start = None

        for i, char in enumerate(chars):
            if char == " ":
                # Space = word boundary. Emit the accumulated word.
                if current_word:
                    words.append(WordAlignment(
                        word=current_word,
                        start_time=word_start,
                        end_time=ends[i - 1] if i > 0 else starts[i],
                    ))
                    current_word = ""
                    word_start = None
            else:
                # Non-space character: accumulate into current word
                if word_start is None:
                    word_start = starts[i]
                current_word += char

        # Don't forget the last word (no trailing space)
        if current_word and word_start is not None:
            words.append(WordAlignment(
                word=current_word,
                start_time=word_start,
                end_time=ends[len(chars) - 1],
            ))

        return words

    @staticmethod
    def align_segments_to_words(
        segments: list[str],
        word_alignments: list[WordAlignment],
    ) -> list[SegmentTiming]:
        """
        Map script segments to audio timestamps using word-level alignment.

        This is the core improvement over v1's approach. Instead of walking
        character arrays with manual +1/+2 offsets, we:

          1. Build the full transcript by joining all words
          2. Build a char-to-word-index mapping
          3. For each segment, find its position in the transcript (exact match
             first, fuzzy fallback if the TTS slightly altered the text)
          4. Map the character range to word indices -> get start/end times

        The fuzzy fallback uses SequenceMatcher to handle cases where the TTS
        engine slightly modifies the text (e.g., "you'll" vs "you will").

        Args:
            segments:        List of script segment strings to align.
            word_alignments: Word-level timing from generate_audio().

        Returns:
            List of SegmentTiming with start_time, end_time, duration for
            each segment. Same length as segments.
        """
        if not word_alignments:
            return []

        # Step 1: Reconstruct the full transcript from word alignments
        full_words = [w.word for w in word_alignments]
        full_text = " ".join(full_words)

        # Step 2: Build a mapping from character position -> word index
        # This lets us convert a character range (from string search)
        # into a word range (which has timing data).
        char_to_word: list[int] = []
        for word_idx, word in enumerate(full_words):
            char_to_word.extend([word_idx] * len(word))
            if word_idx < len(full_words) - 1:
                char_to_word.append(word_idx)  # space character

        results: list[SegmentTiming] = []
        search_start = 0  # Track position to search from (avoids re-matching)

        for segment in segments:
            segment_clean = segment.strip()
            if not segment_clean:
                continue

            # Step 3a: Try exact substring match first
            idx = full_text.find(segment_clean, search_start)

            if idx == -1:
                # Step 3b: Fuzzy fallback for TTS text differences
                idx = _fuzzy_find(full_text, segment_clean, search_start)

            if idx == -1:
                # Step 3c: Last resort — proportional timing estimation
                logger.warning(
                    f"Could not align segment, using proportional timing: "
                    f"'{segment_clean[:50]}...'"
                )
                if results:
                    last_end = results[-1].end_time
                else:
                    last_end = 0.0
                total_duration = (
                    word_alignments[-1].end_time if word_alignments else 0
                )
                remaining = total_duration - last_end
                proportion = len(segment_clean) / max(
                    len(full_text) - search_start, 1
                )
                seg_duration = remaining * proportion
                results.append(SegmentTiming(
                    start_time=last_end,
                    end_time=last_end + seg_duration,
                    duration=seg_duration,
                ))
                search_start = (
                    idx + len(segment_clean) if idx >= 0
                    else search_start + len(segment_clean)
                )
                continue

            # Step 4: Map character range to word indices
            char_end = idx + len(segment_clean) - 1

            # Clamp indices to valid range
            start_word_idx = char_to_word[min(idx, len(char_to_word) - 1)]
            end_word_idx = char_to_word[min(char_end, len(char_to_word) - 1)]

            start_time = word_alignments[start_word_idx].start_time
            end_time = word_alignments[end_word_idx].end_time

            # Add a small gap buffer for the transition between segments.
            # This absorbs the silence between the end of one segment and
            # the start of the next, up to 300ms maximum.
            if end_word_idx + 1 < len(word_alignments):
                gap = word_alignments[end_word_idx + 1].start_time - end_time
                end_time += min(gap, 0.3)

            duration = end_time - start_time
            results.append(SegmentTiming(
                start_time=start_time,
                end_time=end_time,
                duration=max(duration, 0.1),  # Minimum 100ms
            ))

            search_start = idx + len(segment_clean)

        return results


def _fuzzy_find(haystack: str, needle: str, start: int = 0) -> int:
    """
    Find the best approximate match position for needle in haystack.

    Uses a sliding window with SequenceMatcher to find where the needle
    text most closely appears. This handles cases where the TTS engine
    slightly modified the text (contractions, punctuation changes, etc.).

    Args:
        haystack: The full text to search in.
        needle:   The segment text to find.
        start:    Character position to start searching from.

    Returns:
        Character index of the best match, or -1 if no match >= 60% similar.
    """
    search_area = haystack[start:]
    if not search_area or not needle:
        return -1

    best_ratio = 0.0
    best_pos = -1
    needle_len = len(needle)

    # Slide a window of needle's length across the search area.
    # Step by 1/4 of the needle length for speed (not every character).
    step = max(1, needle_len // 4)
    for i in range(0, len(search_area) - needle_len + 1, step):
        candidate = search_area[i:i + needle_len]
        ratio = SequenceMatcher(
            None, needle.lower(), candidate.lower()
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_pos = i

    # Only accept matches that are at least 60% similar
    if best_ratio >= 0.6:
        return start + best_pos

    return -1
