import re
from enum import Enum

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