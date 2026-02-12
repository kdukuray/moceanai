# default python modules
import base64
import os
import uuid
from pprint import pprint
from typing import Optional, Literal, Union
import json
from pathlib import Path
import asyncio
from datetime import datetime
# third party packages
import ffmpeg
from langchain.messages import AIMessage, HumanMessage, SystemMessage

from langgraph.graph import StateGraph
from langgraph.constants import START, END
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model
from elevenlabs import ElevenLabs
# my modules
from system_prompts import (
    short_form_video_goal_generation_system_prompt,
    short_form_script_generation_system_prompt,
    script_enhancer_elevenlabs_v3_system_prompt, script_segmentation_system_prompt,
    image_descriptions_generator_system_prompt, generate_segment_image_descriptions_system_prompt,
    long_form_video_structure_generation_system_prompt, long_form_video_topic_section_script_generation_system_prompt,
    long_form_video_section_script_segmenter_system_prompt
)
from utils import animate_with_motion_effect
from utils import model_providers, image_models, image_styles, voice_model_versions, voice_models, voice_actors
from utils import get_video_duration, generate_image, pseudo_generate_image
from concurrent.futures import ProcessPoolExecutor
NUM_WORKERS = os.cpu_count()
# AI Models
ai_model = init_chat_model(model_provider="google-genai", model="gemini-2.5-pro")
# ai_model = init_chat_model(model_provider="openai", model="gpt-5.1")
ai_voice_model = ElevenLabs(api_key=os.getenv("ELEVEN_LABS_API_KEY"))

# Typed Dictionaries


class GoalContainer(BaseModel):
    goal: str = Field(..., description="The goal of the video to be produced.")

class SectionStructure(BaseModel):
    section_name: str = Field(..., description="A descriptive name for the section.")
    section_purpose: str = Field(..., description="The purpose of the section in paragraph format explaining the strategic function of it.")
    section_directives: list[str] = Field(..., description="A list of directives that define the section's purpose.")
    section_talking_points: list[list] = Field(..., description="A list of talking points that will be discussed within this section.")

class SectionsStructureContainer(BaseModel):
    sections_structure_list: list[SectionStructure] = Field(..., description="A list of section structures for the video.")

class SectionScriptContainer(BaseModel):
    section_script: str = Field(..., description="The complete narration (script) for a section of the video as a single string.")

class SectionScriptSegmentItem(BaseModel):
    section_script_segment: str = Field(..., description="A segment of a section script.")

class SectionScriptSegmentedContainer(BaseModel):
    section_script_segmented_as_list: list[SectionScriptSegmentItem] = Field(..., description="A list of segments for a section's script.")

class ImageDescription(BaseModel):
    description: str = Field(..., description="The description of an image for a clip in the video.")
    uses_logo: bool = Field(..., description="A boolean that defines whether or not the image uses the company logo.")

class SegmentImageDescriptionsContainer(BaseModel):
    segment_image_descriptions: list[ImageDescription] = Field(..., description="A list of image descriptions.")



# -----------------------------------------------------------


class ScriptContainer(BaseModel):
    script: str = Field(..., description="The entire script of the video (all section scripts concatenated in a single string).")

class EnhancedScriptContainer(BaseModel):
    enhanced_script: str = Field(..., description="The enhanced version of the video's script to be used for audio generation."
                                                  "Simply a concatenation of all section's enhanced scripts.")

class SectionScript(BaseModel):
    section_script: str = Field(..., description="The section's script.")
    enhanced_section_script: str = Field(...,
                                         description="An audio enhanced version of the corresponding section's script.")

class ImageDescriptionsContainer(BaseModel):
    image_descriptions: list[ImageDescription] = Field(..., description="A list of image descriptions. Each container "
                                                                        "holds the image descriptions for a single segment within a section.")




class TalkingPoint(BaseModel):
    content: str = Field(..., description="The content of the talking point.")




# Video Creator Agent Definition
class AgentState(BaseModel):
    # required states
    topic: str = Field(..., description="The topic of the video")
    purpose: str = Field(..., description="What the video wishes to accomplish of the video")
    target_audience: str = Field(..., description="The intended audience for the video")
    tone: str = Field(..., description="The tone or mood of the video (e.g., informative, humorous)")
    platform: str = Field(..., description="The platform the video will be posted on (e.g., TikTok, YouTube)")
    duration_seconds: int = Field(..., description="The length of the video in seconds")
    orientation: Literal["Portrait", "Landscape"] = Field("Portrait", description="The orientation of the video")
    model_provider: model_providers = Field(...,
                                            description="The model provider that will be used to generate the video script and metadata")
    image_model: image_models = Field(..., description="The image generation model used")
    image_style: image_styles = Field(..., description="The artistic style for generated images")
    voice_actor: voice_actors = Field(..., description="The chosen voice actor or voice type")
    # states with default values
    voice_model_version: voice_model_versions = Field("eleven_v3", description="The voice generation model to use")
    additional_instructions: Optional[str] = Field(None, description="Any extra requests or creative directions")
    enhance_script_for_audio_generation: bool = Field(False,
                                                      description="A boolean that defines whether the script should be enhanced for audio generation or not.")
    additional_image_requests: Optional[str] = Field(None,
                                                     description="Additional image prompts or instructions for visuals")
    style_reference: str = Field("",
                                 description="A brief description of a creator, pacing, or stylistic pattern the script should emulate.")
    # states to be populated in agent workflow
    voice_actor_id: Optional[str] = Field(None, description="The voice actor id for the video.")
    goal: Optional[str] = Field(None, description="The goal of the video")
    hook: Optional[str] = Field(None, description="The hook of the video")
    script: Optional[str] = Field(None, description="The script for the video.")
    enhanced_script: Optional[str] = Field(None, description="The enhanced script for the video.")
    generated_audio_file_path: Optional[Path] = Field(None,
                                                      description="The file path for audio generated for the video.")
    # the following three states are parallel arrays
    generated_audio_characters: list[str] | None = Field(None, description="The characters for the generated audio.")
    generated_audio_character_start_times: list[float] | None = Field(None,
                                                                      description="The start times for every character in the generated audio.")
    generated_audio_character_end_times: list[float] | None = Field(None,
                                                                    description="The end times for every character in the generated audio.")
    # the following five states are parallel arrays representing individual clips
    script_list: Optional[list[dict[str, str]]] = Field(None,
                                                        description="A list of dictionaries containing segments of the raw and enhanced version of the script.")
    script_segment_durations: list[float] | None = Field(None,
                                                         description="The duration of each segment in the generated audio.")
    image_descriptions: Optional[list[ImageDescription]] = Field(None,
                                                                 description="A list of image descriptions for the clips in the video.")
    image_paths: Optional[list[Path]] = Field(None, description="A list of paths to images generated for the video.")
    video_paths: Optional[list[Path]] = Field(None, description="A list of paths to videos generated for the video.")
    image_descriptions_container_for_all_segments: Optional[list[dict[str, list[ImageDescription]]]] = Field(None,
                                                                                                             description="A list of dictionaries for each script segment, each dictionary has a key whose value is a list of ImageDescription objects.")
    all_segments_image_descriptions_container_for_all_segments: Optional[list[list[dict[str, list[ImageDescription]]]]] = Field(None,)
    image_paths_for_all_segments: Optional[list[list[Path]]] = Field(None,
                                                                     description="A list of lists of paths to images. Each segment corresponds to a list image paths")
    last_image_durations: Optional[list[float]] = Field(None,
                                                        description="The duration of the last image in each segment.")
    all_segments_last_image_durations: Optional[list[list[float]]] = Field(None,)
    # states used for debugging purposes
    debug_mode: bool = Field(False, description="A boolean that defines whether debugging should be enabled.")
    script_segment_begin_and_end_times: list[tuple[float, float]] = Field(None,
                                                                          description="The start and end times for the clips in the video.")
    # final video
    final_video_path: Optional[Path] = Field(None, description="The final path for the generated video.")

    # extras
    ideal_image_duration: int = Field(3, description="The duration of the ideal image in each segment.")
    minimum_acceptable_image_duration: int = Field(2, description="The minimum acceptable image duration in seconds.")
    add_end_buffer: bool = Field(True,
                                 description="A boolean that defines whether to add an end buffer to the generated video.")

    sections_structure: list = Field(None, description="A list of structured sections that make up the video's overall structure.")
    section_scripts: list[str] = Field(None, description="A list of strings that are scripts for the video sections.")
    section_script_as_list: list[dict[str, str]] = Field(None, description="A list of dictionaries containing segments for the script of a single segment.")

    #
    sections_structure_list: list[SectionStructure] = Field(None, description="A list of section structures for the video.")
    all_sections_scripts_as_lists: list[list[SectionScriptSegmentItem]] = Field(None,
                                                                                description="A list of lists, each inner list containing section script segment items, with one key, `section script segment` that contains the raw script for that segment of the section's script.")
    all_sections_generated_audio_file_paths: list[Path] = Field(None, description="The file path for audio generated for all segments.")
    all_sections_generated_audio_characters: list[list[str]] | None = Field(None, description="The segments generated audio characters.")
    all_sections_generated_audio_character_start_times: list[list[float]] | None = Field(None, description="The start times for every segment's audio.")
    all_section_generated_audio_character_end_times: list[list[float]] | None = Field(None, description="The end times for every segment's audio.")
    all_sections_scripts_durations: list[list[float]] | None = Field(None, description="The durations for every section's scripts script segments.")
    all_sections_scripts_begin_and_end_times:list[list[tuple[float, float]]] | None = Field(None, description="The start and end times for every sections's script segments.")
    # all_sections_image_descriptions_container_for_all_segments is a list, of list or SegmentImageDescriptionsContainer
    # remember that each SegmentImageDescriptionsContainer itself contains a list of ImageDescriptions in its segment_image_descriptions attribute
    all_sections_image_descriptions_container_for_all_segments: list[list[SegmentImageDescriptionsContainer]] | None = Field(None, description="A list of lists of SegmentImageDescriptionsContainer. One otter list per section, one inner list for each segment in the segment")
    all_sections_segments_last_image_durations: list[list[float]] | None = Field(None, description="The durations for every section's segments' last images.")
    all_segments_image_paths_for_all_sections: list[list[list[Path]]] | None = Field(None, description="")
    all_sections_final_video_paths: list[Path] | None = Field(None, description="")

# semi done
def resolve_agent_state_values(state: AgentState) -> dict[str, str]:
    """
    This function maps user-friendly names from the AgentState,
    to values that the models expects to their corresponding technical IDs or values
    expected by downstream models or APIs.
    Parameters:
        state (AgentState): The current state of the agent.
    Returns:
        dict[str, str]: The resolved configuration values.
    """
    if state.debug_mode:
        print("Resolving agent state values...")
    voice_actor_ids_dict = {
        "american_male_narrator": "Dslrhjl3ZpzrctukrQSN",  # BRAD
        "american_male_conversationalist": "Dslrhjl3ZpzrctukrQSN",  # MARK
        "american_female_conversationalist": "tnSpp4vdxKPjI9w0GnoV",  # HOPE
        "british_male_narrator": "giAoKpl5weRTCJK7uB9b",  # OWEN
        "british_female_narrator": "1hlpeD1ydbI2ow0Tt3EW",  # ORACLE X
        "american_male_story_teller": "uju3wxzG5OhpWcoi3SMy",
        "american_female_narrator": "yj30vwTGJxSHezdAGsv9",
        "american_female_media_influencer": "kPzsL2i3teMYv0FxEYQ6",
        "american_female_media_influencer_2": "S9NKLs1GeSTKzXd9D0Lf",
        "new_male_convo": "1SM7GgM6IMuvQlz2BwM3"
    }
    return {"voice_actor_id": voice_actor_ids_dict.get(state.voice_actor, "")}

# semi done
def generate_goal(state: AgentState) -> dict[str, str]:
    """
    This function generates the main goal of the video using the target audience, topic and purpose of the video.
    The goal is a sentence describing the angle that the video is taking and what the video intends to achieve.
    It returns a dictionary with a single `goal` key.
    Parameters:
        state (AgentState): The current state of the agent.
    Returns:
        dict[str, str]: Dictionary containing the goal for the video
    """
    if state.debug_mode:
        print("Generating goal...")
    model_for_goal = ai_model.with_structured_output(GoalContainer)
    payload = json.dumps({
        "topic": state.topic,
        "purpose": state.purpose,
        "target_audience": state.target_audience,
    })
    system_message = AIMessage(content=short_form_video_goal_generation_system_prompt)
    user_message = HumanMessage(content=payload)
    messages = [system_message, user_message]
    goal_container: BaseModel = model_for_goal.invoke(messages)
    return {"goal": goal_container.goal}

# semi done
def generate_structure(state: AgentState) -> dict[str, list]:
    """
    This function generates the structure of the video using the topic, purpose, target audience, tone and goal.
    structure divides the video in sections. Each section has topic_name; descriptive name for the section,
    topic_purpose; brief summary of what the section aims to achieve,
    """
    if state.debug_mode:
        print("Generating Video Structure ...")
    model_for_sections_structure = ai_model.with_structured_output(SectionsStructureContainer)
    payload = json.dumps({
        "topic": state.topic,
        "purpose": state.purpose,
        "target_audience": state.target_audience,
        "tone": state.tone,
        "goal": state.goal,
        "max_sections": 3 # delete later
    })
    system_message = AIMessage(content=long_form_video_structure_generation_system_prompt)
    user_message = HumanMessage(content=payload)
    messages = [system_message, user_message]
    sections_structure_container: BaseModel = model_for_sections_structure.invoke(messages)
    return {"sections_structure_list": [section_structure for section_structure in sections_structure_container.sections_structure_list]}



# semi done
def generate_section_scripts(state: AgentState) -> dict[str, str]:
    """
        This function generates the script of the video using the information on the video object.
        It generates the script for the entire video in one shot.
        It returns a dictionary with a single `script` key.
        Parameters:
            state (AgentState): The current state of the agent.
        Returns:
            dict[str, str]: Dictionary containing the script for the video
    """
    if state.debug_mode:
        print("Generating script...")
    model_for_section_script = ai_model.with_structured_output(SectionScriptContainer)
    cumulative_script = ""
    section_scripts = []
    num_of_sections = len(state.sections_structure_list) + 1
    for index, section_structure in enumerate(state.sections_structure_list):
        print(f"Generating script for section {index+1} of {num_of_sections}...")
        payload = json.dumps({
            "topic": state.topic,
            "purpose": state.purpose,
            "target_audience": state.target_audience,
            "tone": state.tone,
            "additional_requests": state.additional_instructions,
            "style_reference": state.style_reference,
            "cumulative_script": cumulative_script,
            "section_information": {
                "section_name": section_structure.section_name,
                "section_purpose": section_structure.section_purpose,
                "section_directives": section_structure.section_directives,
                "section_talking_points": section_structure.section_talking_points,
            }
        })
        system_message = SystemMessage(content=long_form_video_topic_section_script_generation_system_prompt)
        user_message = HumanMessage(content=payload)
        messages = [system_message, user_message]
        section_script_container = model_for_section_script.invoke(messages)
        cumulative_script += section_script_container.section_script
        section_scripts.append(section_script_container.section_script)

    return {"script": cumulative_script, "section_scripts": section_scripts}

# skipped
def enhance_script_for_audio_generation(state: AgentState) -> dict[str, str]:
    """
        This function enhances the script for the audio generation of the video. it does by adding SSML(speech synthesis
        markup language) tags. It returns a dictionary with a single `enhanced_script` key.
        Parameters:
            state (AgentState): The current state of the agent.
        Returns:
            dict[str, str]: Dictionary containing the enhanced script for audio generation.
    """
    if state.debug_mode:
        print("Enhancing script for audio generation...")
    model_for_enhanced_script = ai_model.with_structured_output(EnhancedScriptContainer)
    payload = json.dumps({
        "script": state.script,
    })

    system_message = SystemMessage(content=script_enhancer_elevenlabs_v3_system_prompt)
    user_message = HumanMessage(content=payload)
    messages = [system_message, user_message]
    enhanced_script_container: BaseModel = model_for_enhanced_script.invoke(messages)
    return {"enhanced_script": enhanced_script_container.model_dump().get("enhanced_script", "")}

# semi done
def segment_section_scripts(state: AgentState) -> dict[str, list[list[SectionScriptSegmentItem]]]:
    """
    This function takes the  script and the version of the script that was enhanced for audio generation, splits
    them into cohesive and logically separated segments. It returns a list of dictionaries, where each contains segments
    of the script. It has two keys, one that maps to raw segment of the script, and another that maps to corresponding
    segment from the enhanced version of the script.
    Parameters:
        state(AgentState): pass
    Returns:
        dict[str, list[dict[str, str]]]: Dictionary containing the segmented script for audio generation.
    """
    if state.debug_mode:
        print("Segmenting section_script scripts")
    # This is a list of lists
    # each inner list is the segmented version of a single section_script's script
    # Each instance of the segments is a dictionary
    all_sections_scripts_as_lists: list[list[SectionScriptSegmentItem]] = []
    for index, section_script in enumerate(state.section_scripts):
        print(f"Segmenting script for section_script: index:{index}, script:{section_script}")
        model_for_segmenting_script_segments = ai_model.with_structured_output(SectionScriptSegmentedContainer)
        payload = json.dumps({
            "section_script": section_script
        })
        # SectionScriptSegmentItem
        system_message = SystemMessage(content=long_form_video_section_script_segmenter_system_prompt)
        user_message = HumanMessage(content=payload)
        messages = [system_message, user_message]
        section_script_segmented_container = model_for_segmenting_script_segments.invoke(messages)
        # section_script_segmented_container is a class with a key section_script_segmented_as_list`
        # section_script_segmented_as_list is a list of `section_script_segment_item`
        # each `section_script_segment_item` has one key `section_script_segment` that contain actual segment text
        all_sections_scripts_as_lists.append([section_script_segment_item for section_script_segment_item in section_script_segmented_container.section_script_segmented_as_list])

    return {"all_sections_scripts_as_lists": all_sections_scripts_as_lists}


    # model_for_script_list = ai_model.with_structured_output(ScriptListContainer)
    # payload = json.dumps({
    #     "script": state.script,
    #     "enhanced_script": state.enhanced_script,
    # })
    # system_message = AIMessage(content=script_segmentation_system_prompt)
    # user_message = HumanMessage(content=payload)
    # messages = [system_message, user_message]
    # script_list_container: BaseModel = model_for_script_list.invoke(messages)
    # # print(script_list_container)
    # # print(script_list_container.script_list[0])
    # return {"script_segment_list": script_list_container.model_dump().get("script_segment_list", [])}

# semi done
def generate_section_audios(state: AgentState) -> dict[str, list[str]]:
    """
    This function generates the audio using the script or enhanced script depending on the agent state.
    The generated video is saved and the path to it is stored in the agent state's generated_audio_path attribute along
    with other metadata related to the genefrated audio.
    Parameters:
        state (AgentState): The current state of the agent.
    Returns:
        dict[str, str]: Dictionary containing the file path to audio generated for the video, a list of all the characters
        in the generated audio and a list of start and end times for all the characters in the generated audio.
    """
    if state.debug_mode:
        print("Generating audio...")
    all_sections_generated_audio_file_paths = []
    all_sections_generated_audio_characters = []
    all_sections_generated_audio_character_start_times = []
    all_sections_generated_audio_character_end_times = []
    for section_script in state.section_scripts:
        section_generated_audio = ai_voice_model.text_to_speech.convert_with_timestamps(
            text=section_script,
            model_id=state.voice_model_version,
            voice_id=state.voice_actor_id,
            output_format="mp3_44100_128",
        )

        section_generated_audio_file_path = Path(os.getcwd()) / "generated_audio_files" / f"{uuid.uuid4().hex}.mp3"
        section_generated_audio_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(section_generated_audio_file_path, "wb") as generated_audio_file:
            generated_audio_file.write(base64.b64decode(section_generated_audio.audio_base_64))

        all_sections_generated_audio_file_paths.append(section_generated_audio_file_path)
        all_sections_generated_audio_characters.append(section_generated_audio.normalized_alignment.characters)
        all_sections_generated_audio_character_start_times.append(section_generated_audio.normalized_alignment.character_start_times_seconds)
        all_sections_generated_audio_character_end_times.append(section_generated_audio.normalized_alignment.character_end_times_seconds)

    updated_state = {
        "all_sections_generated_audio_file_paths": all_sections_generated_audio_file_paths,
        "all_sections_generated_audio_characters": all_sections_generated_audio_characters,
        "all_sections_generated_audio_character_start_times": all_sections_generated_audio_character_start_times,
        "all_sections_generated_audio_character_end_times": all_sections_generated_audio_character_end_times,
    }
    return updated_state

# semi done
def compute_section_script_timings(state: AgentState) -> dict[str, list[float]]:
    """
    This function computes precise timing information for each script segment used as voice-over
    for video clips. This function aligns every script segment to the internally
    generated audio timeline by mapping character indices to their corresponding
    audio start times.For each script segment, this function determines:
        • actual_start_time — when the segment begins in the generated audio
        • actual_end_time   — when the segment ends (including gap adjustments)
        • duration          — the total playback length of the segment
    Parameters:
        state (AgentState): The current state of the agent.
    Returns:
        dict[str, Union[list[float], list[tuple[float, float]]]: Dictionary containing the timing information for each script segment.
    """
    if state.debug_mode:
        print("Calculating script segment timings...")
    # This is a list of list, one list per section
    # Each list contains tuples, one tuple per segment in the section
    # The first element in the tuple is the start time and the second element is the end time
    all_sections_scripts_begin_and_end_times = []
    # This is a list of lists, one per section
    # Each list contains floats, the floats in the list represent the
    # durations of the segments in the section.
    all_sections_scripts_durations = []

    # each section_script_segmented_as_list is a list of SectionScriptSegmentItem (which have one key; `section_script_segment`) for a single section
    # section_index is used to index into the section we are on in the iteration
    for section_index, section_script_segmented_as_list in enumerate(state.all_sections_scripts_as_lists):
        section_script_begin_and_end_times = []
        # a list of floats, each float represents the duration of an image frame in the section_script_segment
        # remember, a single segment.......
        section_script_durations = []
        # added exessive comments for fine-grained tracing during development and debugging
        # start_time_index for each section_script_segment, refers to corresponding index of the section_script_segment's first character in
        # generated audio's character array. the end_time_index for each section_script_segment, refers to corresponding index of
        # the section_script_segment's last character in generated audio's character array.
        # the current index is 0. This is the index of the three parallel arrays
        current_index = 0
        # loop through all the script segments
        # section_script_segment_index is used to iterate through a sectino's script segments
        for section_script_segment_index, section_script_segment_item in enumerate(section_script_segmented_as_list):
            # we set the start time index of the parallel arrays to the current index,
            # We add one to accommodate for spaces after sentences if we are not on the first script segment
            start_time_index = current_index if current_index == 0 else current_index + 1
            # start_time_index = current_index
            # get the character length of the script segment's script
            # the 'current script' may be  referring to the raw script or enhanced_script, depending on which mode of audio
            # generation was used
            section_script_segment_length = len(section_script_segment_item.section_script_segment)
            # because of zero indexing, the last character in the section_script_segment's script correspond to the following
            # index in the overall generated audio's character list
            end_time_index = start_time_index + section_script_segment_length - 1

            # actual start and end times for each script segment
            # actual_start_time = state.generated_audio_character_start_times[start_time_index] # error
            # actual_end_time = state.generated_audio_character_start_times[end_time_index] error
            actual_start_time = state.all_sections_generated_audio_character_start_times[section_index][start_time_index]
            actual_end_time = state.all_sections_generated_audio_character_start_times[section_index][end_time_index]


            # there may be a gap between when a script segment ends and when the other begins, to accommodate this, we add
            # the difference in time to the end time of the former script segment
            actual_end_time += (state.all_sections_generated_audio_character_start_times[section_index][end_time_index + 2] -
                                state.all_sections_generated_audio_character_start_times[section_index][end_time_index]) \
                if end_time_index + 2 < len(state.all_sections_generated_audio_character_start_times[section_index]) \
                else 0
            section_script_segment_duration = actual_end_time - actual_start_time
            # segment_script_segment_duration = actual_end_time - actual_start_time
            section_script_durations.append(section_script_segment_duration)
            current_index = end_time_index + 1 if end_time_index + 1 < len(
                state.all_sections_generated_audio_character_start_times[section_index]) else 0
            section_script_begin_and_end_times.append((actual_start_time, actual_end_time))

        all_sections_scripts_durations.append(section_script_durations)
        all_sections_scripts_begin_and_end_times.append(section_script_begin_and_end_times)

    # all_sections_scripts_durations is a list[list[floats]]
    # all_sections_scripts_begin_and_end_times is list[list[tuple[float, float]]]
    return {"all_sections_scripts_durations": all_sections_scripts_durations,
            "all_sections_scripts_begin_and_end_times": all_sections_scripts_begin_and_end_times}


def compute_length_and_num_of_images_per_segment(segment_duration_seconds: float, ideal_image_duration,
                                                 minimum_acceptable_image_duration) -> tuple[int, float]:
    """
    Determine how many B-roll images a segment should use and how long the
    final image should last, based on timing constraints.

    Every image ideally has the same duration (`ideal_image_duration`).
    The segment is divided into these evenly sized chunks. Any leftover
    time (excess) is evaluated:

        - If the leftover time is **greater** than `minimum_acceptable_image_duration`,
          it becomes a **separate additional image**.
        - Otherwise, the leftover time is **absorbed into the last image**, making it
          slightly longer than the others.

    This ensures:
        - At least **one image** always exists (even if the segment is shorter than
          the ideal duration).
        - Images are distributed as evenly as possible.
        - Very short, visually awkward final clips are avoided.
    Parameters:
        segment_duration_seconds (int): Total duration of the segment.
        ideal_image_duration (int): Target duration of each image before considering leftovers.
        minimum_acceptable_image_duration (int): Minimum duration allowed for an additional standalone final image.

    """
    # if the ideal_image_duration > segment_duration, then we should still have
    # one clip at the very least, not zero
    if segment_duration_seconds <= ideal_image_duration:
        # Single image that covers the whole segment
        return 1, segment_duration_seconds

    # Compute how many full images fit and the leftover time
    full_images, excess_time = divmod(segment_duration_seconds, ideal_image_duration)

    # if the excess time after all images (of duration `ideal_image_duration`)
    # is greater than the duration of `minimum_acceptable_image_duration`,
    # make a new image with duration = excess_time
    if excess_time > minimum_acceptable_image_duration:
        images_count = full_images + 1
        last_sub_clip_duration = excess_time

    # if excess_time is less than or equal to minimum_acceptable_image_duration,
    # don't make a new clip; simply add the remaining time to the last clip
    else:
        images_count = full_images
        last_sub_clip_duration = ideal_image_duration + excess_time

    print(f"The actual duration is {segment_duration_seconds}")
    print(f"We calculated time duration is {(images_count - 1) * ideal_image_duration + last_sub_clip_duration}")
    print("With the following:")
    print("Number of images:", images_count)
    print("Last sub clip duration:", last_sub_clip_duration)
    print("-" * 10)

    return int(images_count), last_sub_clip_duration

# semi done
async def generate_segments_image_descriptions(state: AgentState) -> dict[str, list]:
    """"""
    if state.debug_mode:
        print("Generating section segment image descriptions...")
        # each section should have a list of lists, each inner list contains the image descriptions for a segment in the section
    all_sections_image_descriptions_container_for_all_segments = []
    all_sections_segments_last_image_durations = []

    model_for_segment_image_descriptions = ai_model.with_structured_output(SegmentImageDescriptionsContainer)

    for section_index, section_script_segmented_as_list in enumerate(state.all_sections_scripts_as_lists):
        section_tasks = []
        segments_in_section_last_image_durations: list[float] = []

        async with asyncio.TaskGroup() as t:
            # for each segment in a section, get image descriptions and last clip durations
            # for index in range(len(state.script_list)):
            for segment_in_section_script_index in range(len(section_script_segmented_as_list)):
                # calculate num of clips in the segment and length of the last image in it
                num_of_images_per_segment, last_image_duration = compute_length_and_num_of_images_per_segment(
                    state.all_sections_scripts_durations[section_index][segment_in_section_script_index],
                    state.ideal_image_duration,
                    state.minimum_acceptable_image_duration)
                # for each segment, save the last image duration
                segments_in_section_last_image_durations.append(last_image_duration)

                # Construct payload to create image descriptions for a segment
                payload = json.dumps({
                    "script_segment": state.all_sections_scripts_as_lists[section_index][segment_in_section_script_index].section_script_segment,
                    "full_script": state.section_scripts[section_index],
                    "additional_image_requests": state.additional_image_requests,
                    "image_style": state.image_style,
                    "topic": state.topic,
                    "tone": state.tone,
                    "num_of_image_descriptions": num_of_images_per_segment
                })
                system_message = SystemMessage(content=generate_segment_image_descriptions_system_prompt)
                user_message = HumanMessage(content=payload)
                messages = [system_message, user_message]
                section_tasks.append(t.create_task(asyncio.to_thread(model_for_segment_image_descriptions.invoke, messages)))

        # this a list container (container = dictionary) with a key "segment_image_descriptions". For each dictionary, the value of this key
        # is a list of ImageDescription objects.

        # each section_task.result() is an item with key `segment_image_descriptions` thats a list ImageDescriptions
        # this is a list that contains SegmentImageDescriptionsItems
        # each list of SegmentImageDescriptionsItems is associated with one section
        image_descriptions_container_for_all_segments_in_section = [segment_image_descriptions_item.result() for segment_image_descriptions_item in section_tasks]
        ### now we have image descriptions for one section, instead of returning, let's save this in an array and use it later
        # all_sections_segments_last_image_durations is a list, of a list of floats
        # each otter list corresponds to a section
        # each inner list contains last image durations in a section (one for each segment in the section)
        # all_sections_image_descriptions_container_for_all_segments is a list, of list or SegmentImageDescriptionsContainer
        # remember that each SegmentImageDescriptionsContainer itself contains a list of ImageDescriptions in its segment_image_descriptions attribute
        all_sections_segments_last_image_durations.append(segments_in_section_last_image_durations)
        all_sections_image_descriptions_container_for_all_segments.append(image_descriptions_container_for_all_segments_in_section)

    return {"all_sections_image_descriptions_container_for_all_segments": all_sections_image_descriptions_container_for_all_segments,
            "all_sections_segments_last_image_durations": all_sections_segments_last_image_durations}

# semi done
async def generate_segments_images(state: AgentState) -> dict[str, list[list[list[Path]]]]:
    if state.debug_mode:
        print("Generating segment images...")

    #
    all_segments_image_paths_for_all_sections: list[list[list[Path]]] = []

    # section_image_descriptions_container_for_all_segments_in_section is a list of image descriptions, one for each segment in the section
    for section_image_descriptions_container_for_all_segments_in_section in state.all_sections_image_descriptions_container_for_all_segments:
        image_paths_for_all_segments_in_section: list[list[Path]] = []
        tasks = []
        try:
            async with asyncio.TaskGroup() as t:
                # image_descriptions_container has key whose value is a list of ImageDescriptions
                for segment_index, image_descriptions_container in enumerate(section_image_descriptions_container_for_all_segments_in_section):
                    # image_descriptions_container has key whose value is a list of ImageDescriptions
                    image_descriptions_objs_for_segment = image_descriptions_container.segment_image_descriptions
                    num_of_images_to_create = len(image_descriptions_objs_for_segment)
                    image_descriptions_for_segment = [image_description.description for image_description in image_descriptions_objs_for_segment]
                    segment_image_paths: list[Path] = [Path(os.getcwd()) / "generated_image_files" / f"{uuid.uuid4().hex}.jpg" for _ in range(num_of_images_to_create)]
                    segment_image_paths[0].parent.mkdir(parents=True, exist_ok=True)
                    image_paths_for_all_segments_in_section.append(segment_image_paths)

                    if state.debug_mode:
                        print(f"[generate_segments_images] segment_index={segment_index} num_images={len(image_descriptions_for_segment)} model={state.image_model}")
                        print(f"[generate_segments_images] segment_index={segment_index} first_out_path={segment_image_paths[0] if segment_image_paths else None}")
                    task = t.create_task(pseudo_generate_image(image_descriptions=image_descriptions_for_segment,
                                                        image_paths=segment_image_paths,
                                                        image_model_provider="flux",
                                                        orientation="landscape",
                                                        ))
                    # task = t.create_task(asyncio.to_thread(generate_single_image, image_descriptions_for_segment, segment_image_paths, "google", "portrait"))
                    if state.debug_mode:
                        try:
                            task.set_name(f"generate_image[{segment_index}]")
                        except Exception:
                            pass
                    tasks.append((segment_index, task, segment_image_paths))

        except* Exception as eg:
            import traceback
            print("\n[TaskGroup ERROR] generate_segments_images failed")
            print(f"[TaskGroup ERROR] topic={getattr(state, 'topic', None)}")
            print(f"[TaskGroup ERROR] segments_created={len(image_paths_for_all_segments_in_section)} total_tasks={len(tasks)}")
            for seg_i, task, paths in tasks:
                try:
                    name = task.get_name()
                except Exception:
                    name = None
                print(f"[TaskGroup ERROR] task_meta segment_index={seg_i} task_name={name} num_paths={len(paths)} first_path={paths[0] if paths else None}")
            for i, sub in enumerate(eg.exceptions, start=1):
                print(f"\n[TaskGroup ERROR] sub-exception #{i}: {type(sub).__name__}: {sub}")
                print("".join(traceback.format_exception(type(sub), sub, sub.__traceback__)))
            raise

        all_segments_image_paths_for_all_sections.append(image_paths_for_all_segments_in_section)

    return {"all_segments_image_paths_for_all_sections": all_segments_image_paths_for_all_sections}

#
# async def generate_all_sections_segments_images(state: AgentState) -> dict[str, list[list[Path]]]:
#     if state.debug_mode:
#         print("Generating clip images...")
#
#     rate_limit_delay = 7
#     all_sections_image_paths_for_all_segments = []
#     for section_image_descriptions_container_for_all_segments in state.all_sections_image_descriptions_container_for_all_segments:
#         section_image_paths_for_all_segments: list[list[Path]] = []
#         async with asyncio.TaskGroup() as t:
#             # image_descriptions_container has key whose value is a list of ImageDescriptions
#             for image_descriptions_container in section_image_descriptions_container_for_all_segments:
#                 # image_descriptions_container has key whose value is a list of ImageDescriptions
#                 image_descriptions_objs_for_segment = image_descriptions_container.get("segment_image_descriptions")
#                 num_of_images_to_create = len(image_descriptions_objs_for_segment)
#                 image_descriptions_for_segment = [image_description.description for image_description in
#                                                   image_descriptions_objs_for_segment]
#                 segment_image_paths: list[Path] = [Path(os.getcwd()) / "generated_image_files" / f"{uuid.uuid4().hex}.jpg"
#                                                    for _ in range(num_of_images_to_create)]
#                 segment_image_paths[0].parent.mkdir(parents=True, exist_ok=True)
#                 section_image_paths_for_all_segments.append(segment_image_paths)
#                 t.create_task(
#                     asyncio.to_thread(generate_single_image, image_descriptions_for_segment, segment_image_paths, "google",
#                                       "portrait"))
#                 # for Google image gen rate limits
#                 if state.image_model == "google":
#                     await asyncio.sleep(rate_limit_delay * len(image_descriptions_for_segment))
#         all_sections_image_paths_for_all_segments.append(section_image_paths_for_all_segments)
#
#     return {"all_sections_image_paths_for_all_segments": all_sections_image_paths_for_all_segments}

# semi done
async def animate_segments_images(state: AgentState) -> dict[str, list[Path]]:
    if state.debug_mode:
        print("Generating animated clip images...")
    all_sections_final_video_paths: list[Path] = []
    # image_paths_for_all_segments_in_section is a list of lists of paths
    for section_index, image_paths_for_all_segments_in_section in enumerate(state.all_segments_image_paths_for_all_sections):
        video_paths_for_segments_in_section: list[Path] = []
        motion_pattern = ["zoom_in", "zoom_out"]
        pattern_length = len(motion_pattern)
        pattern_start = 0
        tasks = []
        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor(NUM_WORKERS) as executor:
            for i in range(len(image_paths_for_all_segments_in_section)):
                video_path = Path(os.getcwd()) / "generated_video_files" / f"{uuid.uuid4().hex}.mp4"
                video_path.parent.mkdir(parents=True, exist_ok=True)
                video_paths_for_segments_in_section.append(video_path)
                motion_start_index = pattern_start % pattern_length
                task = loop.run_in_executor(executor,
                                        animate_with_motion_effect,
                                        image_paths_for_all_segments_in_section[i],
                                        video_path,
                                        float(state.ideal_image_duration),
                                        state.all_sections_segments_last_image_durations[section_index][i],
                                        motion_pattern,
                                        motion_start_index
                                            )
                tasks.append(task)
                pattern_start += len(image_paths_for_all_segments_in_section[i])
            await asyncio.gather(*tasks)

        # by here, video_paths_for_segments_in_section contains a list of paths to animated videos
        # we should concatenate them with their audio

        all_segments_in_section_video_clips = [ffmpeg.input(segment_video_path) for segment_video_path in video_paths_for_segments_in_section]

        section_time_of_creation = datetime.now().strftime("%Y%m%d%H%M%S")

        section_final_video_path = Path(os.getcwd()) / "section_generated_final_video_files" / f"{section_time_of_creation}.mp4"
        section_final_video_path.parent.mkdir(parents=True, exist_ok=True)

        section_video_clip_concatenated = ffmpeg.concat(*all_segments_in_section_video_clips, v=1, a=0).node
        section_video_stream = section_video_clip_concatenated[0]
        # Add the audio file
        section_audio_stream = ffmpeg.input(state.all_sections_generated_audio_file_paths[section_index])
        section_final_output = ffmpeg.output(
            section_video_stream,
            section_audio_stream,
            str(section_final_video_path),
            vcodec='libx264',
            acodec='aac',
            # shortest=None
        )
        section_final_output.run(overwrite_output=True)
        all_sections_final_video_paths.append(section_final_video_path)


    return {"all_sections_final_video_paths": all_sections_final_video_paths}

#
# async def animate_segments_images(state: AgentState) -> dict[str, list[Path]]:
#     if state.debug_mode:
#         print("Generating animated clip images...")
#     all_sections_video_paths = []
#     for section_image_paths_for_all_segments in state.all_segments_image_paths_for_all_sections:
#         video_paths = []
#         motion_pattern = ["ken_burns"]
#         pattern_length = len(motion_pattern)
#         pattern_start = 0
#         async with asyncio.TaskGroup() as t:
#             for i in range(len(state.image_paths_for_all_segments)):
#                 video_path = Path(os.getcwd()) / "generated_video_files" / f"{uuid.uuid4().hex}.mp4"
#                 video_path.parent.mkdir(parents=True, exist_ok=True)
#                 video_paths.append(video_path)
#                 motion_start_index = pattern_start % pattern_length
#                 t.create_task(asyncio.to_thread(animate_with_motion_effect,
#                                                 image_paths=state.image_paths_for_all_segments[i],
#                                                 video_path=video_path,
#                                                 ideal_image_duration=state.ideal_image_duration,
#                                                 last_image_duration=state.last_image_durations[i],
#                                                 motion_pattern=motion_pattern,
#                                                 motion_start_index=motion_start_index))
#                 pattern_start += len(state.image_paths_for_all_segments[i])
#         all_sections_video_paths.append(video_paths)
#     return {"all_sections_video_paths": all_sections_video_paths}
#
# semi done
def assemble_final_video(state: AgentState) -> dict[str, Path]:
    """
    This function assembles the final video by concatenating all the clips into one video stream and multiplexing it
    with the audio stream to create a single video file.
    It returns a dictionary with a single key 'final_video_path' whose value is the path to the final video file.
    Parameters:
        state (AgentState): The agent state.
    Returns:
        dict[str, Path]: The final video file path.
    """
    if state.debug_mode:
        print("Assembling final video file...")

    final_video_time_of_creation = datetime.now().strftime("%Y%m%d%H%M%S")
    final_video_path = (
        Path(os.getcwd())
        / "long_form_generated_final_video_files"
        / f"{final_video_time_of_creation}.mp4"
    )
    final_video_path.parent.mkdir(parents=True, exist_ok=True)

    all_sections_video_clips = [
        ffmpeg.input(str(section_video_path))
        for section_video_path in state.all_sections_final_video_paths
    ]

    # ffmpeg.concat(v=1, a=1) expects streams in this order:
    # v1, a1, v2, a2, v3, a3, ...
    all_sections_streams = []
    for section_clip in all_sections_video_clips:
        all_sections_streams.append(section_clip.video)
        all_sections_streams.append(section_clip.audio)

    all_sections_video_clip_concatenated = ffmpeg.concat(
        *all_sections_streams,
        v=1,
        a=1
    ).node

    all_sections_video_stream = all_sections_video_clip_concatenated[0]
    all_sections_audio_stream = all_sections_video_clip_concatenated[1]

    final_output = ffmpeg.output(
        all_sections_video_stream,
        all_sections_audio_stream,
        str(final_video_path),
        vcodec="libx264",
        acodec="aac",          # safer than 'copy' for concat pipelines
        audio_bitrate="192k",
        movflags="+faststart",
    )

    final_output.run(overwrite_output=True)
    return {"final_video_path": final_video_path}

# def assemble_final_video(state: AgentState) -> dict[str, Path]:
#     """
#     This function assembles the final video by concatenating all the clips into one video stream and multiplexing it
#     with the audio stream to create a single video file.
#     It returns a dictionary with a single key 'final_video_path' whose value is the path to the final video file.
#     Parameters:
#         state (AgentState): The agent state.
#     Returns:
#         dict[str, Path]: The final video file path.
#     """
#     if state.debug_mode:
#         print("Assembling final video file...")
#
#     final_video_time_of_creation = datetime.now().strftime("%Y%m%d%H%M%S")
#     final_video_path = Path(os.getcwd()) / "long_form_generated_final_video_files" / f"{final_video_time_of_creation}.mp4"
#     final_video_path.parent.mkdir(parents=True, exist_ok=True)
#
#     all_sections_video_clips = [ffmpeg.input(section_video_path) for section_video_path in
#                                            state.all_sections_final_video_paths]
#
#
#
#     all_sections_video_clip_concatenated = ffmpeg.concat(*all_sections_video_clips, v=1, a=1).node
#     all_sections_video_stream = all_sections_video_clip_concatenated[0]
#     all_sections_audio_stream = all_sections_video_clip_concatenated[1]
#
#
#     final_output = ffmpeg.output(
#         all_sections_video_stream,
#         all_sections_audio_stream,
#         str(final_video_path),
#         vcodec='libx264',
#         acodec='copy',
#         # shortest=None
#     )
#     final_output.run(overwrite_output=True)
#     return {"final_video_path": final_video_path}
#




# def assemble_final_video(state: AgentState) -> dict[str, Path]:
#     """
#     This function assembles the final video by concatenating all the clips into one video stream and multiplexing it
#     with the audio stream to create a single video file.
#     It returns a dictionary with a single key 'final_video_path' whose value is the path to the final video file.
#     Parameters:
#         state (AgentState): The agent state.
#     Returns:
#         dict[str, Path]: The final video file path.
#     """
#     if state.debug_mode:
#         print("Assembling final video file...")
#
#     all_sections_final_video_paths = []
#
#     # Create input streams for each video
#     for section_index, section_video_paths in enumerate(state.all_sections_video_paths):
#         section_time_of_creation = datetime.now().strftime("%Y%m%d%H%M%S")
#         section_final_video_path = Path(os.getcwd()) / "section_generated_final_video_files" / f"{section_time_of_creation}.mp4"
#         section_final_video_path.parent.mkdir(parents=True, exist_ok=True)
#
#
#         section_video_clips = [ffmpeg.input(video_path) for video_path in section_video_paths]
#     # if state.add_end_buffer:
#     #     buffer_video_file_path = ""
#     #     if state.orientation == "Portrait":
#     #         buffer_video_file_path = Path(os.getcwd()) / "utility_assets" / "black_buffer_portrait.mp4"
#     #     else:
#     #         buffer_video_file_path = Path(os.getcwd()) / "utility_assets" / "black_buffer_landscape.mp4"
#     #     video_clips.append(ffmpeg.input(str(buffer_video_file_path)))
#
#     # Concatenate video clips (v=1, a=0 since there is no audio anyway)
#         concatenated = ffmpeg.concat(*section_video_clips, v=1, a=0).node
#         section_video_stream = concatenated[0]
#
#     # Add the audio file
#         section_audio_stream = ffmpeg.input(state.all_sections_generated_audio_file_paths[section_index])
#
#         # Combine video and audio, output to file
#         section_final_output = ffmpeg.output(
#             section_video_stream,
#             section_audio_stream,
#             str(section_final_video_path),
#             vcodec='libx264',
#             acodec='aac',
#             # shortest=None
#         )
#         section_final_output.run(overwrite_output=True)
#         all_sections_final_video_paths.append(section_final_video_path)
#
#     final_video_time_of_creation = datetime.now().strftime("%Y%m%d%H%M%S")
#     final_video_path = Path(os.getcwd()) / "generated_final_video_files" / f"{final_video_time_of_creation}.mp4"
#     final_video_path.parent.mkdir(parents=True, exist_ok=True)
#
#     inputs = [ffmpeg.input(str(p)) for p in all_sections_final_video_paths]
#
#     streams = []
#     for i in inputs:
#         streams += [i.video, i.audio]  # order matters: v1,a1,v2,a2,...
#
#     out = ffmpeg.concat(*streams, v=1, a=1).node
#     out_v, out_a = out[0], out[1]
#
#     (
#         ffmpeg
#         .output(out_v, out_a, str(final_video_path), vcodec="libx264", acodec="aac", pix_fmt="yuv420p")
#         .run(overwrite_output=True)
#     )
#
#     # if state.add_end_buffer:
#     #     buffer_video_file_path = ""
#     #     if state.orientation == "Portrait":
#     #         buffer_video_file_path = Path(os.getcwd()) / "utility_assets" / "black_buffer_portrait.mp4"
#     #     else:
#     #         buffer_video_file_path = Path(os.getcwd()) / "utility_assets" / "black_buffer_landscape.mp4"
#     #     video_clips.append(ffmpeg.input(str(buffer_video_file_path)))
#
#     return {"final_video_path": final_video_path}
#

def should_debug(state: AgentState) -> bool:
    """
    This function returns whether the agent is in debug mode or not.
    Parameters:
        state (AgentState): The agent state.
    Returns:
        bool: Whether the agent is in debug mode or not.
    """
    return state.debug_mode


def debug_graph(state: AgentState):
    """
    """
    # print the text of the whole script list
    pprint(state.script_list)
    print("---------All Clips---------")
    print()
    list_length = len(state.script_list)
    for index in range(list_length):
        print(f"--- Clip {index + 1}---")
        print("Script Segment:\t\t\t", state.script_list[index].get("script_segment"))
        print("Segment Computed Duration:\t\t\t", state.script_segment_durations[index])
        print("Segment Visual Actual Duration:\t\t\t", get_video_duration(str(state.video_paths[index])))
        print("Segment Computed Start Time:\t\t\t", state.script_segment_begin_and_end_times[index][0])
        print("Segment Computed End Time:\t\t\t", state.script_segment_begin_and_end_times[index][1])
        print()
    print("Character Timestamp Lookup Tables")
    for index in range(len(state.generated_audio_characters)):
        print(f"Character: \t\t\t{state.generated_audio_characters[index]}\n"
              f"Start Time:\t\t\t{state.generated_audio_character_start_times[index]}\n"
              f"End Time:\t\t\t{state.generated_audio_character_end_times[index]}\n")


graph_builder = StateGraph(AgentState)
# Node definitions
graph_builder.add_node("resolve_state_values", resolve_agent_state_values)
graph_builder.add_node("generate_goal", generate_goal)
graph_builder.add_node("generate_structure", generate_structure)
graph_builder.add_node("generate_section_scripts", generate_section_scripts)
graph_builder.add_node("segment_section_scripts", segment_section_scripts)
graph_builder.add_node("generate_section_audios", generate_section_audios)
graph_builder.add_node("compute_section_script_timings", compute_section_script_timings)
graph_builder.add_node("generate_segments_image_descriptions", generate_segments_image_descriptions)
graph_builder.add_node("generate_segments_images", generate_segments_images)
graph_builder.add_node("animate_segments_images", animate_segments_images)
graph_builder.add_node("assemble_final_video", assemble_final_video)

graph_builder.add_edge(START, "resolve_state_values")
graph_builder.add_edge("resolve_state_values", "generate_goal")
graph_builder.add_edge("generate_goal", "generate_structure")
graph_builder.add_edge( "generate_structure", "generate_section_scripts")
graph_builder.add_edge("generate_section_scripts", "segment_section_scripts")
graph_builder.add_edge("segment_section_scripts", "generate_section_audios")
graph_builder.add_edge("generate_section_audios", "compute_section_script_timings")
graph_builder.add_edge("compute_section_script_timings", "generate_segments_image_descriptions")
graph_builder.add_edge("generate_segments_image_descriptions", "generate_segments_images")
graph_builder.add_edge("generate_segments_images", "animate_segments_images")
graph_builder.add_edge("animate_segments_images", "assemble_final_video")
graph_builder.add_edge("assemble_final_video", END)
# graph_builder.add_edge("generate_script", "segment_script_segments")
# graph_builder.add_edge("segment_script_segments", "generate_segment_audios")
# graph_builder.add_edge("generate_segment_audios", END)


# graph_builder.add_node("generate_goal", generate_goal)
# graph_builder.add_node("generate_hook", generate_hook)
# graph_builder.add_node("generate_script", generate_script)
# graph_builder.add_node("enhance_script", enhance_script_for_audio_generation)
# graph_builder.add_node("generate_audio", generate_audio)
# graph_builder.add_node("segment_script", segment_script)
# graph_builder.add_node("calculate_script_segment_durations", compute_script_segment_timings)
# graph_builder.add_node("generate_segments_image_descriptions", generate_segments_image_descriptions)
# graph_builder.add_node("generate_segments_images", generate_segments_images)
# graph_builder.add_node("animate_segments_images", animate_segments_images)
# graph_builder.add_node("assemble_final_video", assemble_final_video)
# graph_builder.add_node("debug_graph", debug_graph)
# # Edge definitions
# graph_builder.add_edge(START, "resolve_state_values")
# graph_builder.add_edge("resolve_state_values", "generate_goal")
# graph_builder.add_edge("generate_goal", "generate_hook")
# graph_builder.add_edge("generate_hook", "generate_script")
# graph_builder.add_edge("generate_script", "enhance_script")
# graph_builder.add_edge("enhance_script", "segment_script")
# graph_builder.add_edge("segment_script", "generate_audio")
# graph_builder.add_edge("generate_audio", "calculate_script_segment_durations")
# graph_builder.add_edge("calculate_script_segment_durations", "generate_segments_image_descriptions")
# graph_builder.add_edge("generate_segments_image_descriptions", "generate_segments_images")
# graph_builder.add_edge("generate_segments_images", "animate_segments_images")
# graph_builder.add_edge("animate_segments_images", "assemble_final_video")
# graph_builder.add_conditional_edges(
#     "assemble_final_video",
#     should_debug,
#     {
#         True: "debug_graph",
#         False: END,
#     }
#
# )
# graph_builder.add_edge("merge_visual_and_audio", "debug_graph")
# graph_builder.add_edge("debug_graph", END)
video_creator = graph_builder.compile()

# def split_scripts(state: AgentState) -> dict[str: list[str]]:
# #     """
# #
# #     Parameters:
# #
# #     Returns:
# #
# #     """
# #     model_for_split_script = ai_model.with_structured_output(ScriptContainer)

# def generate_script_multi_shot(state: AgentState) -> dict[str, str]:
#     current_cumulative_multi_shot_script = ""
#
#     # generating script segments for each talking point is done sequentially (not concurrently)because each
#     # segment's generation relies on the portion of the script that has already been generated to improve
#     # the cohesion of the script.
#     for talking_point in state.generated_talking_points:
#         payload = json.dumps({
#             "topic": state.topic,
#             "current_talking_point": talking_point,
#             "goal": state.goal,
#             "hook": state.hook,
#             "purpose": state.purpose,
#             "target_audience": state.target_audience,
#             "tone": state.tone,
#             "auxiliary_requests": state.additional_instructions,
#             "platform": "Instagram and Tiktok",
#             "duration_seconds": state.duration_seconds,
#             "style_reference": state.style_reference,
#             "all_talking_points": state.generated_talking_points,
#             "current_script": current_cumulative_multi_shot_script
#         })
#
#         # We get the portion of the script that was generated
#         script_segment: str = state.generate_script_segment_from_talking_point_for_multi_shot_script_generation(payload)
#         current_cumulative_multi_shot_script += script_segment
#     # now we have the whole script as text.
#     polished_script: str = polish_multi_shot_script(json.dumps({"raw_script": current_cumulative_multi_shot_script}))
#     return {"audio_script": polished_script}
#
#
# def split_scirpt
#     # extract the raw one shot script
#     try:
#         generated_script: str = json.loads(extract_json_from_fence(llm_response)).get("raw_script")
#     except Exception as e:
#         raise FailedParsingError(f"Failed to parse one-shot script from json because of: {e}")
#     # get the enhanced for audio generation version of the script
#     audio_enhanced_script: str = self.enhance_script_for_audio_generation(raw_script=generated_script)
#     # split both the raw and enhanced versions of the script
#     script_list_and_audio_enhanced_script_list: list[dict[str, str]] = self.split_scripts_into_script_lists(raw_script=generated_script, audio_enhanced_script=audio_enhanced_script)
#     # store them in the video object's properties
#     self.script_list = [script_object.get("script_segment", "") for script_object in script_list_and_audio_enhanced_script_list]
#     self.audio_enhanced_script_list = [script_object.get("audio_enhanced_script_segment", "") for script_object in script_list_and_audio_enhanced_script_list]
#     print("[Complete] Generating script one-shot...\n")
#
#
#
#
#
#
#





















