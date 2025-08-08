import enum

from elevenlabs import ElevenLabs
import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()
elevenlabs_client = ElevenLabs(api_key=os.getenv("ELEVEN_LABS_API_KEY"), httpx_client=httpx.Client(timeout=httpx.Timeout(60.0)))
elevenlabs_semaphore = asyncio.Semaphore(3)


class VoiceActor(enum.Enum):
    AMERICAN_MALE_NARRATOR = "Dslrhjl3ZpzrctukrQSN" # BRAD
    AMERICAN_MALE_CONVERSATIONALIST = "UgBBYS2sOqTuMpoF3BR0" # MARK
    AMERICAN_FEMALE_CONVERSATIONALIST = "uYXf8XasLslADfZ2MB4u" # HOPE
    BRITISH_MALE_NARRATOR = "giAoKpl5weRTCJK7uB9b" # OWEN
    BRITISH_FEMALE_NARRATOR = "1hlpeD1ydbI2ow0Tt3EW" # ORACLE X




