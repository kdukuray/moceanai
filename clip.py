import base64
import uuid
import os

import moviepy as mvpy
# from pydub.utils import mediainfo
from math import ceil

from ai_models import ImageModel, VoiceModel
from openai_client import openai_client
from elevenlabs_client import elevenlabs_client, VoiceActor
from utils import MediaTone, AspectRatio

os.makedirs("base_images", exist_ok=True)
os.makedirs("voice_over_audios", exist_ok=True)
os.makedirs("video_with_audio_clips", exist_ok=True)
os.makedirs("animated_videos", exist_ok=True)

class Clip:
    def __init__(
            self,
            clip_id: int,
            base_image_description: str,
            clip_duration_sec: int,
            tone: MediaTone,
            voice_presence: str,
            voice_script: str,
            aspect_ratio: AspectRatio,
            image_model: ImageModel,
            voice_model: VoiceModel,
            voice_actor: VoiceActor,
            # Default values
            # To be declared by clip via function calls within clip class
            base_image_path: str = None,
            voice_over_audio_path: str = None,
            animated_video_path: str = None,


    ):
        self.clip_id = clip_id
        self.base_image_description = base_image_description
        self.clip_duration_sec = clip_duration_sec
        self.tone = tone
        self.voice_presence = voice_presence
        self.voice_script = voice_script
        self.base_image_path = base_image_path
        self.voice_over_audio_path = voice_over_audio_path
        self.animated_video_path = animated_video_path
        self.aspect_ratio = aspect_ratio
        self.image_model = image_model
        self.voice_model = voice_model
        self.voice_actor = voice_actor


    def _generate_image_with_openai(self):
        generated_image_data = openai_client.images.generate(
            model="gpt-image-1",
            prompt=self.base_image_description,
            output_format="png",
            quality="medium",
            size="1536x1024" if self.aspect_ratio == AspectRatio.LANDSCAPE else "1024x1536",
        )

        self.base_image_path = os.path.join("base_images", uuid.uuid4().hex + ".png")
        with open(self.base_image_path, "wb") as image_file:
            image_file.write(base64.b64decode(generated_image_data.data[0].b64_json))




    def _generate_image_with_gemini(self):
        pass

    def generate_base_image(self):
        """
        Generates Image to be used as a base for a clip.
        Args:
            self (Clip): The Clip object.
        Returns:
            None
        """
        print(f"Generating base image for clip: {self.clip_id}")
        if not self.base_image_description:
            raise Exception(f"base_image_description cannot be None")

        try:
            match self.image_model:
                case ImageModel.OPENAI:
                    self._generate_image_with_openai()
                case ImageModel.GEMINI:
                    self._generate_image_with_gemini()


        except Exception as e:
            raise Exception(f"Failed to generate base image due to the following Error: {e}")
        print(f"Base image generated for clip: {self.clip_id}")


    def _generate_voice_over_with_elevenlabs(self):
        print(f"Generating voice over for clip: {self.clip_id}")
        voice_over_data = elevenlabs_client.text_to_speech.convert(
            voice_id=self.voice_actor.value,
            output_format="mp3_44100_128",
            text=self.voice_script,
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



    def get_voice_over_length(self) -> float:
        return float(self.clip_duration_sec)

    def animate_video(self):
        if not self.base_image_path:
            raise Exception(f"base_image_path cannot be None")
        audio_length = self.get_voice_over_length()
        clip_video = mvpy.ImageClip(self.base_image_path, duration=audio_length)

        animated_video_path = os.path.join("animated_videos", uuid.uuid4().hex + ".mp4")
        clip_video.write_videofile(animated_video_path, fps=24)
        self.animated_video_path = animated_video_path


    def merge_audio_and_visual(self):
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




