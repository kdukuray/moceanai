# MoceanAI

MoceanAI is an AI-powered video generation platform that automates the end-to-end creation of short-form and long-form video content. Given a topic and a set of creative parameters, it writes a script, generates a voice-over, produces AI-generated imagery, animates those images with cinematic motion effects, and assembles everything into a final video file — all orchestrated through an agentic workflow.

## How It Works

MoceanAI uses [LangGraph](https://github.com/langchain-ai/langgraph) to define a multi-step agent pipeline. Each node in the graph is responsible for a single stage of the video creation process. The agent state flows through the pipeline, accumulating generated artifacts (scripts, audio files, images, video clips) until a final video is assembled.

### Short-Form Content Pipeline

The short-form pipeline (`short_form_content.py`) targets platforms like TikTok, Instagram Reels, and YouTube Shorts. The workflow proceeds through the following stages:

1. **Resolve State Values** — Maps user-friendly configuration (e.g., voice actor names) to internal IDs required by downstream APIs.
2. **Generate Goal** — Uses an LLM to define a strategic goal for the video based on the topic, purpose, and target audience.
3. **Generate Hook** — Creates an attention-grabbing opening line tailored to the platform and tone.
4. **Generate Script** — Produces the full narration script in a single pass, respecting duration targets and style references.
5. **Enhance Script for Audio** — Optionally adds SSML (Speech Synthesis Markup Language) tags to improve voice-over delivery (pauses, emphasis, pacing).
6. **Segment Script** — Splits the script into logically cohesive segments that will each correspond to a visual clip.
7. **Generate Audio** — Sends the script (or enhanced script) to ElevenLabs for text-to-speech conversion with character-level timestamp alignment.
8. **Compute Segment Timings** — Aligns each script segment to precise start/end times in the generated audio using character-index mapping.
9. **Generate Image Descriptions** — For each segment, determines how many B-roll images are needed and produces detailed image prompts using the LLM.
10. **Generate Images** — Concurrently generates images using the selected provider (Google Imagen, OpenAI GPT-Image, or Flux).
11. **Animate Images** — Applies cinematic motion effects (zoom in/out, pan, Ken Burns) to static images using FFmpeg's zoompan filter, producing individual video clips.
12. **Assemble Final Video** — Concatenates all animated clips into a single video stream, multiplexes it with the audio track, and outputs the final `.mp4` file.

### Long-Form Content Pipeline

The long-form pipeline (`long_form_content.py`) extends the architecture for longer, structured videos (e.g., YouTube explainers). Key differences:

- **Structure Generation** — The LLM first creates a multi-section outline with named sections, purposes, directives, and talking points.
- **Section-by-Section Scripting** — Scripts are generated sequentially per section, with the cumulative script passed as context to maintain coherence.
- **Per-Section Audio & Visuals** — Audio, timing, image generation, and animation are performed independently per section, then concatenated.
- **Final Assembly** — Section videos (each with their own audio) are concatenated with both video and audio streams into the final output.

## Features

- **Multi-Provider LLM Support** — Supports Google Gemini, OpenAI, Anthropic Claude, xAI Grok, and DeepSeek for script generation.
- **Multi-Provider Image Generation** — Choose between Google Imagen 4.0 Ultra, OpenAI GPT-Image 1.5, or Flux 2 Pro for visuals.
- **ElevenLabs Voice-Over** — Multiple voice actors with character-level timestamp alignment for precise audio-visual synchronization.
- **Cinematic Motion Effects** — Configurable motion patterns (zoom in/out, pan, Ken Burns, rock) applied via FFmpeg with smooth frame interpolation.
- **Profile System** — Save and reuse brand profiles (name, description, target audience, brand color, slogan) so video parameters stay consistent across batches.
- **Batch Generation** — Paste a block of text and the system will extract individual topics and generate a separate video for each one.
- **Streamlit UI** — Interactive web interface for configuring and launching video generation, with real-time progress and debug output.
- **Portrait & Landscape** — Full support for both orientations across all image and video generation stages.
- **Async & Parallel Processing** — Image generation and animation tasks run concurrently using `asyncio.TaskGroup` and `ProcessPoolExecutor` for maximum throughput.

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) (StateGraph) |
| LLM Framework | [LangChain](https://github.com/langchain-ai/langchain) |
| Structured Output | [Pydantic](https://docs.pydantic.dev/) v2 |
| Voice Synthesis | [ElevenLabs](https://elevenlabs.io/) API |
| Image Generation | Google Imagen 4.0 Ultra, OpenAI GPT-Image 1.5, Flux 2 Pro |
| Video Processing | [FFmpeg](https://ffmpeg.org/) via [python-ffmpeg](https://github.com/kkroening/ffmpeg-python) |
| Web UI | [Streamlit](https://streamlit.io/) |
| Database | SQLite via [SQLAlchemy](https://www.sqlalchemy.org/) |
| Async Rate Limiting | [aiolimiter](https://github.com/mjpieters/aiolimiter) |

## Project Structure

```
moceanai/
├── moceanai.py                  # Main Streamlit app (single short-form video)
├── short_form_content.py        # Short-form video agent pipeline & LangGraph definition
├── long_form_content.py         # Long-form video agent pipeline & LangGraph definition
├── system_prompts.py            # All LLM system prompts (goal, hook, script, segmentation, images)
├── utils.py                     # Image generation, animation, FFmpeg helpers, topic extraction
├── errors.py                    # Custom exception classes
├── models.py                    # SQLAlchemy ORM models (Profile)
├── db.py                        # Database engine & session configuration
├── crud.py                      # CRUD operations for profiles
├── pages/
│   ├── multiple_video_gen.py    # Batch video generation (extract topics → generate videos)
│   └── profiles.py              # Profile management UI (create, update, delete)
├── utility_assets/              # Static assets (black buffer videos for end padding)
├── generated_audio_files/       # Output directory for generated voice-over audio
├── generated_image_files/       # Output directory for generated B-roll images
├── generated_video_files/       # Output directory for animated segment clips
├── generated_final_video_files/ # Output directory for assembled final videos
└── .env                         # API keys (not committed)
```

## Prerequisites

- **Python 3.11+**
- **FFmpeg** installed and available on `PATH`
- API keys for the services you intend to use:
  - `GOOGLE_API_KEY` — Google Gemini / Imagen
  - `ELEVEN_LABS_API_KEY` — ElevenLabs text-to-speech
  - `OPENAI_API_KEY` — OpenAI (optional, for GPT-Image)
  - `BFL_API_KEY` — Black Forest Labs / Flux (optional)

## Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/<your-username>/moceanai.git
   cd moceanai
   ```

2. **Create a virtual environment and install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   Create a `.env` file in the project root:

   ```env
   GOOGLE_API_KEY=your_google_api_key
   ELEVEN_LABS_API_KEY=your_elevenlabs_api_key
   OPENAI_API_KEY=your_openai_api_key        # optional
   BFL_API_KEY=your_flux_api_key              # optional
   ```

4. **Run the application**

   ```bash
   streamlit run moceanai.py
   ```

   The app will open in your browser. Use the sidebar and form to configure your video, then click **Generate Video**.

## Usage

### Single Video Generation

Navigate to the main page. Fill in the topic, purpose, target audience, tone, platform, duration, and select your preferred models and styles. Click **Generate Video** and wait for the pipeline to complete. The final video will be displayed inline.

### Batch Video Generation

Navigate to the **Multiple Video Gen** page. Paste a block of text containing multiple topics. The system uses an LLM to extract individual topics from the text, then generates a separate video for each one sequentially.

### Profile Management

Navigate to the **Profiles** page to create, update, or delete brand profiles. Profiles store target audience, description, brand colors, and slogans. When generating videos, select a profile to auto-fill the target audience and append brand context to the script instructions.

## License

This project is provided as-is for personal and educational use.
