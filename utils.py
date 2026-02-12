import time
from pathlib import Path
from typing import Literal, Union
from google import genai
from google.genai import types
import os

from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from openai import OpenAI
import base64
import ffmpeg
from system_prompts import topics_extractor_system_prompt
import requests as r
import asyncio
from typing import Optional
import dotenv

dotenv.load_dotenv()

class TopicsContainer(BaseModel):
    topics: list[str] = Field(..., description="List of topic extracted from the text.")

ai_model = init_chat_model(model_provider="google-genai", model="gemini-2.5-pro")

# Enums
model_providers = Literal["google", "openai", "claude", "xai", "deepseek"]
image_models = Literal["google", "openai", "flux"]
image_styles = Literal[
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
voice_model_versions = Literal["eleven_v3", "eleven_multilingual_v2"]
voice_models = Literal["elevenlabs"]
voice_actors = Literal[
    "american_male_narrator",
    "american_male_conversationalist",
    "american_female_conversationalist",
    "british_male_narrator",
    "british_female_narrator",
    "american_male_story_teller",
    "american_female_narrator",
    "american_female_media_influencer",
    "american_female_media_influencer_2",
    "new_male_convo"
]

from aiolimiter import AsyncLimiter
import asyncio

class LoopBoundLimits:
    def __init__(self):
        self._loop = None

        self.google_limiter = None
        self.openai_limiter = None
        self.flux_limiter = None

        self.google_sem = None
        self.openai_sem = None
        self.flux_sem = None

    def ensure(self):
        loop = asyncio.get_running_loop()
        if self._loop is loop:
            return

        # loop changed (or first time) -> rebuild everything
        self._loop = loop

        rate = 1
        period = 9  # your current math

        self.google_limiter = AsyncLimiter(max_rate=rate, time_period=period)
        self.openai_limiter  = AsyncLimiter(max_rate=rate, time_period=period)
        self.flux_limiter    = AsyncLimiter(max_rate=rate, time_period=period)

        self.google_sem = asyncio.Semaphore(8)
        self.openai_sem = asyncio.Semaphore(8)
        self.flux_sem   = asyncio.Semaphore(5)

limits = LoopBoundLimits()


# google_image_generation_limiter = AsyncLimiter(max_rate=1, time_period=60/9)
# openai_image_generation_limiter = AsyncLimiter(max_rate=1, time_period=60/9)
# flux_image_generation_limiter = AsyncLimiter(max_rate=1, time_period=60/9)
# flux_image_generation_semaphore = asyncio.Semaphore(8)
# google_image_generation_semaphore = asyncio.Semaphore(8)
# openai_image_generation_semaphore = asyncio.Semaphore(8)

async def generate_image_with_flux(prompt: str, orientation: str) -> Optional[bytes]:
    def _generate_image_with_flux(_prompt: str, _orientation: str) ->Optional[bytes]:
        api_response = r.post(
            "https://api.bfl.ai/v1/flux-2-pro",
            headers={
                "accept": "application/json",
                "x-key": os.environ.get("BFL_API_KEY"),
                "Content-Type": "application/json",
            },
            json={
                "prompt": _prompt,
                "width": 1088 if _orientation == "portrait" else 1920,
                "height": 1920 if _orientation == "portrait" else 1088,
            },
        )
        api_response.raise_for_status()
        json_response = api_response.json()
        polling_url = json_response["polling_url"]
        image_url = ""
        while True:
            result = r.get(
                polling_url,
                headers={"accept": "application/json", "x-key": os.environ.get("BFL_API_KEY")}
            ).json()

            if result["status"] == "Ready":
                image_url = result["result"]["sample"]
                print(f"Image URL: {result['result']['sample']}")
                break
            elif result["status"] == "Failed":
                print(f"Error: {result['error']}")
                break

            time.sleep(0.5)

        if image_url:
            image_response = r.get(image_url, timeout=20)
            image_response.raise_for_status()
            return image_response.content
        return None
    limits.ensure()
    async with limits.flux_sem:
        async with limits.flux_limiter:
            return await asyncio.to_thread(_generate_image_with_flux, prompt, orientation)


async def generate_image_with_gemini(prompt: str, orientation: str) -> Optional[bytes]:
    def _generate_image_with_gemini(_prompt: str, _orientation: str) -> Optional[bytes]:
        gemini_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        image_config = types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="16:9" if _orientation == "landscape" else "9:16",
        )
        generated_image_container = gemini_client.models.generate_images(
            model="imagen-4.0-ultra-generate-001",
            prompt=_prompt,
            config=image_config,
        )
        return generated_image_container.images[0].image_bytes
    limits.ensure()
    async with limits.google_sem:
        async with limits.google_limiter:
            return await asyncio.to_thread(_generate_image_with_gemini, prompt, orientation)


async def generate_image_with_openai(prompt: str, orientation: str) -> Optional[bytes]:
    def _generate_image_with_openai(_prompt: str, _orientation: str) -> Optional[bytes]:
        openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        generated_image = openai_client.images.generate(
            prompt=_prompt,
            model="gpt-image-1.5",
            quality="high",
            size="1536x1024" if _orientation == "landscape" else "1024x1536"
        )
        return base64.b64decode(generated_image.data[0].b64_json)
    limits.ensure()
    async with limits.openai_sem:
        async with limits.openai_limiter:
            return await asyncio.to_thread(_generate_image_with_openai, prompt, orientation)

def get_video_duration(video_path: str) -> float:
    """Get duration of video file in seconds."""
    try:
        probe = ffmpeg.probe(video_path)
        duration = float(probe['format']['duration'])
        return duration
    except ffmpeg.Error as e:
        print(f"Error probing video file: {e.stderr.decode()}")
        return 0.0


async def generate_image(image_descriptions: str | list[str], image_paths: Path | list[Path], image_model_provider: str, orientation: str):
    if isinstance(image_descriptions, str):
        image_descriptions = [image_descriptions]
    if isinstance(image_paths, Path):
        image_paths = [image_paths]

    if len(image_descriptions) != len(image_paths):
        raise ValueError("Image descriptions and image paths must have the same length.")

    print("generate_image ran...")

    tasks: list[tuple[int, asyncio.Task[Optional[bytes]]]] = []
    async with asyncio.TaskGroup() as tg:
        for index, image_description in enumerate(image_descriptions):
            match image_model_provider:
                case "google":
                    image_generation_task = tg.create_task(generate_image_with_gemini(prompt=image_description, orientation=orientation))

                case "openai":
                    image_generation_task = tg.create_task(generate_image_with_openai(prompt=image_description, orientation=orientation))

                case "flux":
                    image_generation_task = tg.create_task(generate_image_with_flux(prompt=image_description, orientation=orientation))

            tasks.append((index, image_generation_task))
    for index, image_generation_task in tasks:
        image_generation_result = image_generation_task.result()
        if image_generation_result:
            with open(image_paths[index], "wb") as image_file:
                image_file.write(image_generation_result)
        else: # generation failed, we need retry logic later
            raise RuntimeError(f"Image generation failed. Image model {image_model_provider}.")

#
# def generate_image(image_descriptions: str | list[str], image_paths: Path | list[Path], image_model_provider: str,
#                    orientation: str):
#     if isinstance(image_descriptions, str):
#         image_descriptions = [image_descriptions]
#     if isinstance(image_paths, Path):
#         image_paths = [image_paths]
#
#     if len(image_descriptions) != len(image_paths):
#         raise ValueError("Image descriptions and image paths must have the same length.")
#     print("generate_image ran...")
#     for index, image_description in enumerate(image_descriptions):
#         match image_model_provider:
#             case "google":
#                 gemini_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
#                 image_config = types.GenerateImagesConfig(
#                     number_of_images=1,
#                     aspect_ratio="16:9" if orientation == "landscape" else "9:16",
#                     # add_watermark=False, this is only supported by vertex-ai
#                 )
#                 generated_image_container = gemini_client.models.generate_images(
#                     model="imagen-4.0-ultra-generate-001",
#                     prompt=image_description,
#                     config=image_config,
#                 )
#                 with open(image_paths[index], "wb") as image_file:
#                     image_file.write(generated_image_container.images[0].image_bytes)
#
#             case "openai":
#                 openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
#                 generated_image = openai_client.images.generate(
#                     prompt=image_description,
#                     model="gpt-image-1.5",
#                     quality="high",
#                     size="1536x1024" if orientation == "landscape" else "1024x1536"
#                 )
#                 with open(image_paths[index], "wb") as image_file:
#                     image_file.write(base64.b64decode(generated_image.data[0].b64_json))
#
#             case "flux":
#                 generated_image = asyncio.run(
#                     generate_image_with_flux(prompt=image_description, orientation=orientation))
#                 if generated_image:
#                     with open(image_paths[index], "wb") as image_file:
#                         image_file.write(generated_image)
#

#
#
# def animate_with_motion_effect(
#     image_paths: Path | list[Path],
#     video_path: Path,
#     ideal_image_duration: float,
#     last_image_duration: float,
#     motion_pattern: str | list[str] = "ken_burns",
#     motion_start_index: int = 0,
#     orientation: str = "portrait",
# ):
#     if isinstance(image_paths, Path):
#         image_paths = [image_paths]
#
#     # Make sure motion_pattern is a list
#     if isinstance(motion_pattern, str):
#         motion_pattern = [motion_pattern]
#
#     num_of_images = len(image_paths)
#     fps = 30
#     output_size = "1080x1920" if orientation == "portrait" else "1920x1080"
#     width, height = map(int, output_size.split("x"))
#     total_frames = int(ideal_image_duration * fps)
#     pattern_index = motion_start_index
#     pattern_length = len(motion_pattern)
#
#     zoompan_size = f"{width}x{height}"
#
#     pan_speed = 0.8  # 0.1 = very slow, 0.3 = subtle, 0.5 = medium, 1.0 = full speed
#     zoom_speed = 0.20  # controls zoom intensity
#     rock_speed = 15  # pixel amplitude for rocking
#     kenburns_speed = 120  # px/frame drift; reduce for smoother motion
#
#     motion_styles = {
#         "pan_right": {
#             "z": "1.1",
#             "x": f"(iw - iw/zoom) * {pan_speed} * (on / {total_frames})",
#             "y": "ih/2 - (ih/zoom/2)",
#         },
#         "pan_left": {
#             "z": "1.1",
#             "x": f"(iw - iw/zoom) * {pan_speed} * (1 - on / {total_frames})",
#             "y": "ih/2 - (ih/zoom/2)",
#         },
#         "pan_down": {
#             "z": "1.1",
#             "x": "iw/2 - (iw/zoom/2)",
#             "y": f"(ih - ih/zoom) * {pan_speed} * (on / {total_frames})",
#         },
#         "pan_up": {
#             "z": "1.1",
#             "x": "iw/2 - (iw/zoom/2)",
#             "y": f"(ih - ih/zoom) * {pan_speed} * (1 - on / {total_frames})",
#         },
#
#         "zoom_in": {
#             "z": f"min(1 + on/{total_frames} * {zoom_speed}, 1 + {zoom_speed})",
#             "x": "iw/2 - (iw/zoom/2)",
#             "y": "ih/2 - (ih/zoom/2)",
#         },
#         "zoom_out": {
#             "z": f"max(1 + {zoom_speed} - on/{total_frames} * {zoom_speed}, 1)",
#             "x": "iw/2 - (iw/zoom/2)",
#             "y": "ih/2 - (ih/zoom/2)",
#         },
#
#         "rock_horizontal": {
#             "z": "1.05",
#             "x": f"iw/2-(iw/zoom/2) + sin(on*PI/{fps}*0.5) * {rock_speed}",
#             "y": "ih/2-(ih/zoom/2)",
#         },
#         "rock_vertical": {
#             "z": "1.05",
#             "x": "iw/2-(iw/zoom/2)",
#             "y": f"ih/2-(ih/zoom/2) + sin(on*PI/{fps}*0.5) * {rock_speed}",
#         },
#
#         "ken_burns": {
#             "z": f"1 + on/{total_frames} * {zoom_speed}",
#             "x": f"iw/2-(iw/zoom/2) + on*({kenburns_speed} / {fps})",
#             "y": f"ih/2-(ih/zoom/2) + on*({kenburns_speed} / {fps})",
#         },
#     }
#
#     try:
#         sub_clips = []
#         for index, image_path in enumerate(image_paths):
#             duration = ideal_image_duration if image_path != image_paths[-1] else last_image_duration
#             total_frames_for_clip = int(duration * fps)
#             new_clip = ffmpeg.input(str(image_path), loop=1, t=duration, framerate=fps)
#             new_clip = ffmpeg.input(str(image_path))
#
#             if orientation == "portrait":
#                 # Scale height to 2500 (plenty of buffer for zooming on a 1920 height)
#                 new_clip = new_clip.filter('scale', w=-2, h=2500)
#             else:
#                 # Scale width to 2500 (plenty of buffer for zooming on a 1920 width)
#                 new_clip = new_clip.filter('scale', w=2500, h=-2)
#
#             style = motion_styles[motion_pattern[pattern_index % pattern_length]]
#
#             new_clip = new_clip.filter(
#                 "zoompan",
#                 z=style["z"],
#                 x=style["x"],
#                 y=style["y"],
#                 # d=int(duration * fps),
#                 # d=1, # per-image frames
#                 d=total_frames_for_clip,
#                 fps=fps,
#                 s=zoompan_size,         # force portrait/landscape size
#             )
#
#             pattern_index += 1
#             sub_clips.append(new_clip)
#
#         animated_video_stream = ffmpeg.concat(*sub_clips, v=1, a=0).node[0]
#         outfile = ffmpeg.output(animated_video_stream, str(video_path), vcodec="libx264", pix_fmt="yuv420p")
#         outfile.run()
#         duration_of_created_clip = ffmpeg.probe(str(video_path))["format"]["duration"]
#         duration_desired = (len(image_paths) - 1) * ideal_image_duration + last_image_duration
#         print("Inside animation function.")
#         print(f"Video produced is {duration_of_created_clip} seconds but it should actually be {duration_desired} seconds.")
#         print(f"This function call received num_of_images{len(image_paths)}. \nIdeal_image_duration is {ideal_image_duration}. \nLast image is {last_image_duration}.")
#
#     except ffmpeg.Error as e:
#         error_message = e.stderr.decode() if e.stderr else str(e)
#         raise RuntimeError(f"FFmpeg error while animating {image_paths}: {error_message}")

#
# import ffmpeg
# from pathlib import Path
#
#
def animate_with_motion_effect(
        image_paths: Path | list[Path],
        video_path: Path,
        ideal_image_duration: float,
        last_image_duration: float,
        motion_pattern: str | list[str] = "ken_burns",
        motion_start_index: int = 0,
        orientation: str = "portrait",
):
    if isinstance(image_paths, Path):
        image_paths = [image_paths]

    if isinstance(motion_pattern, str):
        motion_pattern = [motion_pattern]

    # Video settings
    fps = 48 # used to be 120, 48 seems better
    output_size = "1080x1920" if orientation == "portrait" else "1920x1080"

    # Motion speeds
    pan_speed = 0.8
    zoom_speed = 0.17 # used to be 0.20, 0.15 seems better, doesnt zoom in as much, less zoom, less jitter
    rock_speed = 15
    kenburns_speed = 60

    pattern_index = motion_start_index
    pattern_length = len(motion_pattern)

    try:
        sub_clips = []
        for index, image_path in enumerate(image_paths):
            # 1. Determine exact duration and frame count for THIS clip
            duration = ideal_image_duration if image_path != image_paths[-1] else last_image_duration
            total_frames = int(duration * fps)

            # 2. Select the motion pattern
            current_pattern = motion_pattern[pattern_index % pattern_length]

            # 3. Define the formulas dynamically using the CALCULATED total_frames
            # We inject the integer 'total_frames' directly into the string so FFmpeg sees numbers, not variables.
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

            # 4. Create the input stream
            # loop=1 turns the image into a video stream (prevents jitter)
            # t=duration sets the length
            new_clip = ffmpeg.input(str(image_path), loop=1, t=duration, framerate=fps)

            # 5. Pre-scale to high resolution (prevents pixelation during zoom)
            # if orientation == "portrait":
            #     new_clip = new_clip.filter('scale', w=-2, h=3000)
            # else:
            #     new_clip = new_clip.filter('scale', w=3000, h=-2)
            if orientation == "portrait":
                # 2x overscale of 1080x1920
                new_clip = new_clip.filter("scale", 2160, 3840, flags="lanczos")
            else:
                # 2x overscale of 1920x1080
                new_clip = new_clip.filter("scale", 3840, 2160, flags="lanczos")

            # 6. Apply Zoompan
            # d=1 is CRITICAL. It means "produce 1 output frame for 1 input frame".
            # Since our input is already 'total_frames' long (due to loop=1), this matches perfectly.
            new_clip = new_clip.filter(
                "zoompan",
                z=style["z"],
                x=style["x"],
                y=style["y"],
                d=1,
                fps=fps,
                s=output_size
            )

            # 7. Force correct pixel aspect ratio
            new_clip = new_clip.filter("setsar", "1")
            new_clip = new_clip.filter('tmix', frames=3) # wasn't here, makes videos much smoother

            pattern_index += 1
            sub_clips.append(new_clip)

        # Concatenate and Output
        animated_video_stream = ffmpeg.concat(*sub_clips, v=1, a=0).node[0]

        outfile = ffmpeg.output(
            animated_video_stream,
            str(video_path),
            vcodec="libx264",
            pix_fmt="yuv420p",
            r=fps,
            preset="slow" # reduced 150 to 11mb, no brainer
        )
        outfile.run(overwrite_output=True)

        # Verification
        duration_of_created_clip = ffmpeg.probe(str(video_path))["format"]["duration"]
        expected_duration = (len(image_paths) - 1) * ideal_image_duration + last_image_duration
        print(f"Success! Video duration: {duration_of_created_clip}s (Expected: {expected_duration}s)")

    except ffmpeg.Error as e:
        error_message = e.stderr.decode() if e.stderr else str(e)
        raise RuntimeError(f"FFmpeg error while animating: {error_message}")

def extract_topics_form_text(text: str) -> list[str]:
    ai_model_for_topics_container = ai_model.with_structured_output(TopicsContainer)
    ai_message = AIMessage(content=topics_extractor_system_prompt)
    human_message = HumanMessage(content=text)
    messages = [ai_message, human_message]
    topics_container:BaseModel = ai_model_for_topics_container.invoke(messages)
    topics: list[str] = topics_container.topics
    return topics



import asyncio
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
import textwrap


async def pseudo_generate_image(
    image_descriptions: str | list[str],
    image_paths: Path | list[Path],
    image_model_provider: str,
    orientation: str,
):
    """
    Mock image generator for development/testing.
    Creates a black image and writes the image description in white text.

    This function mirrors the real generate_image signature and behavior,
    but does NOT call any external image APIs.
    """

    if isinstance(image_descriptions, str):
        image_descriptions = [image_descriptions]
    if isinstance(image_paths, Path):
        image_paths = [image_paths]

    if len(image_descriptions) != len(image_paths):
        raise ValueError("Image descriptions and image paths must have the same length.")

    print("pseudo_generate_image ran (mock mode)...")

    async def _create_mock_image(
        description: str,
        path: Path,
    ) -> Optional[bytes]:
        # Decide image size based on orientation
        match orientation.lower():
            case "portrait":
                size = (1024, 1792)
            case "landscape":
                size = (1792, 1024)
            case _:
                size = (1024, 1024)

        img = Image.new("RGB", size, color="black")
        draw = ImageDraw.Draw(img)

        # Load default font (safe, no external deps)
        try:
            font = ImageFont.truetype("arial.ttf", 32)
        except Exception:
            font = ImageFont.load_default()

        # Wrap text nicely
        max_chars_per_line = 40
        wrapped_text = textwrap.fill(description, width=max_chars_per_line)

        # Center text
        text_bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        x = (size[0] - text_width) // 2
        y = (size[1] - text_height) // 2

        draw.multiline_text(
            (x, y),
            wrapped_text,
            fill="white",
            font=font,
            align="center",
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, format="PNG")

        return b"mock-image-bytes"

    tasks: list[tuple[int, asyncio.Task[Optional[bytes]]]] = []

    async with asyncio.TaskGroup() as tg:
        for index, description in enumerate(image_descriptions):
            task = tg.create_task(
                _create_mock_image(description, image_paths[index])
            )
            tasks.append((index, task))

    for index, task in tasks:
        result = task.result()
        if not result:
            raise RuntimeError(
                f"Pseudo image generation failed (provider={image_model_provider})."
            )
