"""
Script generation pipeline: goal -> hook -> script -> enhancement -> segmentation.
Handles both short-form and long-form script workflows.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from v2.core.models import (
    GoalContainer,
    HookContainer,
    ScriptContainer,
    EnhancedScriptContainer,
    ScriptListContainer,
    ScriptSegment,
    SectionsStructureContainer,
    SectionStructure,
    SectionScriptContainer,
    SectionScriptSegmentedContainer,
    SectionScriptSegmentItem,
    SegmentImageDescriptionsContainer,
    ImageDescription,
)
from v2.core.prompts import (
    GOAL_GENERATION_PROMPT,
    HOOK_GENERATION_PROMPT,
    SCRIPT_GENERATION_PROMPT,
    SCRIPT_ENHANCEMENT_PROMPT,
    SCRIPT_SEGMENTATION_PROMPT,
    SEGMENT_IMAGE_DESCRIPTIONS_PROMPT_TEMPLATE,
    FACE_FREE_RULE,
    FACES_ALLOWED_RULE,
    LONG_FORM_STRUCTURE_PROMPT,
    LONG_FORM_SECTION_SCRIPT_PROMPT,
    LONG_FORM_SECTION_SEGMENTER_PROMPT,
)
from v2.services.llm_service import LLMService

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str], None]]


class ScriptGenerator:
    """Orchestrates all LLM-based content generation steps."""

    def __init__(self, provider: str = "google"):
        self.llm = LLMService(provider=provider)

    # ------------------------------------------------------------------
    # SHORT-FORM steps
    # ------------------------------------------------------------------

    def generate_goal(
        self,
        topic: str,
        purpose: str,
        target_audience: str,
        on_progress: ProgressCallback = None,
    ) -> str:
        if on_progress:
            on_progress("Generating video goal...")

        result = self.llm.generate_structured(
            system_prompt=GOAL_GENERATION_PROMPT,
            user_payload={
                "topic": topic,
                "purpose": purpose,
                "target_audience": target_audience,
            },
            output_model=GoalContainer,
        )
        logger.info(f"Goal: {result.goal}")
        return result.goal

    def generate_hook(
        self,
        topic: str,
        purpose: str,
        target_audience: str,
        tone: str,
        platform: str,
        on_progress: ProgressCallback = None,
    ) -> str:
        if on_progress:
            on_progress("Crafting opening hook...")

        result = self.llm.generate_structured(
            system_prompt=HOOK_GENERATION_PROMPT,
            user_payload={
                "topic": topic,
                "purpose": purpose,
                "target_audience": target_audience,
                "tone": tone,
                "platform": platform,
            },
            output_model=HookContainer,
        )
        logger.info(f"Hook: {result.hook}")
        return result.hook

    def generate_script(
        self,
        topic: str,
        goal: str,
        hook: str,
        purpose: str,
        target_audience: str,
        tone: str,
        platform: str,
        duration_seconds: int,
        additional_instructions: str | None = None,
        style_reference: str = "",
        on_progress: ProgressCallback = None,
    ) -> str:
        if on_progress:
            on_progress("Writing narration script...")

        result = self.llm.generate_structured(
            system_prompt=SCRIPT_GENERATION_PROMPT,
            user_payload={
                "topic": topic,
                "goal": goal,
                "hook": hook,
                "purpose": purpose,
                "target_audience": target_audience,
                "tone": tone,
                "additional_requests": additional_instructions,
                "platform": platform,
                "duration_seconds": duration_seconds,
                "style_reference": style_reference,
            },
            output_model=ScriptContainer,
        )
        logger.info(f"Script generated: {len(result.script)} chars")
        return result.script

    def enhance_script(
        self,
        script: str,
        on_progress: ProgressCallback = None,
    ) -> str:
        if on_progress:
            on_progress("Enhancing script for voice generation...")

        result = self.llm.generate_structured(
            system_prompt=SCRIPT_ENHANCEMENT_PROMPT,
            user_payload={"script": script},
            output_model=EnhancedScriptContainer,
        )
        logger.info("Script enhanced for TTS")
        return result.enhanced_script

    def segment_script(
        self,
        script: str,
        enhanced_script: str,
        on_progress: ProgressCallback = None,
    ) -> list[ScriptSegment]:
        if on_progress:
            on_progress("Segmenting script into clips...")

        result = self.llm.generate_structured(
            system_prompt=SCRIPT_SEGMENTATION_PROMPT,
            user_payload={
                "script": script,
                "enhanced_script": enhanced_script,
            },
            output_model=ScriptListContainer,
        )
        logger.info(f"Script segmented into {len(result.script_list)} clips")
        return result.script_list

    def generate_segment_image_descriptions(
        self,
        script_segment: str,
        full_script: str,
        num_images: int,
        image_style: str,
        topic: str,
        tone: str,
        additional_image_requests: str | None = None,
        allow_faces: bool = False,
    ) -> list[ImageDescription]:
        """
        Generate image descriptions for a single script segment.

        Args:
            allow_faces: If True, the prompt allows visible human faces.
                         If False (default), the prompt enforces face-free images.
        """
        # Substitute the face rule placeholder based on the allow_faces setting
        face_rule = FACES_ALLOWED_RULE if allow_faces else FACE_FREE_RULE
        prompt = SEGMENT_IMAGE_DESCRIPTIONS_PROMPT_TEMPLATE.format(face_rule=face_rule)

        result = self.llm.generate_structured(
            system_prompt=prompt,
            user_payload={
                "script_segment": script_segment,
                "full_script": full_script,
                "additional_image_requests": additional_image_requests or "",
                "image_style": image_style,
                "topic": topic,
                "tone": tone,
                "num_of_image_descriptions": num_images,
            },
            output_model=SegmentImageDescriptionsContainer,
        )
        return result.segment_image_descriptions

    # ------------------------------------------------------------------
    # LONG-FORM steps
    # ------------------------------------------------------------------

    def generate_structure(
        self,
        topic: str,
        purpose: str,
        target_audience: str,
        tone: str,
        goal: str,
        on_progress: ProgressCallback = None,
    ) -> list[SectionStructure]:
        if on_progress:
            on_progress("Generating video structure...")

        result = self.llm.generate_structured(
            system_prompt=LONG_FORM_STRUCTURE_PROMPT,
            user_payload={
                "topic": topic,
                "purpose": purpose,
                "target_audience": target_audience,
                "tone": tone,
                "goal": goal,
            },
            output_model=SectionsStructureContainer,
        )
        logger.info(f"Structure generated: {len(result.sections_structure_list)} sections")
        return result.sections_structure_list

    def generate_section_script(
        self,
        topic: str,
        purpose: str,
        target_audience: str,
        tone: str,
        section_info: SectionStructure,
        cumulative_script: str = "",
        additional_instructions: str | None = None,
        style_reference: str = "",
        on_progress: ProgressCallback = None,
    ) -> str:
        if on_progress:
            on_progress(f"Writing script for: {section_info.section_name}...")

        result = self.llm.generate_structured(
            system_prompt=LONG_FORM_SECTION_SCRIPT_PROMPT,
            user_payload={
                "topic": topic,
                "purpose": purpose,
                "target_audience": target_audience,
                "tone": tone,
                "additional_requests": additional_instructions or "",
                "style_reference": style_reference,
                "cumulative_script": cumulative_script,
                "section_information": {
                    "section_name": section_info.section_name,
                    "section_purpose": section_info.section_purpose,
                    "section_directives": section_info.section_directives,
                    "section_talking_points": section_info.section_talking_points,
                },
            },
            output_model=SectionScriptContainer,
        )
        logger.info(f"Section script: {len(result.section_script)} chars")
        return result.section_script

    def segment_section_script(
        self,
        section_script: str,
    ) -> list[SectionScriptSegmentItem]:
        """Split a section script into vocal-unit segments."""
        result = self.llm.generate_structured(
            system_prompt=LONG_FORM_SECTION_SEGMENTER_PROMPT,
            user_payload={"section_script": section_script},
            output_model=SectionScriptSegmentedContainer,
        )
        logger.info(f"Section segmented into {len(result.script_segment_list)} parts")
        return result.script_segment_list
