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


class TopicsContainer(BaseModel):
    topics: list[str] = Field(..., description="List of topic extracted from the text.")

ai_model = init_chat_model(model_provider="google-genai", model="gemini-2.5-pro")

# Enums
model_providers = Literal["google", "openai", "claude", "xai", "deepseek"]
image_models = Literal["google", "openai"]
image_styles = Literal[
    "Photo Realism",
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
    "american_female_media_influencer_2"
]

def get_video_duration(video_path: str) -> float:
    """Get duration of video file in seconds."""
    try:
        probe = ffmpeg.probe(video_path)
        duration = float(probe['format']['duration'])
        return duration
    except ffmpeg.Error as e:
        print(f"Error probing video file: {e.stderr.decode()}")
        return 0.0


def generate_image(image_descriptions: str | list[str], image_paths: Path | list[Path], image_model_provider: str, orientation: str):
    if isinstance(image_descriptions, str):
        image_descriptions = [image_descriptions]
    if isinstance(image_paths, Path):
        image_paths = [image_paths]

    if len(image_descriptions) != len(image_paths):
        raise ValueError("Image descriptions and image paths must have the same length.")

    for index, image_description in enumerate(image_descriptions):
        match image_model_provider:
            case "google":
                gemini_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
                image_config = types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="16:9" if orientation == "landscape" else "9:16",
                    # add_watermark=False, this is only supported by vertex-ai
                )
                generated_image_container = gemini_client.models.generate_images(
                    model="imagen-4.0-ultra-generate-001",
                    prompt=image_description,
                    config=image_config,
                )
                with open(image_paths[index], "wb") as image_file:
                    image_file.write(generated_image_container.images[0].image_bytes)

            case "openai":
                openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
                generated_image = openai_client.images.generate(
                    prompt=image_description,
                    model="gpt-image-1",
                    quality="low",
                    size="1536x1024" if orientation == "landscape" else "1024x1536"
                )
                with open(image_paths[index], "wb") as image_file:
                    image_file.write(base64.b64decode(generated_image.data[0].b64_json))

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
    fps = 120
    output_size = "1080x1920" if orientation == "portrait" else "1920x1080"

    # Motion speeds
    pan_speed = 0.8
    zoom_speed = 0.20
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
            if orientation == "portrait":
                new_clip = new_clip.filter('scale', w=-2, h=3000)
            else:
                new_clip = new_clip.filter('scale', w=3000, h=-2)

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
            preset="fast"
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

