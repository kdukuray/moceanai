# default python packages
import os
import uuid
import base64
from datetime import datetime
import json
from typing import Any, Literal, Optional
import asyncio

# downloaded modules
import moviepy as mvpy

# local modules
from system_prompts import (
    one_shot_script_generation_system_prompt,
    short_form_video_goal_generation_system_prompt,
    short_form_video_hook_generation_system_prompt,
    short_form_video_talking_point_generation_system_prompt,
    multi_shot_script_generation_system_prompt,
    multi_shot_script_polishing_system_prompt,
    script_to_script_list_system_prompt,
    eleven_v3_audio_enhancer_system_prompt,
    eleven_v2_audio_enhancer_system_prompt
)
from ai_clients.openai_client import openai_semaphore
from ai_clients.gemini_client import gemini_semaphore
from ai_clients.elevenlabs_client import elevenlabs_semaphore, VoiceActor, elevenlabs_client
from ai_models import ImageModel, VoiceModel, ModelProvider
from clip import Clip
from errors import AppError, MissingDataError, FailedGenerationError, FailedParsingError
from utils import extract_json_from_fence, MediaTone, MediaPurpose, MediaPlatform, AspectRatio, ImageStyle, invoke_llm

# Makes sure the directories needed to store permanent and temporary media exists
required_directories = ["final_videos", "base_images", "animated_videos", "voice_over_audios", "clip_video_with_audios"]
for directory in required_directories:
    os.makedirs(os.path.join(os.getcwd(), directory), exist_ok=True)


class ShortFormVideo:
    def __init__(self,
                 topic: str,
                 purpose: MediaPurpose,
                 target_audience: str,
                 tone: MediaTone,
                 duration_seconds: int,

                 # default values
                 # changed frequently
                 auxiliary_requests: Optional[str] = None,
                 model_provider: ModelProvider = ModelProvider.OPENAI,
                 image_model: ImageModel = ImageModel.OPENAI,
                 animation_probability: int = 0,
                 image_style: ImageStyle = ImageStyle.CARTOON,
                 voice_actor: VoiceActor = VoiceActor.AMERICAN_MALE_NARRATOR,
                 max_retries: int = 3,
                 auxiliary_image_requests: str = "",
                 use_enhanced_script_for_audio_generation: bool = True,
                 # not changed frequently
                 style_reference: Optional[str] = None,
                 platform: MediaPlatform = MediaPlatform.INSTAGRAM_TIKTOK,
                 aspect_ratio: AspectRatio = AspectRatio.PORTRAIT,
                 voice_model: VoiceModel = VoiceModel.ELEVENLABS,

                 ):

        self.topic: str = topic
        self.purpose: MediaPurpose = purpose
        self.target_audience: str = target_audience
        self.tone: MediaTone = tone
        self.duration_seconds: int = duration_seconds

        # attributes with defaults
        # changed frequently
        self.auxiliary_requests: str = auxiliary_requests
        self.model_provider: ModelProvider = model_provider
        self.image_model = image_model
        self.animation_probability: int = animation_probability
        self.image_style: ImageStyle = image_style
        self.voice_actor = voice_actor
        self.auxiliary_image_requests: str = auxiliary_image_requests
        self.use_enhanced_script_for_audio_generation: bool = use_enhanced_script_for_audio_generation
        # not changed frequently
        self.style_reference: str = style_reference     # usually kept blank
        self.platform: MediaPlatform = platform         # Instagram and Tiktok are usually implied as short form content
        self.aspect_ratio: AspectRatio = aspect_ratio   # Short form content is usually in portrait orientation
        self.voice_model = voice_model                  # voice model is elevenlabs by default (best voice model available)
        self.max_retries: int = max_retries

        # attributes to be used by class methods
        # for media generation
        self.cumulative_script: str = ""
        self.clip_count: int = 0
        self.generated_talking_points: list[dict[str, Any]] = []
        self.clips: list[Clip] = []
        self.script_list: list[str] = []
        self.audio_enhanced_script_list: list[str] = []
        self.goal: str = ""
        self.hook: str = ""
        self.one_shot_audio_voice_over_characters: list[str] | None = None
        self.one_shot_audio_voice_over_start_times_seconds: list[float] | None = None
        self.one_shot_audio_voice_over_end_times_seconds: list[float] | None = None
        self.one_shot_audio_file_path = ""

        # for media access inspection
        self.all_clips_valid: bool = False
        self.final_video_path: str = ""


    # Generation Methods
    def generate_goal(self):
        """
        This function generates the main goal of the video using the target audience, topic and purpose of the video.
        The goal is a sentence describing the angle that the video is taking and what the video intends to achieve.
        This goal is stored as a string in the video object's `goal` attribute.
        Returns:
            None
        """
        print("[Starting] Generating goal from target audience, tone and topic....")
        required_fields = [
            "topic",
            "purpose",
            "target_audience",
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to generate goal.")

        payload = json.dumps({
            "topic": self.topic,
            "purpose": self.purpose.value,
            "target_audience": self.target_audience,
        })
        try:
            llm_response = invoke_llm(user_input=payload, system_instruction=short_form_video_goal_generation_system_prompt,
                                      model_provider=self.model_provider)
        except Exception as e:
            raise FailedGenerationError(f"Failed to generate goal because of: {e}")

        try:
            generated_goal = json.loads(extract_json_from_fence(llm_response)).get("goal")
        except Exception as e:
            raise FailedParsingError(f"Failed to parse goal data from json because of: {e}")
        self.goal = generated_goal
        print("[Complete] Generated goal....\n")


    def generate_hook(self):
        """
        This function generates the hook of the video using the information on the video object.
        The hook is the opener to the video and the most important line in short form content.
        This hook is stored as a string in the video object's `hook` attribute.
        Returns:
            None
        """
        print("[Starting] Generating hook from Video data...")
        required_fields = [
            "topic",
            "purpose",
            "target_audience",
            "tone",
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to generate hook.")

        payload = json.dumps({
            "topic": self.topic,
            "purpose": self.purpose.value,
            "target_audience": self.target_audience,
            "tone": self.tone.value,
            "platform": "Instagram and Tiktok",
        })
        try:
            llm_response = invoke_llm(user_input=payload, system_instruction=short_form_video_hook_generation_system_prompt,
                                  model_provider=self.model_provider)
        except Exception as e:
            raise FailedGenerationError(f"Failed to generate hook because of {e}:")

        try:
            generated_hook = json.loads(extract_json_from_fence(llm_response)).get("hook")
        except Exception as e:
            raise FailedParsingError(f"Failed to parse hook data from json because of: {e}")

        self.hook = generated_hook
        print("[Complete] Generated hook....\n")


    def generate_talking_points(self):
        """
        This function generates the talking points of the video using the information on the video object.
        The talking points are stored as a list of strings in the video object's `generated_talking_points` attribute.
        Returns:
            None
        """
        print("[Starting] Generating talking points from video data...")
        required_fields = [
            "topic",
            "purpose",
            "target_audience",
            "tone",
            "goal",
            "hook",
            "duration_seconds",
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to generate talking points.")

        payload = json.dumps({
            "topic": self.topic,
            "purpose": self.purpose.value,
            "goal": self.goal,
            "hook": self.hook,
            "target_audience": self.target_audience,
            "tone": self.tone.value,
            "duration_seconds": self.duration_seconds,
            "auxiliary_requests": self.auxiliary_requests,
        })

        try:
            llm_response = invoke_llm(user_input=payload, system_instruction=short_form_video_talking_point_generation_system_prompt, model_provider=self.model_provider)
        except Exception as e:
            raise FailedGenerationError(f"Failed to generate talking points because of {e}")

        try:
            generated_talking_points: dict = json.loads(extract_json_from_fence(llm_response)).get("talking_points", [])
        except Exception as e:
            raise FailedParsingError(f"Failed to parse talking points data from json because of: {e}")
        self.generated_talking_points = generated_talking_points
        print("[Complete] Generated talking points.....\n")


    def enhance_script_for_audio_generation(self, raw_script: str, audio_generation_model: Literal["elevenlabs_v2", "elevenlabs_v3"] = "elevenlabs_v3") -> str:
        """
        This function enhances the script for the audio generation of the video.
        Parameters:
            raw_script(str): The raw script to be enhanced.
            audio_generation_model(str): The audio generation model to be used. Currently only supports
            `elevenlabs_v2` and `elevenlabs_v3`.`
        Returns:
            str: The enhanced version of the script for audio generation.
        """
        print("[Starting] Enhancing script for audio generation...")
        enhanced_script = ""
        payload = json.dumps({
            "raw_script": raw_script,
        })
        system_prompt: str = ""
        match audio_generation_model:
            case "elevenlabs_v2":
                system_prompt = eleven_v2_audio_enhancer_system_prompt
            case "elevenlabs_v3":
                system_prompt = eleven_v3_audio_enhancer_system_prompt
        try:
            llm_response = invoke_llm(user_input=payload, system_instruction=system_prompt, model_provider=self.model_provider)
        except Exception as e:
            raise FailedGenerationError(f"Failed to enhance script because of: {e}")

        try:
            audio_enhanced_script: str = json.loads(extract_json_from_fence(llm_response)).get("enhanced_script")
        except Exception as e:
            raise FailedParsingError(f"Failed to parse enhanced script data from json because of: {e}")
        print("[Complete] Enhanced script for audio generation.....\n")
        return audio_enhanced_script


    def split_scripts_into_script_lists(self, raw_script: str, audio_enhanced_script: str) -> list[dict[str, str]]:
        """
        Takes the cumulative script and the version of the script that was enhanced for audio generation, splits
        them into cohesive and logically separated script lists.
        Parameters:
            raw_script (str): The full script generated.
            audio_enhanced_script (str): The enhanced version of the script for audio generation.
        Returns:
            list[dict[str, str]]: The cohesive and logically separated script lists. The list is a list of dictionaries.
            Each dictionary has the following keys: `script_segment` and `audio_enhanced_script_segment`.
        """
        print("[Starting] Splitting scripts...")
        payload = json.dumps({"raw_script": raw_script, "audio_enhanced_script": audio_enhanced_script})
        try:
            llm_response: str = invoke_llm(user_input=payload, system_instruction=script_to_script_list_system_prompt, model_provider=self.model_provider)
        except Exception as e:
            raise FailedGenerationError(f"Failed to generate script lists because of: {e}")

        try:
            script_list_and_audio_enhanced_script_list: list[dict[str, str]] = json.loads(extract_json_from_fence(llm_response)).get("script_list")
        except Exception as e:
            raise FailedParsingError(f"Failed to parse script lists from json because of: {e}")
        print("[Complete] Splitting scripts...\n")
        return script_list_and_audio_enhanced_script_list


    def generate_script_one_shot(self):
        """
            This function generates the script of the video using the information on the video object and generated the talking points.
            It generates the script for the entire video in one shot.
            The script is then enhanced for audio generation.
            Both the script and it's enhanced version are stored as a lists of string in the video object's
            `script_list` and `audio_enhanced_script_list` properties respectively.
            Returns:
                None
        """
        print("[Starting] Generating script one-shot...")
        required_fields = [
            "generated_talking_points",
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to generate a script in one shot.")

        payload = json.dumps({
            "topic": self.topic,
            "talking_points": "".join([talking_point.get("topic") for talking_point in self.generated_talking_points]),
            "goal": self.goal,
            "hook": self.hook,
            "purpose": self.purpose.value,
            "target_audience": self.target_audience,
            "tone": self.tone.value,
            "auxiliary_requests": self.auxiliary_requests,
            "platform": "Instagram and Tiktok",
            "duration_seconds": self.duration_seconds,
            "style_reference": self.style_reference,
        })
        try:
            llm_response = invoke_llm(user_input=payload, system_instruction=one_shot_script_generation_system_prompt, model_provider=self.model_provider)
        except Exception as e:
            raise FailedGenerationError(f"Failed to generate script one-shot because of: {e}")

        # extract the raw one shot script
        try:
            generated_script: str = json.loads(extract_json_from_fence(llm_response)).get("raw_script")
        except Exception as e:
            raise FailedParsingError(f"Failed to parse one-shot script from json because of: {e}")
        # get the enhanced for audio generation version of the script
        audio_enhanced_script: str = self.enhance_script_for_audio_generation(raw_script=generated_script)
        # split both the raw and enhanced versions of the script
        script_list_and_audio_enhanced_script_list: list[dict[str, str]] = self.split_scripts_into_script_lists(raw_script=generated_script, audio_enhanced_script=audio_enhanced_script)
        # store them in the video object's properties
        self.script_list = [script_object.get("script_segment", "") for script_object in script_list_and_audio_enhanced_script_list]
        self.audio_enhanced_script_list = [script_object.get("audio_enhanced_script_segment", "") for script_object in script_list_and_audio_enhanced_script_list]
        print("[Complete] Generating script one-shot...\n")


    def generate_script_segment_from_talking_point_for_multi_shot_script_generation(self, payload: str) -> str:
        """
        This function generates a segment of the script using the payload passed as an argument for multi-shot scripts.
        Parameters:
            payload (str): Contains data about the talking point and the video object, needed to generate a script segment for the talking point.
             It is in json string format.
        Returns:
            str: The generated script segment for the talking point.
        """
        print("[Starting] Generating script segment (multi-shot script)...")
        try:
            llm_response: str = invoke_llm(user_input=payload, system_instruction=multi_shot_script_generation_system_prompt, model_provider=self.model_provider)
        except Exception as e:
            raise FailedGenerationError(f"Failed to generate script segment because of: {e}")

        try:
            script_segment: str = json.loads(extract_json_from_fence(llm_response)).get("script_segment")
        except Exception as e:
            raise FailedParsingError(f"Failed to parse multi-shot script from json because of: {e}")
        print("[Complete] Generating script segment (multi-shot script)...\n")
        return script_segment


    def polish_multi_shot_script(self, raw_multi_shot_script: str) -> str:
        """
        This function takes the cumulative multi shot script and polishes it to make sure that it is nice and cohesive.
        Parameters:
            raw_multi_shot_script (str): The raw multi shot script generated.
        Returns:
            str: The polished multi shot script.
        """
        print("[Starting] Polishing multi shot script...")
        try:
            llm_response: str = invoke_llm(user_input=raw_multi_shot_script, system_instruction=multi_shot_script_polishing_system_prompt, model_provider=self.model_provider)
        except Exception as e:
            raise FailedGenerationError(f"Failed to generate polished multi shot script because of: {e}")

        try:
            polished_script: str = json.loads(extract_json_from_fence(llm_response)).get("polished_script")
        except Exception as e:
            raise FailedParsingError(f"Failed to parse multi shot script from json because of: {e}")
        print("[Complete] Polishing multi shot script...\n")
        return polished_script


    def generate_script_multi_shot(self):
        """
        This function generates the script of the video using the information on the video object and generated the talking points.
        It generated the script for each segment of the video separately. The actual generation of each segment is done
        in a separate method called `generate_script_segment_from_talking_point_for_multi_shot_script_generation`.
        The script is then enhanced for audio generation.
        Both the script and it's enhanced version are split and stored as a lists of string in the video object's
        `script_list` and `audio_enhanced_script_list` attributes respectively.
        Returns:
            None
        """
        print("[Starting] Generating script multi-shot...")
        required_fields = [
            "generated_talking_points",
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to generate a script in multi shots.")

        current_cumulative_multi_shot_script = ""

        # generating script segments for each talking point is done sequentially (not concurrently)because each
        # segment's generation relies on the portion of the script that has already been generated to improve
        # the cohesion of the script.
        for talking_point in self.generated_talking_points:

            payload = json.dumps({
                "topic": self.topic,
                "current_talking_point": talking_point,
                "goal": self.goal,
                "hook": self.hook,
                "purpose": self.purpose.value,
                "target_audience": self.target_audience,
                "tone": self.tone.value,
                "auxiliary_requests": self.auxiliary_requests,
                "platform": "Instagram and Tiktok",
                "duration_seconds": self.duration_seconds,
                "style_reference": self.style_reference,
                "all_talking_points": self.generated_talking_points,
                "current_script": current_cumulative_multi_shot_script
            })

            # We get the portion of the script that was generated
            script_segment: str = self.generate_script_segment_from_talking_point_for_multi_shot_script_generation(payload)
            current_cumulative_multi_shot_script += script_segment

        # After the for loop, we have a long script, that may or may not be cohesive because of its generation. it needs polishing
        polished_script: str = self.polish_multi_shot_script(json.dumps({"raw_script": current_cumulative_multi_shot_script}))
        # get the enhanced for audio generation version of the script
        audio_enhanced_script: str = self.enhance_script_for_audio_generation(raw_script=polished_script)
        # split both the raw and enhanced versions of the script
        script_list_and_audio_enhanced_script_list: list[dict[str, str]] = self.split_scripts_into_script_lists(raw_script=polished_script, audio_enhanced_script=audio_enhanced_script)
        # store them in the video object's attributes
        self.script_list = [script_object.get("script_segment", "") for script_object in script_list_and_audio_enhanced_script_list]
        self.audio_enhanced_script_list = [script_object.get("audio_enhanced_script_segment", "") for script_object in
                                           script_list_and_audio_enhanced_script_list]
        print("[Complete] Generating script multi-shot...\n")


    def create_clips(self):
        """
        This function creates the clips for the video using the script_list and video information.
        The clips are stored as a list of `Clips` in the video object's `clips` attribute
        """
        print("[Starting] Creating clips...")
        required_fields = [
            "script_list"
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to create clips.")

        for script_segment_index, script_segment in enumerate(self.script_list):
            previous_clip_voice_script_index = script_segment_index - 1
            next_clip_voice_script_index = script_segment_index + 1
            self.clip_count += 1
            new_clip = Clip(
                clip_id=self.clip_count,
                tone=self.tone,
                previous_clip_voice_script=self.script_list[previous_clip_voice_script_index] if (previous_clip_voice_script_index > 0) else None,
                voice_script=script_segment,
                voice_script_enhanced_for_audio_generation=self.audio_enhanced_script_list[script_segment_index],
                next_clip_voice_script=self.script_list[next_clip_voice_script_index] if next_clip_voice_script_index < (len(self.script_list) - 1) else None,
                aspect_ratio=self.aspect_ratio,
                model_provider=self.model_provider,
                image_model=self.image_model,
                image_style=self.image_style,
                voice_model=self.voice_model,
                voice_actor=self.voice_actor,
            )
            self.clips.append(new_clip)
        print("[Completed] Creating clips...")


    @staticmethod
    async def _generate_clips_audios(clip):
        """
        This is a helper function that generates audio clips for every clip concurrently by calling their
        `generate_voice_over` function in a different thread. It is called only by the `generate_clips_audios` function.
        Parameters:
            clip (Clip): The clip to generate audio clips for.
        Returns:
            None
        """
        async with elevenlabs_semaphore:
            await asyncio.to_thread(clip.generate_voice_over)


    async def generate_clips_audios(self):
        """
        This function generates audio clips for every clip. it makes use of a helper function called `_generate_clips_audios`.
        **This function is only to be called in multi-shot audio generation.**
        Returns:
            None
        """
        print("[Starting] Generating audio clips...")
        required_fields = [
            "clips"
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to generate clips.")

        async with asyncio.TaskGroup() as tg:
            for clip in self.clips:
                tg.create_task(self._generate_clips_audios(clip))
        print("[Completed] Generating audio clips...")


    def generate_video_audio(self, voice_model_version: Literal["eleven_v3", "eleven_multilingual_v2"] = "eleven_v3"):
        """
        This function generates the voiceover for the entire video in one shot.
        The audio file path is store in the video object's `one_shot_audio_file_path` attribute.
        **This function is only to be called in one-shot audio generation.**
        When the audio ifile s generated, information regarding the timestamps of every letter in the audio file is stored
        on the video object via the attributes `one_shot_audio_voice_over_characters`,
        `one_shot_audio_voice_over_start_times_seconds` and `one_shot_audio_voice_over_end_times_seconds`
        Parameters:
            voice_model_version (str) = The version of the audio generation model to be used. Only supports eleven labs models.
        Returns:
            None
        """
        print("[Starting] Generating video audio (one shot)...")
        required_fields = [
            "script_list",
            "audio_enhanced_script_list",
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to generate video audio.")

        text = "".join(self.audio_enhanced_script_list) if self.use_enhanced_script_for_audio_generation else "".join(self.script_list)

        elevenlabs_response = elevenlabs_client.text_to_speech.convert_with_timestamps(
            text=text,
            model_id=voice_model_version,
            voice_id=self.voice_actor.value,
            output_format="mp3_44100_128",
        )
        self.one_shot_audio_voice_over_characters = elevenlabs_response.normalized_alignment.characters
        self.one_shot_audio_voice_over_start_times_seconds = elevenlabs_response.normalized_alignment.character_start_times_seconds
        self.one_shot_audio_voice_over_end_times_seconds = elevenlabs_response.normalized_alignment.character_end_times_seconds


        audio_file_name = os.path.join("voice_over_audios", uuid.uuid4().hex + ".mp3")
        self.one_shot_audio_file_path = audio_file_name
        with open(audio_file_name, "wb") as audio_file:
                    audio_file.write(base64.b64decode(elevenlabs_response.audio_base_64))
        print("[Completed] Generated video audio (one shot)...")


    def assign_start_and_end_times_to_clips(self) -> None:
        """
        This functions assigns a start and end time to the clips in the video using its 3 parallel list attributes
        `one_shot_audio_voice_over_characters`, `one_shot_audio_voice_over_start_times_seconds`,
        and `one_shot_audio_voice_over_end_times_seconds`.
        **This function is only to be called in one-shot audio generation.**
        These attributes are populated by the `convert_with_timestamps` function in eleven labs within the video
        objects `generate_video_audio` method.

        """
        print("[Starting] Assigning start and end times to clips...")
        required_fields = [
            "one_shot_audio_voice_over_characters",
            "one_shot_audio_voice_over_start_times_seconds",
            "one_shot_audio_voice_over_end_times_seconds",
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to assign start and end times to clips.")

        # for debugging purposes.
        print("\n-----------")
        print(f"Characters length: {len(self.one_shot_audio_voice_over_characters)}")
        print(f"Start time length: {len(self.one_shot_audio_voice_over_start_times_seconds)}")
        print(f"End time length: {len(self.one_shot_audio_voice_over_end_times_seconds)}")
        print("-----------\n")

        # added exessive comments for fine-grained tracing during development and debugging
        # the current index is 0. This is the index of the three parallel arrays
        current_index = 0
        # we loop through all the clips
        for index, clip in enumerate(self.clips):
            # we set the start time index of the parallel arrays to the current index, We add one to accommodate for spaces after sentences
            start_time_index = current_index if current_index == 0 else current_index + 1
            # get the length of the clip's script
            clip_script_length = len(clip.voice_script_enhanced_for_audio_generation) if self.use_enhanced_script_for_audio_generation else len(clip.voice_script)
            # What ever the length of this is, the last character in it, is ONE above its place in the overall script (didn't subtract one because end is exclusive)
            # just added -1 during debugging
            end_time_index = start_time_index + clip_script_length - 1
            # the clips start_time_index and end_time_index define its length (end time is exclusive)
            clip.voice_over_start_time_index = start_time_index
            clip.voice_end_time_index = end_time_index

            #
            print(f"Start time index: {start_time_index}")
            print(f"End time index: {end_time_index}\n")
            print(f"last_index of start times: {len(self.one_shot_audio_voice_over_start_times_seconds)-1}")
            #

            # assign actual times to the clip
            clip.voice_over_start_time = self.one_shot_audio_voice_over_start_times_seconds[start_time_index]
            clip.voice_over_end_time = self.one_shot_audio_voice_over_start_times_seconds[end_time_index]
            clip.duration_seconds = clip.voice_over_end_time - clip.voice_over_start_time
            # this is meant to accommodate the inter clip gaps. basically adding to each clip, the the difference in duration after it ends and before the
            # next clips start as far as there is a next clip.
            clip.voice_over_end_time += (self.one_shot_audio_voice_over_start_times_seconds[end_time_index+1] -
                                         self.one_shot_audio_voice_over_start_times_seconds[end_time_index]) \
                if end_time_index+1 < len(self.one_shot_audio_voice_over_start_times_seconds) \
                else 0

            current_index = clip.voice_end_time_index

            # for debugging purposes.
            print(f"----Clip {index}----")
            print(f"Script length: {clip_script_length}")
            print(f"Script Start Index: {start_time_index}")
            print(f"Script start time: {clip.voice_over_start_time}")
            print(f"Script end time: {clip.voice_over_end_time}")
            print(f"Script end Index: {end_time_index}")
            print("-"*20)

            print("[Completed] Assigned start and end times to clips...")


    async def generate_clips_base_image_descriptions(self):
        """
        This functions generates base image descriptions for clips in the video object. It does this by calling the
        `generate_base_image_descriptions` method on each clip object. The base image descriptions are stored on the
        clip objects.
        Returns:
            None
        """
        print("[Starting] Generating base image descriptions for clips...")
        required_fields = [
            "clips"
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to generate base image descriptions.")

        full_script = "".join(self.script_list)
        async with asyncio.TaskGroup() as tg:
            for clip in self.clips:
                tg.create_task(clip.generate_base_image_descriptions(full_script=full_script,
                                                                     auxiliary_image_requests=self.auxiliary_image_requests))
        print("[Completed] Generated base image descriptions for clips...")


    @staticmethod
    async def _generate_clips_visuals(clip):
        """
        This is a helper function that generates visuals for clips by calling their `generate_base_images` method.
        Parameters:
            clip (Clip): The clip to generate visuals for.
        Returns:
            None
        """
        if clip.image_model == ImageModel.OPENAI:
            async with openai_semaphore:
                await asyncio.to_thread(clip.generate_base_images)

        elif clip.image_model == ImageModel.GEMINI:
            async with gemini_semaphore:
                await asyncio.to_thread(clip.generate_base_images)

    async def generate_clips_visuals(self):
        """
        This functions generates visuals for clips. It passes clips into its helper function `_generate_clips_visuals`
        which calls their `generate_base_images` method.
        Returns:
            None
        """
        print("[Starting] Generating visuals for clips...")
        required_fields = [
            "clips"
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to generate clip visuals.")

        async with asyncio.TaskGroup() as tg:
            for clip in self.clips:
                tg.create_task(self._generate_clips_visuals(clip))
        print("[Completed] Generated visuals for clips...")


    def animate_clips_visuals(self, audio_generation_method: Literal["one-shot", "multi-shot"] = "one-shot"):
        """
        This functions animates visuals for clips; animation in the sense that it turns their base images into videos.
        It does this by calling their `animate_visuals` method.
        """
        print("[Starting] Animating visuals for clips...")
        required_fields = [
            "clips"
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to animate clip visuals.")

        for clip in self.clips:
            clip.animate_visuals(audio_generation_method=audio_generation_method)
        print("[Completed] Animated visuals for clips...")


    def merge_clips_audios_and_visuals(self):
        """
        This functions merges the audio and visuals of clips by calling their `merge_audio_and_visuals` method.
        The merged media is a video that overwrites the clip's `animated_video_path` attribute.
        This function is only to be called for multi-shot audio generation.
        Returns:
            None
        """
        print("[Starting] Merging audio and visuals for clips (multi shot audio...")
        required_fields = [
            "clips"
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to merge clip audios with clip visuals.")

        for clip in self.clips:
            clip.merge_audio_and_visuals()
        print("[Completed] Merging audio and visuals for clips (multi shot audio)...")


    def merge_video_audio_and_clip_visuals(self):
        """
        This function merges the video audio with clip visuals.
        This will generate a final media object whose path is saved in the video object's `final_video_path` attribute.`
        This function is only to be called for one-shot audio generation.
        Returns:
            None
        """
        print("[Starting] Merging video audio with clip visuals (one-shot audio...)...")
        required_fields = [
            "clips"
        ]
        for field in required_fields:
            if not getattr(self, field):
                raise MissingDataError(f"The data point {field} is missing and is required to merge video audio with clip visuals.")
        if not self.clips:
            raise Exception("Clip visuals cannot be merged without clips.")
        time_of_creation = datetime.now().strftime("%Y%m%d%H%M%S")

        video_clips = [mvpy.VideoFileClip(clip.animated_video_path) for clip in self.clips]
        final_video = mvpy.concatenate_videoclips(video_clips, method="compose")
        audio_clip = mvpy.AudioFileClip(self.one_shot_audio_file_path)
        final_video_with_audio = final_video.with_audio(audio_clip)

        final_video_path = os.path.join("final_videos", f"{time_of_creation}.mp4")
        final_video_with_audio.write_videofile(final_video_path, fps=24, audio=True,
                                    codec='libx264',
                                    audio_codec='aac',
                                    )
        self.final_video_path = final_video_path
        print("[Completed] Merging video audio with clip visuals (one-shot audio...)...")


    def merge_all_clips(self):
        """
        This function merges all clips visuals into a media object (video) which is stored on the video object.
        This will generate a final media object whose path is saved in the video object's `final_video_path` attribute.`
        This function is only to be called for multi-shot audio generation.
        :return:
        """
        print("[Starting] Merging all clips (multi shot audio...)...")
        self.validate_clips()
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
        print("[Completed] Merging all clips (multi shot audio)...")

    async def generate_video(self, audio_generation_method: Literal["one-shot", "multi-shot"] = "one-shot",
                             script_generation_method: Literal["one-shot", "multi-shot"] = "one-shot"):
        """
        This function create a final media object whose path is stored on the video objects `final_video_path` attribute.
        Parameters:
            audio_generation_method (str): A string literal describing how the audio should be generated (one-shot or multi-shot).
            script_generation_method (str): A string literal describing how the script should be generated (one-shot or multi-shot).
        Returns:
            None
        """
        print("[Starting] Generating video...")
        for i in range(self.max_retries):
            try:
                self.generate_goal() # if it executes without error, break the loop
                break
            except MissingDataError as e:
                raise Exception(f"{e}") # For Missing Data Errors, raise immediately
            except Exception as e:
                print("Failed to generate goal, retrying...")
                if i == self.max_retries - 1:
                    raise e

        for i in range(self.max_retries):
            try:
                self.generate_hook()
            except MissingDataError as e:
                raise Exception(f"{e}")
            except Exception as e:
                print("Failed to generate hook, retrying...")
                if i == self.max_retries - 1:
                    raise e

        for i in range(self.max_retries):
            try:
                self.generate_talking_points()
                break
            except MissingDataError as e:
                raise Exception(f"{e}")
            except Exception as e:
                print("Failed to generate talking point, retrying...")
                if i == self.max_retries - 1:
                    raise e

        match script_generation_method:
            case "one-shot":
                for i in range(self.max_retries):
                    try:
                        self.generate_script_one_shot()
                        break
                    except MissingDataError as e:
                        raise Exception(f"{e}")
                    except Exception as e:
                        print("Failed to generate script one-shot, retrying...")
                        if i == self.max_retries - 1:
                            raise e

            case "multi-shot":
                for i in range(self.max_retries):
                    try:
                        self.generate_script_multi_shot()
                        break
                    except MissingDataError as e:
                        raise Exception(f"{e}")
                    except Exception as e:
                        print("Failed to generate script multi-shot, retrying...")
                        if i == self.max_retries - 1:
                            raise e

        for i in range(self.max_retries):
            try:
                self.create_clips()
                break
            except MissingDataError as e:
                raise Exception(f"{e}")
            except Exception as e:
                print("Failed to create clips, retrying...")
                if i == self.max_retries - 1:
                    raise e

        match audio_generation_method:
            case "one-shot":
                # no error handling because the only possible error is missing data, and we want those to always
                # terminate as we currently have no mechanism to generate missing data
                self.generate_video_audio()
                # start and end times must be assigned to clips before base image descriptions can be made
                # no error handling because the only possible error is out of index, and we want those to always
                # terminate as we currently have no mechanism to mitigate this
                self.assign_start_and_end_times_to_clips()
            case "multi-shot":
                # no error handling because the only possible error is missing data, and we want those to always
                # terminate as we currently have no mechanism to generate missing data
                await self.generate_clips_audios()

        for i in range(self.max_retries):
            try:
                await self.generate_clips_base_image_descriptions()
            except MissingDataError as e:
                raise Exception(f"{e}")
            except Exception as e:
                print("Failed to generate base image descriptions, retrying...")
                if i == self.max_retries - 1:
                    raise e

        # no error handling because the only possible error is missing data, and we want those to always
        # terminate as we currently have no mechanism to generate missing data
        await self.generate_clips_visuals()

        self.animate_clips_visuals(audio_generation_method=audio_generation_method)

        match audio_generation_method:
            case "one-shot":
                self.merge_video_audio_and_clip_visuals()
            case "multi-shot":
                self.merge_clips_audios_and_visuals()
                self.merge_all_clips()

        print("[Completed] Generated video...")


    # Inspection Methods
    def validate_clips(self):
        """
        This function validated if all the clips in the video. A clip is valid if it's `animated_video_path` attribute is not falsy.
        Returns:
            None
        """
        if not self.clips:
            raise Exception("Clip cannot be validated without clips.")
        all_clips_valid = True
        for clip in self.clips:
            if not clip.animated_video_path:
                all_clips_valid = False
                break
        self.all_clips_valid = all_clips_valid


    def get_final_video_path(self) -> str:
        """
        This function returns the final path of the final video.
        Returns:
            (str): the final video path
        """
        if not self.final_video_path:
            raise Exception("Final video path cannot be retrieved.")
        return self.final_video_path


    #  for interface
    def re_do_clip_action(self, clip_id: int, action: Literal["base_image","animate_base" ,"audio", "animate"]):
        pass
        # if clip_id > self.clip_count or clip_id < 0:
        #     raise Exception("Clip id is out of range.")
        #
        # clip_index = clip_id - 1
        # match action:
        #     case "base_image":
        #         self.clips[clip_index].generate_base_images()
        #         print("ran base image")
        #     case "animate_base":
        #         self.clips[clip_index].animate_video_multi_shot_audio()
        #         print("ran animate base image")
        #     case "audio":
        #         self.clips[clip_index].generate_voice_over()
        #         print("ran audio")
        #     case "animate":
        #         self.clips[clip_index].merge_audio_and_visuals()
        #         print("ran animate")


    def clips_summary(self):
        valid_clips = []
        invalid_clips = []
        for clip in self.clips:
            if clip.animated_video_path and os.path.isfile(clip.animated_video_path):
                valid_clips.append(clip.clip_id)
            else:
                invalid_clips.append(clip.clip_id)
        return valid_clips, invalid_clips




