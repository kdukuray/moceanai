"""
Centralized configuration for MoceanAI V2.

This is the single source of truth for all constants, enums, API key
lookups, and default settings. When you need to change a frame rate,
add a new voice actor, support a new LLM provider, or adjust rate
limits, this is the file to edit.

Organization:
  - Paths:          Where output files (audio, images, video) are saved
  - Video settings: FPS, resolution, overscale ratios for zoompan
  - Rate limiting:  Per-provider request throttling for image APIs
  - Enums/types:    Literal types for model providers, orientations, etc.
  - UI options:     Lists of choices shown in Streamlit dropdowns
  - Voice actors:   Name -> ElevenLabs voice ID mapping
  - LLM models:     Provider -> default model name mapping
  - Motion:         Zoompan animation pattern configuration
  - Visual modes:   zoompan vs AI video generation toggle
"""

import os
from enum import Enum
from typing import Literal
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one level above v2/)
load_dotenv()

# ---------------------------------------------------------------------------
# Paths — all output goes under v2/output/ with subdirectories per media type
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent          # v2/
OUTPUT_DIR = BASE_DIR / "output"
AUDIO_DIR = OUTPUT_DIR / "audio"                           # .mp3 voice-overs
IMAGE_DIR = OUTPUT_DIR / "images"                          # .jpg B-roll images
VIDEO_DIR = OUTPUT_DIR / "videos"                          # .mp4 per-segment clips
FINAL_VIDEO_DIR = OUTPUT_DIR / "final_videos"              # .mp4 assembled finals
SECTION_VIDEO_DIR = OUTPUT_DIR / "section_videos"          # .mp4 long-form sections
DB_PATH = BASE_DIR / "database.db"                         # SQLite database

# Create directories on import so we never get FileNotFoundError
for d in (AUDIO_DIR, IMAGE_DIR, VIDEO_DIR, FINAL_VIDEO_DIR, SECTION_VIDEO_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Video encoding settings
# ---------------------------------------------------------------------------
FPS = 48                                # Frame rate for all output video
PORTRAIT_SIZE = (1080, 1920)            # Width x Height for portrait (9:16)
LANDSCAPE_SIZE = (1920, 1080)           # Width x Height for landscape (16:9)
PORTRAIT_OVERSCALE = (2160, 3840)       # 2x portrait for zoompan headroom
LANDSCAPE_OVERSCALE = (3840, 2160)      # 2x landscape for zoompan headroom

IDEAL_IMAGE_DURATION = 3               # Default seconds per image in a segment
MIN_IMAGE_DURATION = 2                  # Shortest acceptable standalone image

# ---------------------------------------------------------------------------
# Rate limiting for image generation APIs
#
# Each provider gets a rate limiter (max 1 request per RATE_LIMIT_PERIOD)
# and a semaphore (max concurrent requests). This prevents 429 errors.
# Adjust these if you get rate-limited or want to go faster.
# ---------------------------------------------------------------------------
RATE_LIMIT_PERIOD = 9                   # Seconds between requests (per provider)
GOOGLE_SEMAPHORE = 8                    # Max concurrent Google Imagen requests
OPENAI_SEMAPHORE = 8                    # Max concurrent OpenAI image requests
FLUX_SEMAPHORE = 5                      # Max concurrent Flux requests

# ---------------------------------------------------------------------------
# Type aliases used by Pydantic models and function signatures
# ---------------------------------------------------------------------------
ModelProvider = Literal["google", "openai", "anthropic", "xai", "deepseek"]
ImageProvider = Literal["google", "openai", "flux"]
Orientation = Literal["Portrait", "Landscape"]
VoiceModelVersion = Literal["eleven_v3", "eleven_multilingual_v2"]

# ---------------------------------------------------------------------------
# UI dropdown options — used directly by Streamlit selectboxes
# ---------------------------------------------------------------------------
IMAGE_STYLES = [
    "Photo Realism",
    "Isometric Illustrations",
    "Vector Illustrations",
    "Hyperrealism",
    "Cartoon / 2D Illustration",
    "Minimalist / Flat Illustration",
    "Comic / Manga",
    "Cinematic",
    "3D Render / CGI",
    "Fantasy / Surreal",
    "Vintage / Retro",
]

PURPOSES = [
    "Educational",
    "Promotional",
    "Awareness",
    "Storytelling",
    "Motivational",
    "Tutorial",
    "News",
    "Entertainment",
]

TONES = [
    "Informative",
    "Conversational",
    "Professional",
    "Inspirational",
    "Humorous",
    "Dramatic",
    "Empathetic",
    "Persuasive",
    "Narrative",
    "Neutral",
]

PLATFORMS = ["TikTok", "Instagram", "YouTube"]

# ---------------------------------------------------------------------------
# Voice actors — maps friendly names to ElevenLabs voice IDs
#
# To add a new voice:
#   1. Find the voice ID in ElevenLabs dashboard
#   2. Add an entry here: "descriptive_name": "voice_id"
#   3. The name will automatically appear in UI dropdowns via VOICE_ACTOR_NAMES
# ---------------------------------------------------------------------------
VOICE_ACTORS: dict[str, str] = {
    "american_male_narrator": "Dslrhjl3ZpzrctukrQSN",
    "american_male_conversationalist": "Dslrhjl3ZpzrctukrQSN",
    "american_female_conversationalist": "tnSpp4vdxKPjI9w0GnoV",
    "british_male_narrator": "giAoKpl5weRTCJK7uB9b",
    "british_female_narrator": "1hlpeD1ydbI2ow0Tt3EW",
    "american_male_story_teller": "uju3wxzG5OhpWcoi3SMy",
    "american_female_narrator": "yj30vwTGJxSHezdAGsv9",
    "american_female_media_influencer": "kPzsL2i3teMYv0FxEYQ6",
    "american_female_media_influencer_2": "S9NKLs1GeSTKzXd9D0Lf",
}

VOICE_ACTOR_NAMES = list(VOICE_ACTORS.keys())

# ---------------------------------------------------------------------------
# LLM model mapping
#
# To add a new provider:
#   1. Add the provider key and default model name to LLM_MODELS
#   2. Add the LangChain provider string to LLM_PROVIDER_MAP
#   3. Make sure the API key env var is set (OPENAI_API_KEY, etc.)
# ---------------------------------------------------------------------------
LLM_MODELS: dict[str, str] = {
    "google": "gemini-2.5-pro",
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "xai": "grok-3-latest",
    "deepseek": "deepseek-chat",
}

LLM_PROVIDER_MAP: dict[str, str] = {
    "google": "google-genai",
    "openai": "openai",
    "anthropic": "anthropic",
    "xai": "xai",
    "deepseek": "deepseek",
}

# ---------------------------------------------------------------------------
# Motion patterns for zoompan animation
# Used by image_generator.py to cycle through effects across segments
# ---------------------------------------------------------------------------
MOTION_PATTERNS = ["zoom_in", "zoom_out", "pan_right", "pan_left", "ken_burns"]
DEFAULT_MOTION_PATTERN = ["zoom_in", "zoom_out"]

# ---------------------------------------------------------------------------
# Visual modes — how segment visuals are created
#
# "zoompan"   — Generate static images, apply FFmpeg camera motion (cheap, fast)
# "video_gen" — Use AI video generation APIs for actual video clips (expensive, higher quality)
# ---------------------------------------------------------------------------
VISUAL_MODES = ["zoompan", "video_gen"]

# Video generation providers (requires API key in .env):
#   RUNWAY_API_KEY  — Runway Gen-3 Alpha Turbo
#   LUMA_API_KEY    — Luma Dream Machine
#   KLING_API_KEY   — Kling by Kuaishou
VIDEO_PROVIDERS = ["runway", "luma", "kling"]
