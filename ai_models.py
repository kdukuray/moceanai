from enum import Enum

class ImageModel(Enum):
    OPENAI = "OpenAI"
    GEMINI = "Gemini"


class VoiceModel(Enum):
    ELEVENLABS = "ElevenLabs"


class ModelProvider(Enum):
    OPENAI = "OpenAI"
    GEMINI = "Gemini"
    ANTHROPIC = "Anthropic"
    DEEPSEEK = "Deepseek"
    META = "Meta"
    XAI = "XAI"