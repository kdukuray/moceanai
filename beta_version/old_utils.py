import re
from enum import Enum

from beta_version.ai_models import ModelProvider
from beta_version.ai_clients.openai_client import openai_client
from beta_version.ai_clients import gemini_client
from beta_version.ai_clients import anthropic_client
from beta_version.ai_clients import xai_client
from google.genai.types import GenerateContentConfig
from typing import Literal



default_models_for_model_providers = {
    ModelProvider.OPENAI: "gpt-4o",
    ModelProvider.ANTHROPIC: "claude-4-opus-20250514",
    ModelProvider.GEMINI: "gemini-2.5-pro",
    ModelProvider.XAI: "",
    ModelProvider.DEEPSEEK: ""
}


def extract_json_from_fence(text):
    return re.sub(r"^```json\s*|\s*```$", "", text.strip(), flags=re.DOTALL)

class MediaPlatform(Enum):
    INSTAGRAM_TIKTOK = "Instagram and Tiktok"
    YOUTUBE = "YouTube"

class MediaPurpose(Enum):
    EDUCATIONAL = "Educational"
    PROMOTIONAL = "Promotional"
    SOCIAL_MEDIA_CONTENT = "SocialMediaContent"
    AWARENESS = "Awareness"
    STORYTELLING = "Storytelling"
    MOTIVATIONAL = "Motivational"
    TUTORIAL = "Tutorial"
    NEWS = "News"
    Entertainment = "Entertainment"


class MediaTone(Enum):
    INFORMATIVE = "Informative"
    CONVERSATIONAL = "Conversational"
    PROFESSIONAL = "Professional"
    INSPIRATIONAL = "Inspirational"
    HUMOROUS = "Humorous"
    DRAMATIC = "Dramatic"
    EMPATHETIC = "Empathetic"
    PERSUASIVE = "Persuasive"
    NARRATIVE = "Narrative"
    NEUTRAL = "Neutral"

class AspectRatio(Enum):
    LANDSCAPE = "Landscape"
    PORTRAIT = "Portrait"


class ImageStyle(Enum):
    PHOTO_REALISM = "Photo Realistic; Lifelike but natural."
    HYPERREALISM = "Hyper Realistic; Ultra-detailed, sharp, heightened 'more real than real.'"
    CARTOON = "Cartoonish; Fun, approachable, good for explainers."
    MINIMALIST = "Minimalistic; Clean, simple, vector-based."
    COMIC_MANGA = "Comic Manga; Bold lines, stylized, storytelling focus."
    CINEMATIC = "Cinematic; Film-like, dramatic lighting and grading."
    RENDER_3D = "3D Rendered; Polished 3D models and animations."
    FANTASY_SURREAL = "Fantasy Surreal; Dreamlike, imaginative, otherworldly."
    VINTAGE_RETRO = "Vintage Retro; Nostalgic, grainy, old-school vibe."


def invoke_llm(user_input: str, system_instruction: str, model_provider: ModelProvider = ModelProvider.OPENAI, model: Literal["gpt-4o", "gemini-2.5-pro", "claude-4-opus-20250514", "gpt-5"] | None = None) -> str:
    # if no model is specified, simply use the default model for the given model provider
    if not model:
        model = default_models_for_model_providers[model_provider]
    output = ""
    match model_provider:
        case ModelProvider.OPENAI:
            # add check to verify model
            messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_input}]
            openai_response = openai_client.chat.completions.create(
                model=model,
                messages=messages,
            )
            output = openai_response.choices[0].message.content
        case ModelProvider.GEMINI:
            gemini_response = gemini_client.models.generate_content(
                model=model,
                contents=user_input,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                )
            )
            output = gemini_response.text
        case ModelProvider.ANTHROPIC:
            messages = [{"role": "user", "content": user_input}]
            anthropic_response = anthropic_client.messages.create(
                model=model,
                system=system_instruction,
                max_tokens=1024,
                messages=messages,
            )
            output = anthropic_response.content.text
        case ModelProvider.DEEPSEEK:
            pass
        case ModelProvider.XAI:
            messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_input}]
            xai_response = xai_client.invoke(
                messages=messages,
            )
            output = xai_response.choices[0].message.content
        case _ :
            # add check to verify model
            messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": user_input}]
            openai_response = openai_client.chat.completions.create(
                model=model,
                messages=messages,
            )
            output = openai_response.choices[0].message.content


    return output
