import streamlit as st
from utils import MediaPurpose, MediaTone, MediaPlatform, AspectRatio
from ai_models import ImageModel, VoiceModel
from video import Video
import asyncio
from elevenlabs_client import VoiceActor

voice_actor_options = {
        "American Male - Narrator": VoiceActor.AMERICAN_MALE_NARRATOR,
        "American Male - Conversationalist": VoiceActor.AMERICAN_MALE_CONVERSATIONALIST,
        "American Female - Conversationalist": VoiceActor.AMERICAN_FEMALE_CONVERSATIONALIST,
        "British Male - Narrator": VoiceActor.BRITISH_MALE_NARRATOR,
        "British Female - Narrator": VoiceActor.BRITISH_FEMALE_NARRATOR,
    }


if "central_theme" not in st.session_state:
    st.session_state["central_theme"] = ""
if "purpose" not in st.session_state:
    st.session_state["purpose"] = "Educational"
if "target_audience" not in st.session_state:
    st.session_state["target_audience"] = ""
if "tone" not in st.session_state:
    st.session_state["tone"] = "Informative"
if "platform" not in st.session_state:
    st.session_state["platform"] = "Instagram and Tiktok"
if "length" not in st.session_state:
    st.session_state["length"] = 30
if "style_reference" not in st.session_state:
    st.session_state["style_reference"] = ""
if "auxiliary_requests" not in st.session_state:
    st.session_state["auxiliary_requests"] = ""
if "aspect_ratio" not in st.session_state:
    st.session_state["aspect_ratio"] = "PORTRAIT"
if "image_model" not in st.session_state:
    st.session_state["image_model"] = "OPENAI"
if "voice_model" not in st.session_state:
    st.session_state["voice_model"] = "ELEVENLABS"
if "voice_actor" not  in st.session_state:
    st.session_state["voice_actor"] = "American Male - Narrator"
if "video" not in st.session_state:
    st.session_state["video"] = Video(
        central_theme="",
        purpose=MediaPurpose.EDUCATIONAL,
        target_audience="",
        tone=MediaTone.INFORMATIVE,
        platform=MediaPlatform.INSTAGRAM_TIKTOK,
        length=0,
        style_reference="",
        auxiliary_requests="",
        aspect_ratio=AspectRatio.PORTRAIT,
        image_model=ImageModel.OPENAI,
        voice_model=VoiceModel.ELEVENLABS
    )


def populate_with_dummy_data():
    st.session_state["central_theme"] = "Why Compostable Bags Are Better for the Environment"
    st.session_state["purpose"] = "Educational"
    st.session_state["target_audience"] = "Eco-conscious consumers and young adults interested in sustainability"
    st.session_state["tone"] = "Informative"
    st.session_state["platform"] = "Instagram and Tiktok"
    st.session_state["length"] = 20
    st.session_state["style_reference"] = ""
    st.session_state["auxiliary_requests"] = (
        "Use captions and quick visual comparisons (e.g., compostable vs plastic). "
        "Include a call-to-action to switch to compostable bags. "
        "Make it short (5 topics max). "
        "Although it is an informative video, include a segment that promotes getting compostable bags from 'Go Gryyn'—"
        "a brand that sells eco-friendly alternatives to everyday items."
    )
    st.session_state["aspect_ratio"] = "PORTRAIT"
    st.session_state["image_model"] = "OPENAI"
    st.session_state["voice_model"] = "ELEVENLABS"
    st.session_state["voice_actor"] = "American Male - Narrator"

def create_video():
    match st.session_state["purpose"]:
        case "Educational":
            video_purpose = MediaPurpose.EDUCATIONAL
        case "Promotional":
            video_purpose = MediaPurpose.PROMOTIONAL
        case "SocialMediaContent":
            video_purpose = MediaPurpose.SOCIAL_MEDIA_CONTENT
        case "Awareness":
            video_purpose = MediaPurpose.AWARENESS
        case "Storytelling":
            video_purpose = MediaPurpose.STORYTELLING
        case "Motivational":
            video_purpose = MediaPurpose.MOTIVATIONAL
        case "Tutorial":
            video_purpose = MediaPurpose.TUTORIAL
        case "News":
            video_purpose = MediaPurpose.NEWS
        case "Entertainment":
            video_purpose = MediaPurpose.Entertainment
        case _:
            video_purpose = MediaPurpose.EDUCATIONAL

    match st.session_state["tone"]:
        case "Informative":
            video_tone = MediaTone.INFORMATIVE
        case "Conversational":
            video_tone = MediaTone.CONVERSATIONAL
        case "Professional":
            video_tone = MediaTone.PROFESSIONAL
        case "Inspirational":
            video_tone = MediaTone.INSPIRATIONAL
        case "Humorous":
            video_tone = MediaTone.HUMOROUS
        case "Dramatic":
            video_tone = MediaTone.DRAMATIC
        case "Empathetic":
            video_tone = MediaTone.EMPATHETIC
        case "Persuasive":
            video_tone = MediaTone.PERSUASIVE
        case "Narrative":
            video_tone = MediaTone.NARRATIVE
        case "Neutral":
            video_tone = MediaTone.NEUTRAL
        case _:
            video_tone = MediaTone.INFORMATIVE

    match st.session_state["platform"]:
        case "Instagram and Tiktok":
            video_platform = MediaPlatform.INSTAGRAM_TIKTOK
        case "YouTube":
            video_platform = MediaPlatform.YOUTUBE
        case _:
            video_platform = MediaPlatform.INSTAGRAM_TIKTOK

    match st.session_state["aspect_ratio"]:
        case "Landscape":
            video_aspect_ratio = AspectRatio.LANDSCAPE
        case "Portrait":
            video_aspect_ratio = AspectRatio.PORTRAIT
        case _:
            video_aspect_ratio = AspectRatio.PORTRAIT

    match st.session_state["image_model"]:
        case "OpenAI":
            video_image_model = ImageModel.OPENAI
        case "Gemini":
            video_image_model = ImageModel.GEMINI
        case _:
            video_image_model = ImageModel.OPENAI

    match st.session_state["voice_model"]:
        case "ElevenLabs":
            video_voice_model = VoiceModel.ELEVENLABS
        case _:
            video_voice_model = VoiceModel.ELEVENLABS



    new_video = Video(
        central_theme=st.session_state["central_theme"],
        purpose=video_purpose,
        target_audience=st.session_state["target_audience"],
        tone=video_tone,
        platform=video_platform,
        length=st.session_state["length"],
        style_reference=st.session_state["style_reference"],
        auxiliary_requests=st.session_state["auxiliary_requests"],
        aspect_ratio=video_aspect_ratio,
        image_model=video_image_model,
        voice_model=video_voice_model,
        voice_actor=voice_actor_options[st.session_state["voice_actor"]],
    )
    st.session_state["video"]: Video = new_video


# Streamlit UI
st.title("SimmAI Content Generation APP")
st.divider()


st.header("Video Information")
if st.button("Populate Default"):
    populate_with_dummy_data()

central_theme = st.text_input("Central Theme", key="central_theme")
purpose = st.selectbox(label="Purpose", options=[purpose.value for purpose in MediaPurpose], key="purpose")
target_audience = st.text_input("Target Audience", key="target_audience")
tone = st.selectbox(label="Tone", options=[tone.value for tone in MediaTone], key="tone")
platform = st.selectbox(label="Platform", options=[platform.value for platform in MediaPlatform], key="platform")
length = st.slider(label="Length (secs)", min_value=1, max_value=120, key="length")
style_reference = st.text_input("Style Reference", key="style_reference")
auxiliary_requests = st.text_area(label="Auxiliary Requests", key="auxiliary_requests")
aspect_ratio = st.selectbox(label="Aspect Ratio", options=[aspect_ratio.value for aspect_ratio in AspectRatio], key="aspect_ratio")
image_model = st.selectbox(label="Image Model", options=[image_model.value for image_model in ImageModel], key="image_model")
voice_model = st.selectbox(label="Voice Model", options=[voice_model.value for voice_model in VoiceModel], key="voice_model")
voice_actor  = st.selectbox(label="Voice Actor", options=voice_actor_options.values(), key="voice_actor")

if st.button("Create Video BluePrint"):
    create_video()

if st.session_state.video.central_theme:
    if st.button("Generate Video"):
        with st.spinner("Generating Video..."):
            asyncio.run(st.session_state.video.generate_video())


if st.session_state.video.final_video_path:
    final_video_path = st.session_state.video.get_final_video_path()
    st.video(final_video_path)



