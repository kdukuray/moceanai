from enum import Enum

class ImageModel(Enum):
    OPENAI = "OpenAI"
    GEMINI = "Gemini"


class VoiceModel(Enum):
    ELEVENLABS = "ElevenLabs"
