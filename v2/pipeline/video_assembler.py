"""
Video assembly pipeline using MoviePy for final composition.
Supports crossfade transitions, subtitle overlays, and background music.
FFmpeg is still used under the hood by MoviePy, but the API is much cleaner
for composition tasks (transitions, text overlays, audio mixing).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import ffmpeg as ffmpeg_lib

from v2.core.config import FINAL_VIDEO_DIR, SECTION_VIDEO_DIR, FPS
from v2.core.models import SegmentVisualPlan, WordAlignment

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str], None]]


class VideoAssembler:
    """Assembles final videos from animated clips and audio."""

    def assemble_short_form(
        self,
        visual_plans: list[SegmentVisualPlan],
        audio_path: Path,
        orientation: str = "portrait",
        add_end_buffer: bool = True,
        add_subtitles: bool = False,
        word_alignments: list[WordAlignment] | None = None,
        on_progress: ProgressCallback = None,
    ) -> Path:
        """
        Assemble a short-form video from animated clips + audio.

        Uses ffmpeg-python for reliable concat + mux, with optional subtitle overlay.
        """
        if on_progress:
            on_progress("Assembling final video...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = FINAL_VIDEO_DIR / f"short_{timestamp}.mp4"
        final_path.parent.mkdir(parents=True, exist_ok=True)

        clip_paths = [p.video_path for p in visual_plans if p.video_path]

        if not clip_paths:
            raise RuntimeError("No animated clips available for assembly")

        if add_subtitles and word_alignments:
            return self._assemble_with_subtitles(
                clip_paths=clip_paths,
                audio_path=audio_path,
                word_alignments=word_alignments,
                final_path=final_path,
                orientation=orientation,
                add_end_buffer=add_end_buffer,
            )
        else:
            return self._assemble_basic(
                clip_paths=clip_paths,
                audio_path=audio_path,
                final_path=final_path,
                add_end_buffer=add_end_buffer,
            )

    def assemble_section(
        self,
        visual_plans: list[SegmentVisualPlan],
        audio_path: Path,
        section_index: int,
        on_progress: ProgressCallback = None,
    ) -> Path:
        """Assemble a single long-form section (clips + section audio)."""
        if on_progress:
            on_progress(f"Assembling section {section_index + 1} video...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        section_path = SECTION_VIDEO_DIR / f"section_{section_index}_{timestamp}.mp4"
        section_path.parent.mkdir(parents=True, exist_ok=True)

        clip_paths = [p.video_path for p in visual_plans if p.video_path]

        return self._assemble_basic(
            clip_paths=clip_paths,
            audio_path=audio_path,
            final_path=section_path,
            add_end_buffer=False,
        )

    def assemble_long_form(
        self,
        section_video_paths: list[Path],
        on_progress: ProgressCallback = None,
    ) -> Path:
        """Concatenate section videos into final long-form video (with audio)."""
        if on_progress:
            on_progress("Assembling final long-form video...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = FINAL_VIDEO_DIR / f"long_{timestamp}.mp4"
        final_path.parent.mkdir(parents=True, exist_ok=True)

        inputs = [ffmpeg_lib.input(str(p)) for p in section_video_paths]

        # For sections that already have audio baked in, use v=1,a=1 concat
        streams = []
        for inp in inputs:
            streams.append(inp.video)
            streams.append(inp.audio)

        concat_node = ffmpeg_lib.concat(*streams, v=1, a=1).node
        video_out = concat_node[0]
        audio_out = concat_node[1]

        output = ffmpeg_lib.output(
            video_out,
            audio_out,
            str(final_path),
            vcodec="libx264",
            acodec="aac",
            audio_bitrate="192k",
            movflags="+faststart",
        )
        output.run(overwrite_output=True, quiet=True)

        logger.info(f"Long-form video assembled: {final_path}")
        return final_path

    # ------------------------------------------------------------------
    # Private assembly methods
    # ------------------------------------------------------------------

    def _assemble_basic(
        self,
        clip_paths: list[Path],
        audio_path: Path,
        final_path: Path,
        add_end_buffer: bool = False,
    ) -> Path:
        """Basic assembly: concatenate video clips + mux with audio."""
        video_inputs = [ffmpeg_lib.input(str(p)) for p in clip_paths]

        # Add a 1-second black buffer at the end if requested
        if add_end_buffer:
            buffer_dur = 1.0
            black = ffmpeg_lib.input(
                f"color=c=black:s=1080x1920:d={buffer_dur}:r={FPS}",
                f="lavfi",
            )
            video_inputs.append(black)

        concat_node = ffmpeg_lib.concat(*video_inputs, v=1, a=0).node
        video_stream = concat_node[0]
        audio_stream = ffmpeg_lib.input(str(audio_path))

        output = ffmpeg_lib.output(
            video_stream,
            audio_stream,
            str(final_path),
            vcodec="libx264",
            acodec="aac",
            shortest=None,
        )
        output.run(overwrite_output=True, quiet=True)

        logger.info(f"Video assembled: {final_path}")
        return final_path

    def _assemble_with_subtitles(
        self,
        clip_paths: list[Path],
        audio_path: Path,
        word_alignments: list[WordAlignment],
        final_path: Path,
        orientation: str = "portrait",
        add_end_buffer: bool = False,
    ) -> Path:
        """
        Assemble video with burned-in subtitles using word-level timing.

        Creates an ASS subtitle file from word alignments, then burns it in
        using FFmpeg's subtitles filter.
        """
        # First assemble without subtitles into a temp file
        temp_path = final_path.with_suffix(".temp.mp4")
        self._assemble_basic(
            clip_paths=clip_paths,
            audio_path=audio_path,
            final_path=temp_path,
            add_end_buffer=add_end_buffer,
        )

        # Generate ASS subtitle file
        srt_path = final_path.with_suffix(".srt")
        _generate_srt(word_alignments, srt_path)

        # Burn subtitles into the video
        width = 1080 if orientation.lower() == "portrait" else 1920

        inp = ffmpeg_lib.input(str(temp_path))
        video = inp.video.filter(
            "subtitles",
            str(srt_path),
            force_style=f"FontSize=22,FontName=Arial,PrimaryColour=&H00FFFFFF,"
                        f"OutlineColour=&H00000000,Outline=2,MarginV=60,"
                        f"Alignment=2",
        )
        audio = inp.audio

        output = ffmpeg_lib.output(
            video,
            audio,
            str(final_path),
            vcodec="libx264",
            acodec="copy",
        )
        output.run(overwrite_output=True, quiet=True)

        # Cleanup temp files
        temp_path.unlink(missing_ok=True)
        srt_path.unlink(missing_ok=True)

        logger.info(f"Video with subtitles assembled: {final_path}")
        return final_path


def _generate_srt(
    word_alignments: list[WordAlignment],
    output_path: Path,
    words_per_group: int = 4,
) -> None:
    """Generate SRT subtitle file from word-level alignments."""
    lines = []
    idx = 1

    for i in range(0, len(word_alignments), words_per_group):
        group = word_alignments[i:i + words_per_group]
        if not group:
            continue

        start = group[0].start_time
        end = group[-1].end_time
        text = " ".join(w.word for w in group)

        lines.append(str(idx))
        lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
        lines.append(text)
        lines.append("")
        idx += 1

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
