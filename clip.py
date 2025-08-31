import base64
import uuid
import os
import json
import asyncio
from typing import Literal

import moviepy as mvpy
# from pydub.utils import mediainfo
from math import ceil

from pydub.utils import mediainfo

from ai_models import ImageModel, VoiceModel, ModelProvider
from ai_clients.openai_client import openai_client, openai_semaphore
from ai_clients.elevenlabs_client import elevenlabs_client, VoiceActor
from ai_clients.gemini_client import gemini_client
from google.genai.types import GenerateImagesConfig
from utils import MediaTone, AspectRatio, extract_json_from_fence, ImageStyle, invoke_llm
from system_prompts import base_image_descriptions_generator_system_prompt

os.makedirs("base_images", exist_ok=True)
os.makedirs("voice_over_audios", exist_ok=True)
os.makedirs("video_with_audio_clips", exist_ok=True)
os.makedirs("animated_videos", exist_ok=True)

class Clip:
    def __init__(
            self,
            clip_id: int,
            tone: MediaTone,
            previous_clip_voice_script: str | None,
            voice_script: str,
            voice_script_enhanced_for_audio_generation: str,
            next_clip_voice_script: str | None,
            aspect_ratio: AspectRatio,
            model_provider: ModelProvider,
            image_model: ImageModel,
            voice_model: VoiceModel,
            voice_actor: VoiceActor,


            # Default values,
            should_animate: bool = False,
            image_style: ImageStyle = ImageStyle.CARTOON,
            desired_clip_duration_seconds: int = 4,
            use_enhanced_script_for_audio_generation: bool = True,

            # To be declared by clip via function calls within clip class

            voice_over_audio_path: str | None = None,
            animated_video_path: str | None = None,
            sub_clip_count: int  | None = None,
            last_sub_clip_length: float | None = None,
            # separated because their default values should be list and mutable objects shouldn't be used as default values as per python documentation.
            base_image_descriptions: list | None = None,
            base_image_paths: list | None = None,


    ):
        if base_image_paths is None:
            base_image_paths = []
        if base_image_descriptions is None:
            base_image_descriptions = []
        self.clip_id: int = clip_id
        self.base_image_descriptions: list[str] = base_image_descriptions
        self.desired_clip_duration_seconds: int = desired_clip_duration_seconds
        self.tone: MediaTone = tone
        self.previous_clip_voice_script: str | None = previous_clip_voice_script
        self.voice_script: str = voice_script
        self.voice_script_enhanced_for_audio_generation = voice_script_enhanced_for_audio_generation
        self.next_clip_voice_script: str | None = next_clip_voice_script
        self.base_image_paths: list[str] = base_image_paths
        self.voice_over_audio_path: str = voice_over_audio_path
        self.animated_video_path = animated_video_path
        self.aspect_ratio: AspectRatio = aspect_ratio
        self.model_provider: ModelProvider = model_provider
        self.image_model: ImageModel = image_model
        self.voice_model: VoiceModel = voice_model
        self.voice_actor: VoiceActor = voice_actor
        self.should_animate: bool = should_animate
        self.image_style: ImageStyle = image_style
        self.sub_clip_count: int = sub_clip_count
        self.last_sub_clip_duration: float = last_sub_clip_length
        self.use_enhanced_script_for_audio_generation = use_enhanced_script_for_audio_generation

        # Default Values
        self.voice_over_start_time: float | None = None
        self.voice_over_end_time: float | None = None
        self.duration_seconds: float = 0
        self.desired_sub_clip_duration_seconds: float = 4
        self.compromised_sub_clip_duration_seconds: float = 3


    def _generate_image_with_openai(self, base_image_description: str) -> None:
        generated_image_data = openai_client.images.generate(
            model="gpt-image-1",
            prompt=f"{base_image_description}",
            output_format="png",
            quality="medium",
            size="1536x1024" if self.aspect_ratio == AspectRatio.LANDSCAPE else "1024x1536",
        )

        base_image_path = os.path.join("base_images", uuid.uuid4().hex + ".png")
        self.base_image_paths.append(base_image_path)
        with open(base_image_path, "wb") as image_file:
            image_file.write(base64.b64decode(generated_image_data.data[0].b64_json))


    def _generate_image_with_gemini(self, base_image_description: str) -> None:
        generated_base_image = gemini_client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=base_image_description,
            config=GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9" if self.aspect_ratio == AspectRatio.LANDSCAPE else "9:16",
                image_size="2K"
            ),
        )
        base_image_path = os.path.join("base_images", uuid.uuid4().hex + ".png")
        self.base_image_paths.append(base_image_path)
        with open(base_image_path, "wb") as image_file:
            image_file.write(generated_base_image.images[0].image_bytes)


    def generate_base_images(self):
        """
        Generates Image to be used as a base for a clip.
        Args:
            self (Clip): The Clip object.
        Returns:
            None
        """
        print(f"Generating base image for clip: {self.clip_id}")
        print(f"Base Image Descriptions for clip: {self.clip_id}: {self.base_image_descriptions}")
        if not self.base_image_descriptions:
            print("!!!!!!!!No base image descriptions provided.!!!!!!!!")
            self.base_image_descriptions = ["A cartoonish illustration of a futuristic classroom where AI technology integrates seamlessly with human teaching. In the foreground, a friendly robot assists a teacher, who is smiling and engaging with a diverse group of students. The background shows various tech devices displaying educational content. The colors are bright and high-contrast, creating a fun and approachable atmosphere. The scene is framed with a slight upward angle, emphasizing innovation and a positive future."]

            # raise Exception(f"base_image_descriptions cannot be None")

        for base_image_description in self.base_image_descriptions:

            try:
                match self.image_model:
                    case ImageModel.OPENAI:
                        self._generate_image_with_openai(base_image_description)
                    case ImageModel.GEMINI:
                        self._generate_image_with_gemini(base_image_description)

            except Exception as e:
                raise Exception(f"Failed to generate base image due to the following Error: {e}")
            print(f"Base image generated for clip: {self.clip_id}")


    def _generate_voice_over_with_elevenlabs(self):
        print(f"Generating voice over for clip: {self.clip_id}")
        voice_over_data = elevenlabs_client.text_to_speech.convert(
            voice_id=self.voice_actor.value,
            output_format="mp3_44100_128",
            previous_text=self.previous_clip_voice_script,
            text=self.voice_script,
            next_text=self.next_clip_voice_script,
            model_id="eleven_multilingual_v2",
        )
        self.voice_over_audio_path = os.path.join("voice_over_audios", uuid.uuid4().hex + ".mp3")
        with open(self.voice_over_audio_path, "wb") as audio_file:
            for chunk in voice_over_data:
                if chunk:
                    audio_file.write(chunk)
        print(f"Voice over generated for clip: {self.clip_id}")


    def generate_voice_over(self):
        if not self.voice_script:
            self.voice_script = "temporary_voice_script"
            raise Exception(f"voice_script cannot be None")
        try:
            match self.voice_model:
                case VoiceModel.ELEVENLABS:
                    self._generate_voice_over_with_elevenlabs()
        except Exception as e:
            raise Exception(f"Failed to generate voice over due to the following Error: {e}")

        # after the voiceover has been created, determine how many clips will be needed to for the clip
        length_of_audio = self.get_voice_over_length()
        # sub_clips_time_remainder = length_of_audio % self.desired_sub_clip_duration_seconds
        # sub_clip_count = length_of_audio // self.desired_sub_clip_duration_seconds
        # # if the remainder after  all subclips(of length 3s) is greater than 2, make a new sub clip
        # if sub_clips_time_remainder > self.compromised_sub_clip_duration_seconds:
        #     self.last_sub_clip_duration = sub_clips_time_remainder
        #     self.sub_clip_count = sub_clip_count + 1
        # # if not, add it to the last clip
        # else:
        #     self.last_sub_clip_duration = self.desired_sub_clip_duration_seconds + sub_clips_time_remainder
        #     self.sub_clip_count = sub_clip_count

        self.duration_seconds = length_of_audio



    def get_voice_over_length(self) -> float:
        if not self.voice_over_audio_path:
            raise Exception(f"voice_over_audio_path cannot be None")
        info = mediainfo(self.voice_over_audio_path)
        return ceil(float(info['duration']))


    def animate_visuals(self,  audio_generation_method: Literal["one-shot", "multi-shot"] = "one-shot"):
        if not self.base_image_descriptions:
            raise Exception(f"Cannot animate clip visuals if base_image_descriptions is None")

        all_sub_clip_paths = []
        animated_video_path = ""
        for index, sub_clip_image_path in enumerate(self.base_image_paths):
            # as long as we are not at the last clip, clip duration is `desired_sub_clip_duration_seconds` seconds long
            if not (index == self.sub_clip_count - 1):
                sub_clip_video = mvpy.ImageClip(sub_clip_image_path, duration=self.desired_sub_clip_duration_seconds)
            else:
                sub_clip_video = mvpy.ImageClip(sub_clip_image_path, duration=self.last_sub_clip_duration)

            animated_sub_clip_path = os.path.join("animated_videos", uuid.uuid4().hex + ".mp4")
            sub_clip_video.write_videofile(animated_sub_clip_path, fps=24)
            all_sub_clip_paths.append(animated_sub_clip_path)


        #  once all sub clips have been created and are in all_sub_clip_paths, merge them
        all_sub_clips = [mvpy.VideoFileClip(sub_clip_path) for sub_clip_path in all_sub_clip_paths]
        animated_video = mvpy.concatenate_videoclips(all_sub_clips, method="compose")
        animated_video_path = os.path.join("animated_videos", uuid.uuid4().hex + ".mp4")


        match audio_generation_method:
            # for one-shot audio, just save the video
            case "one-shot":
                animated_video.write_videofile(animated_video_path, fps=24, audio=True, codec='libx264', audio_codec='aac')

            # for multi-shot audio, add the audio then save
            case "multi-shot":
                if not self.voice_over_audio_path:
                    raise Exception(
                        f"Cannot animate clip visuals if voice_over_audio_path is None and audio_generation_method is 'multi-shot'")
                audio_clip = mvpy.AudioFileClip(self.voice_over_audio_path)
                animated_video = animated_video.with_audio(audio_clip)
                animated_video.write_videofile(animated_video_path, fps=24, audio=True,
                                               codec='libx264',
                                               audio_codec='aac',
                                               )

        self.animated_video_path = animated_video_path
        print(f"Animated Video path for clip: {self.clip_id} is {self.animated_video_path} and its duration is {self.duration_seconds}")


    async def generate_base_image_descriptions(self, full_script: str="", auxiliary_image_requests: str = ""):
        # When audio is generated, either one shot or multi shot, the `duration_seconds` attribute is populated
        # this can be used to derive the sub clip count and the `last_sub_clip_duration`
        if not self.duration_seconds:
            raise Exception(f"duration_seconds cannot be None")

        sub_clip_count = self.duration_seconds // self.desired_sub_clip_duration_seconds
        sub_clips_time_remainder = self.duration_seconds % self.desired_sub_clip_duration_seconds
        # if the time remainder after all subclips (of duration `desired_sub_clip_duration_seconds`)
        # is greater than the duration of `compromised_sub_clip_duration_seconds`, make a new sub clip
        # with duration `compromised_sub_clip_duration_seconds`
        if sub_clips_time_remainder > self.compromised_sub_clip_duration_seconds:
            self.last_sub_clip_duration = sub_clips_time_remainder
            self.sub_clip_count = sub_clip_count + 1
        # if not, add the remaining time to the last sub clip
        else:
            self.last_sub_clip_duration = self.desired_sub_clip_duration_seconds + sub_clips_time_remainder
            self.sub_clip_count = sub_clip_count

        # for debugging purposes
        print(f"Clip {self.clip_id} should have {self.sub_clip_count} subclips")
        print(f"Last subclip length should be: {self.last_sub_clip_duration}")

        payload = {
            "clip_voice_script": self.voice_script,
            "full_script": full_script,
            "image_style": self.image_style.value,
            "auxiliary_image_requests": auxiliary_image_requests,
            "num_of_sub_clips": self.sub_clip_count if self.sub_clip_count > 0 else 1,
        }

        system_prompt = {"role": "system", "content": base_image_descriptions_generator_system_prompt}
        user_input = {"role": "user", "content": json.dumps(payload)}
        messages: list[dict[str, str]] = [system_prompt, user_input]
        clip_base_image_descriptions = []
        async with openai_semaphore:
            clip_base_image_descriptions = await asyncio.to_thread(self._generate_base_image_descriptions, messages)

        self.base_image_descriptions = clip_base_image_descriptions
        print(f"Finished generating base image description for clip: {self.clip_id}")


    @staticmethod
    def _generate_base_image_descriptions(messages: list[dict[str, str]]) -> list[str]:
        ai_response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )
        clip_base_image_descriptions_with_fence = ai_response.choices[0].message.content

        clip_base_image_descriptions: list[str] = json.loads(
            extract_json_from_fence(clip_base_image_descriptions_with_fence)).get("base_image_descriptions")
        print("-" * 10)
        print(clip_base_image_descriptions)
        return clip_base_image_descriptions




    def merge_audio_and_visuals(self):
        if not self.animated_video_path  or not self.voice_over_audio_path:
            raise Exception(f"animated_video_path or voice_over_audio_path cannot be None")

        try:
            video_clip = mvpy.VideoFileClip(self.animated_video_path)
            audio_clip = mvpy.AudioFileClip(self.voice_over_audio_path)
            video_with_audio_clip = video_clip.with_audio(audio_clip)

            video_with_audio_clip_path = os.path.join("video_with_audio_clips", uuid.uuid4().hex + ".mp4")
            video_with_audio_clip.write_videofile(video_with_audio_clip_path, fps=24, audio=True,
                                       codec='libx264',
                                       audio_codec='aac',
                                       )
            self.animated_video_path = video_with_audio_clip_path
        except Exception as e:
            raise Exception(f"Failed to merge audio and visuals due to the following Error: {e}")

    # functions for interface
    def is_valid(self):
        return bool(self.animated_video_path) and os.path.isfile(self.animated_video_path)










    async def enhance_script_for_audio_generation(self, audio_generation_model: Literal["elevenlabs_v2", "elevenlabs_v3"] = "elevenlabs_v2"):
        try:
            payload = json.dumps({"script_text": self.voice_script})
            llm_response = invoke_llm(user_input=payload, system_instruction="", model_provider=self.model_provider)
        except Exception as e:
            raise Exception(f"Failed to enhance script due to the following Error: {e}")



        # ai_response = openai_client.chat.completions.create(
        #     model="gpt-4o",
        #     messages=messages,
        # )
        #
        # clip_base_image_description_with_fence = ai_response.choices[0].message.content
        # clip_base_image_description: str = json.loads(
        #     extract_json_from_fence(clip_base_image_description_with_fence)).get("base_image_description")
        #
        # self.base_image_description = clip_base_image_description
        #

        # async def generate_base_image_description_one_shot_audio(self, full_enhanced_script: str = "", auxiliary_image_requests: str = ""):
        #     print(f"Generating base image description for clip: {self.clip_id}")
        #     if not self.voice_script:
        #         raise Exception(f"voice_script cannot be None")
        #
        #     duration = self.voice_over_end_time - self.voice_over_start_time
        #     print(f"Duration for clip {self.clip_id}: {duration}")
        #
        #     ######################## for one shot, I added duration in house and finding the clip count in house
        #     sub_clip_count = duration // 4
        #     sub_clips_time_remainder = duration % 4
        #     # if the remainder after  all subclips(of length 3s) is greater than 2, make a new sub clip
        #     if sub_clips_time_remainder > 3:
        #         self.last_sub_clip_duration = sub_clips_time_remainder
        #         self.sub_clip_count = sub_clip_count + 1
        #     # if not, add it to the last clip
        #     else:
        #         self.last_sub_clip_duration = 4 + sub_clips_time_remainder
        #         self.sub_clip_count = sub_clip_count
        #     print(f"Clip {self.clip_id} should have {self.sub_clip_count} subclips")
        #     print(f"Last subclip length should be: {self.last_sub_clip_duration}")
        #
        #     payload = {
        #         "clip_voice_script": self.voice_script,
        #         "full_script": full_enhanced_script,
        #         "image_style": self.image_style.value,
        #         "auxiliary_image_requests": auxiliary_image_requests,
        #         "num_of_sub_clips": self.sub_clip_count if self.sub_clip_count > 0 else 1,
        #     }
        #     system_prompt = {"role": "system", "content": base_image_descriptions_generator_system_prompt}
        #     user_input = {"role": "user", "content": json.dumps(payload)}
        #     messages: list[dict[str, str]] = [system_prompt, user_input]
        #     clip_base_image_descriptions = []
        #     async with openai_semaphore:
        #         clip_base_image_descriptions = await asyncio.to_thread(self._generate_base_image_descriptions, messages)
        #
        #     self.base_image_descriptions = clip_base_image_descriptions
        #     print(f"Finished generating base image description for clip: {self.clip_id}")
        #
        #
        #



    # def animate_video_multi_shot_audio(self):
    #     if not self.base_image_paths:
    #         raise Exception(f"base_image_paths cannot be None")
    #     all_sub_clip_paths = []
    #     for index, sub_clip_image_path in enumerate(self.base_image_paths):
    #         # as long as we are not at the last clip, duration is 3 seconds
    #         if not (index == self.sub_clip_count-1):
    #             sub_clip_video = mvpy.ImageClip(sub_clip_image_path, duration=4)
    #         else:
    #             sub_clip_video = mvpy.ImageClip(sub_clip_image_path, duration=self.last_sub_clip_duration)
    #
    #         animated_sub_clip_path = os.path.join("animated_videos", uuid.uuid4().hex + ".mp4")
    #         sub_clip_video.write_videofile(animated_sub_clip_path, fps=24)
    #         all_sub_clip_paths.append(animated_sub_clip_path)
    #
    #     #  all sub clips have been created and are in all_sub_clip_paths, merge them
    #     all_sub_clips = [mvpy.VideoFileClip(sub_clip_path) for sub_clip_path in all_sub_clip_paths]
    #     animated_video = mvpy.concatenate_videoclips(all_sub_clips, method="compose")
    #     animated_video_path = os.path.join("animated_videos", uuid.uuid4().hex + ".mp4")
    #     animated_video.write_videofile(animated_video_path, fps=24, audio=True, codec='libx264', audio_codec='aac')
    #     self.animated_video_path = animated_video_path
    #     print(f"Animated Video path for clip: {self.clip_id} is {self.animated_video_path} and its duration is {self.voice_over_end_time - self.voice_over_start_time}")
    #
    #     # clip_video = mvpy.ImageClip(self.base_image_path, duration=audio_length,)
        #
        # animated_video_path = os.path.join("animated_videos", uuid.uuid4().hex + ".mp4")
        # clip_video.write_videofile(animated_video_path, fps=24)
        # self.animated_video_path = animated_video_path








###### if i add veo, clips will simply have a should animate bpplean. if true, it generated base image description will change and its animate_visuals will change. thats reall it.