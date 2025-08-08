from system_prompts import topic_generation_system_prompt, clip_builder_system_prompt
from openai_client import openai_client, openai_semaphore
from elevenlabs_client import elevenlabs_semaphore, VoiceActor
from utils import extract_json_from_fence, MediaTone, MediaPurpose, MediaPlatform, AspectRatio
from ai_models import ImageModel, VoiceModel
from clip import Clip
import json
from typing import Any, Literal
import asyncio
import moviepy as mvpy
from datetime import datetime
import os

os.makedirs("final_videos", exist_ok=True)
class Video:
    def __init__(self,
                 central_theme: str,
                 purpose: MediaPurpose,
                 target_audience: str,
                 tone: MediaTone,
                 platform: MediaPlatform,
                 length: int,
                 style_reference: str = None,
                 auxiliary_requests: str = None,
                 aspect_ratio: AspectRatio = AspectRatio.PORTRAIT,
                 image_model: ImageModel = ImageModel.OPENAI,
                 voice_model: VoiceModel = VoiceModel.ELEVENLABS,
                 voice_actor: VoiceActor = VoiceActor.AMERICAN_MALE_NARRATOR,
                 ):
        self.central_theme: str = central_theme
        self.purpose: MediaPurpose = purpose
        self.target_audience: str = target_audience
        self.tone: MediaTone = tone
        self.style_reference: str = style_reference
        self.auxiliary_requests: str = auxiliary_requests
        self.platform: MediaPlatform = platform
        self.length: int = length
        self.image_model = image_model
        self.voice_model = voice_model
        self.aspect_ratio: AspectRatio = aspect_ratio
        self.voice_actor = voice_actor


        self.cumulative_script: str = ""
        self.clip_count: int = 0
        self.generated_topics: list[dict[str, Any]]= []
        self.clips: list[Clip]=[]
        self.all_clips_valid: bool = False
        self.final_video_path: str = ""


    def generate_topics(self):
        if not self.central_theme:
            raise Exception("Video theme cannot be None")

        payload = {
            "central_theme": self.central_theme,
            "purpose": self.purpose.value,
            "target_audience": self.target_audience,
            "tone": self.tone.value,
            "auxiliary_requests": self.auxiliary_requests,
            "platform": self.platform.value,
            "length": self.length,
            "style_reference": self.style_reference,
        }

        system_prompt = {"role": "system", "content": topic_generation_system_prompt}
        user_input = {"role": "user", "content": json.dumps(payload)}
        messages = [system_prompt, user_input]
        try:
            ai_response = openai_client.chat.completions.create(
                model="gpt-5",
                messages=messages,
            )
            generated_topics_with_fence = ai_response.choices[0].message.content
        except:
            raise Exception("Generation of topics for the video payload failed.")

        generated_topics: dict = json.loads(extract_json_from_fence(generated_topics_with_fence))
        self.generated_topics = generated_topics.get("topics", [])


    def generate_clip_data(self, topic: str) -> list[dict[str, Any]]:
        payload = {
            "talking_point": topic,
            "cumulative_script": self.cumulative_script,
            "meta": {
                "central_theme": self.central_theme,
                "purpose": self.purpose.value,
                "target_audience": self.target_audience,
                "tone": self.tone.value,
                "auxiliary_requests": self.auxiliary_requests,
                "platform": self.platform.value,
                "length": self.length,
                "style_reference": self.style_reference,
            }
        }

        system_prompt = {"role": "system", "content": clip_builder_system_prompt}
        user_input = {"role": "user", "content": json.dumps(payload)}
        messages = [system_prompt, user_input]

        try:
            ai_response = openai_client.chat.completions.create(
                model="gpt-5",
                messages=messages,
            )
            clip_data_with_fence: str = ai_response.choices[0].message.content
            clip_data: list[dict[str, Any]] = json.loads(extract_json_from_fence(clip_data_with_fence))
            return clip_data
        except Exception as e:
            raise Exception(f"Generation of clip data failed with exception: {e}")



    def generate_clips(self):
        if not self.generated_topics:
            raise Exception("Generation of topics for the video clip data failed.")
        # For each topic, generate the clip data, and create a clip
        for topic in self.generated_topics:
            clips_data_per_topic: list = self.generate_clip_data(topic.get("topic", ""))
            for clip_data in clips_data_per_topic:
                # creating the clip
                self.clip_count += 1
                new_clip = Clip(
                    clip_id=self.clip_count,
                    base_image_description=clip_data.get("base_image_description", ""),
                    clip_duration_sec=int(clip_data.get("clip_duration_sec", "")),
                    tone=self.tone,
                    voice_presence=clip_data.get("voice_presence", ""),
                    voice_script=clip_data.get("voice_script", "empty my boy"),
                    aspect_ratio=self.aspect_ratio,
                    image_model=self.image_model,
                    voice_model=self.voice_model,
                    voice_actor=self.voice_actor,
                )
                # add clip to the videos clips and update the cumulative script
                self.clips.append(new_clip)
                self.cumulative_script += new_clip.voice_script


    @staticmethod
    async def _generate_clips_visuals(clip):
        if clip.image_model == ImageModel.OPENAI:
            async with openai_semaphore:
                await asyncio.to_thread(clip.generate_base_image)

    async def generate_clips_visuals(self):
        if not self.clips:
            raise Exception("Clip visuals cannot be generated without clips.")

        async with asyncio.TaskGroup() as tg:
            for clip in self.clips:
                tg.create_task(self._generate_clips_visuals(clip))

    @staticmethod
    async def _generate_clips_audios(clip):
        async with elevenlabs_semaphore:
            await asyncio.to_thread(clip.generate_voice_over)


    async def generate_clips_audios(self):
        if not self.clips:
            raise Exception("Clip audios cannot be generated without clips.")
        async with asyncio.TaskGroup() as tg:
            for clip in self.clips:
                tg.create_task(self._generate_clips_audios(clip))


    def animate_clips_visuals(self):
        if not self.clips:
            raise Exception("Clip visuals cannot be animated without clips.")
        for clip in self.clips:
            clip.animate_video()

    def merge_clips_audios_and_visuals(self):
        if not self.clips:
            raise Exception("Clips audios and visuals cannot be merged without clips.")
        for clip in self.clips:
            clip.merge_audio_and_visual()

    def validate_clips(self):
        # for a clip to be valid, it must have an animated video path
        if not self.clips:
            raise Exception("Clip cannot be validated without clips.")
        all_clips_valid = True
        for clip in self.clips:
            if not clip.animated_video_path:
                all_clips_valid = False
                break
        self.all_clips_valid = all_clips_valid


    def merge_all_clips(self):
        if not self.all_clips_valid:
            raise Exception("Some clips are not valid and therefore clips cannot be merged.")


        video_clips = [mvpy.VideoFileClip(clip.animated_video_path) for clip in self.clips]
        time_of_creation = datetime.now().strftime("%Y%m%d%H%M%S")
        final_video = mvpy.concatenate_videoclips(video_clips, method="compose")
        final_video_path = os.path.join("final_videos", f"{time_of_creation}.mp4")
        final_video.write_videofile(final_video_path, fps=24, audio=True,
                                   codec='libx264',
                                   audio_codec='aac',
                                   )
        self.final_video_path = final_video_path

    def get_final_video_path(self):
        if not self.final_video_path:
            raise Exception("Final video path cannot be retrieved.")
        return self.final_video_path

    async def generate_video(self):
        print("Generating topics.")
        self.generate_topics()
        print("Finished generating topics.")
        print("-"*25)
        print("Generating clips.")
        self.generate_clips()
        print("Finished generating clips.")
        print("-" * 25)
        print("Generating clip visuals.")
        await self.generate_clips_visuals()
        print("Finished generating clip visuals.")
        print("-" * 25)
        print("Generating audio clips.")
        await self.generate_clips_audios()
        print("Finished generating audio clips.")
        print("-" * 25)
        print("Animating clip Visuals.")
        self.animate_clips_visuals()
        print("Finished animating clip Visuals.")
        print("-" * 25)
        print("Merging clip audio and visuals")
        self.merge_clips_audios_and_visuals()
        print("Finished merging clip audio and visuals.")
        print("-" * 25)
        print("Validating clips.")
        self.validate_clips()
        print("Finished validating clips.")
        print("-" * 25)
        print("Merging all clips.")
        self.merge_all_clips()
        print("Finished merging all clips.")
        print("-" * 25)
        print(f"Final Video path {self.get_final_video_path()}")

    #  for interface
    def re_do_clip_action(self, clip_id: int, action: Literal["base_image", "audio", "animate"]):
        print("redo ran")
        if clip_id > self.clip_count or clip_id < 0:
            raise Exception("Clip id is out of range.")

        clip_index = clip_id - 1
        match action:
            case "base_image":
                self.clips[clip_index].generate_base_image()
                print("ran base image")
            case "audio":
                self.clips[clip_index].generate_voice_over()
                print("ran audio")
            case "animate":
                self.clips[clip_index].merge_audio_and_visual()
                print("ran animate")


    def clips_summary(self):
        valid_clips = []
        invalid_clips = []
        for clip in self.clips:
            if clip.animated_video_path and os.path.isfile(clip.animated_video_path):
                valid_clips.append(clip.clip_id)
            else:
                invalid_clips.append(clip.clip_id)
        return valid_clips, invalid_clips


