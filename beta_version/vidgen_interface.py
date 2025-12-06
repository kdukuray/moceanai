import streamlit as st

from crud import get_all_profiles
from models import Profile
from beta_version.old_utils import MediaPurpose, MediaTone, MediaPlatform, AspectRatio, ImageStyle
from beta_version.ai_models import ImageModel, VoiceModel, ModelProvider
from video import Video
import asyncio
from beta_version.ai_clients import VoiceActor


voice_actor_options = {
        "American Male - Narrator": VoiceActor.AMERICAN_MALE_NARRATOR,
        "American Male - Conversationalist": VoiceActor.AMERICAN_MALE_CONVERSATIONALIST,
        "American Female - Conversationalist": VoiceActor.AMERICAN_FEMALE_CONVERSATIONALIST,
        "British Male - Narrator": VoiceActor.BRITISH_MALE_NARRATOR,
        "British Female - Narrator": VoiceActor.BRITISH_FEMALE_NARRATOR,
}

image_style_options = {
    "Photo Realism": ImageStyle.PHOTO_REALISM,
    "Hyperrealism": ImageStyle.HYPERREALISM,
    "Cartoon / 2D Illustration": ImageStyle.CARTOON,
    "Minimalist / Flat Illustration": ImageStyle.MINIMALIST,
    "Comic / Manga": ImageStyle.COMIC_MANGA,
    "Cinematic": ImageStyle.CINEMATIC,
    "3D Render / CGI": ImageStyle.RENDER_3D,
    "Fantasy / Surreal": ImageStyle.FANTASY_SURREAL,
    "Vintage / Retro": ImageStyle.VINTAGE_RETRO,
}

# get all the profiles in the app
all_profiles = [profile for profile in get_all_profiles()]

if "current_profile" not in st.session_state:
    st.session_state["current_profile"] = all_profiles[0].name if all_profiles else None

if "topic" not in st.session_state:
    st.session_state["topic"] = ""

if "purpose" not in st.session_state:
    st.session_state["purpose"] = MediaPurpose.EDUCATIONAL.value

if "target_audience" not in st.session_state:
    st.session_state["target_audience"] = ""

if "tone" not in st.session_state:
    st.session_state["tone"] = MediaTone.INFORMATIVE.value

if "platform" not in st.session_state:
    st.session_state["platform"] = MediaPlatform.INSTAGRAM_TIKTOK.value

if "duration_seconds" not in st.session_state:
    st.session_state["duration_seconds"] = 40

if "style_reference" not in st.session_state:
    st.session_state["style_reference"] = ""

if "auxiliary_requests" not in st.session_state:
    st.session_state["auxiliary_requests"] = ""

if "aspect_ratio" not in st.session_state:
    st.session_state["aspect_ratio"] = AspectRatio.PORTRAIT.value

if "model_provider" not in st.session_state:
    st.session_state["model_provider"] = ModelProvider.OPENAI.value

if "image_model" not in st.session_state:
    st.session_state["image_model"] = ImageModel.OPENAI.value

if "animation_probability" not in st.session_state:
    st.session_state["animation_probability"] = 0

if "image_style" not in st.session_state:
    st.session_state["image_style"] = list(image_style_options.keys())[0]  # default first option

if "voice_model" not in st.session_state:
    st.session_state["voice_model"] = VoiceModel.ELEVENLABS.value

if "voice_model_version" not in st.session_state:
    st.session_state["voice_model_version"] = "elevenlabs_multilingual_v2"

if "voice_actor" not in st.session_state:
    st.session_state["voice_actor"] = list(voice_actor_options.keys())[0]  # default first option

if "use_enhanced_script_for_audio_generation" not in st.session_state:
    st.session_state["use_enhanced_script_for_audio_generation"] = True

if "auxiliary_image_requests" not in st.session_state:
    st.session_state["auxiliary_image_requests"] = ""

if "audio_generation_method" not in st.session_state:
    st.session_state["audio_generation_method"] = "one-shot"

if "script_generation_method" not in st.session_state:
    st.session_state["script_generation_method"] = "one-shot"

if "video" not in st.session_state:
    st.session_state["video"] = Video(
        topic=st.session_state["topic"],
        purpose=MediaPurpose.EDUCATIONAL,
        target_audience=st.session_state["target_audience"],
        tone=MediaTone.INFORMATIVE,
        platform=MediaPlatform.INSTAGRAM_TIKTOK,
        duration_seconds=st.session_state["duration_seconds"],
        style_reference=st.session_state["style_reference"],
        auxiliary_requests=st.session_state["auxiliary_requests"],
        aspect_ratio=AspectRatio.PORTRAIT,
        image_model=ImageModel.OPENAI,
        voice_model=VoiceModel.ELEVENLABS
    )



def populate_with_dummy_data():
    # Dummy short-form video profile
    st.session_state["topic"] = "Boost Your Productivity: 3 Morning Hacks to Start Strong"
    st.session_state["purpose"] = "Educational"
    st.session_state["target_audience"] = "Young professionals and college students who want simple daily routines to be more productive"
    st.session_state["tone"] = "Conversational"
    st.session_state["platform"] = "Instagram and Tiktok"
    st.session_state["duration_seconds"] = 45
    st.session_state["style_reference"] = ""
    st.session_state["auxiliary_requests"] = (
        "CTA: 'Follow @DailyFocus on instagram and Tiktok for more productivity hacks'; "
        "Include a quick reminder: 'Consistency matters more than perfection.'"
    )
    st.session_state["aspect_ratio"] = "Portrait"
    st.session_state["model_provider"] = "OpenAI"
    st.session_state["image_model"] = "OpenAI"
    st.session_state["image_style"] = "Photo Realism"
    st.session_state["voice_model"] = "Elevenlabs"
    st.session_state["voice_actor"] = "American Female - Conversationalist"
    st.session_state["auxiliary_image_requests"] = (
        "Use warm, natural palettes (soft neutrals, gentle greens/blues); "
        "ensure text is large and readable; tasteful minimal overlays highlighting each habit."
    )

    st.session_state["audio_generation_method"] = "one-shot"
    st.session_state["script_generation_method"] = "one-shot"


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

    match st.session_state["model_provider"]:
        case "OpenAI":
            video_model_provider = ModelProvider.OPENAI
        case "Gemini":
            video_model_provider = ModelProvider.GEMINI
        case "Meta":
            video_model_provider = ModelProvider.META
        case "Deepseek":
            video_model_provider = ModelProvider.DEEPSEEK
        case "Anthropic":
            video_model_provider = ModelProvider.ANTHROPIC
        case _:
            video_model_provider = ModelProvider.OPENAI

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

    match st.session_state["image_style"]:
        case "Photo Realism":
            image_style = ImageStyle.PHOTO_REALISM
        case "Hyperrealism":
            image_style = ImageStyle.HYPERREALISM
        case "Cartoon / 2D Illustration":
            image_style = ImageStyle.CARTOON
        case "Minimalist / Flat Illustration":
            image_style = ImageStyle.MINIMALIST
        case "Comic / Manga":
            image_style = ImageStyle.COMIC_MANGA
        case "Cinematic":
            image_style = ImageStyle.CINEMATIC
        case "3D Render / CGI":
            image_style = ImageStyle.RENDER_3D
        case "Fantasy / Surreal":
            image_style = ImageStyle.FANTASY_SURREAL
        case "Vintage / Retro":
            image_style = ImageStyle.VINTAGE_RETRO
        case _:
            image_style = ImageStyle.PHOTO_REALISM  # fallback

    new_video = Video(
        topic=st.session_state["topic"],
        purpose=video_purpose,
        target_audience=st.session_state["target_audience"],
        tone=video_tone,
        platform=video_platform,
        duration_seconds=st.session_state["duration_seconds"],
        style_reference=st.session_state["style_reference"],
        auxiliary_requests=st.session_state["auxiliary_requests"],
        use_enhanced_script_for_audio_generation=st.session_state["use_enhanced_script_for_audio_generation"],
        aspect_ratio=video_aspect_ratio,
        model_provider=video_model_provider,
        image_model=video_image_model,
        image_style=image_style,
        voice_model=video_voice_model,
        voice_actor=voice_actor_options[st.session_state["voice_actor"]],
        auxiliary_image_requests=st.session_state["auxiliary_image_requests"],
    )
    st.session_state["video"]: Video = new_video

# modify the mechanism for retrieving profiles later, this works now simply for mvp
def populate_with_profile_data() -> None:
    current_profile_obj: Profile = Profile()
    for profile in all_profiles:
        if st.session_state["current_profile"] == profile.name:
            current_profile_obj = profile
    if current_profile_obj:
        st.session_state["target_audience"] = current_profile_obj.target_audience
        st.session_state["auxiliary_requests"] = f"This piece of content is designed for the {current_profile_obj.name} social page, so be sure to include a strong call-to-action at the end"


# Streamlit UI
st.title("MoceanAI Short-Form Vid Gen")
st.divider()

st.header("Video Information")
col1, col2 = st.columns(2)
with col1:
    if st.button("Populate Default"):
        current_profile = st.session_state["current_profile"]
        populate_with_dummy_data()


with col2:
    st.selectbox(label="Choose Profile", options=[profile.name for profile in all_profiles], key="current_profile", on_change=populate_with_profile_data)


if st.session_state["current_profile"]:
    st.target_audience = ""

topic = st.text_input("Topic", key="topic")
purpose = st.selectbox(label="Purpose", options=[purpose.value for purpose in MediaPurpose], key="purpose")
target_audience = st.text_input("Target Audience", key="target_audience")
tone = st.selectbox(label="Tone", options=[tone.value for tone in MediaTone], key="tone")
platform = st.selectbox(label="Platform", options=[platform.value for platform in MediaPlatform], key="platform")
duration_seconds = st.slider(label="Duration (secs)", min_value=1, max_value=120, key="duration_seconds")
style_reference = st.text_input("Style Reference", key="style_reference")
auxiliary_requests = st.text_area(label="Auxiliary Requests", key="auxiliary_requests")
aspect_ratio = st.selectbox(label="Aspect Ratio", options=[aspect_ratio.value for aspect_ratio in AspectRatio], key="aspect_ratio")
model_provider = st.selectbox(label="Model Provider", options=[model_provider.value for model_provider in ModelProvider], key="model_provider")
image_model = st.selectbox(label="Image Model", options=[image_model.value for image_model in ImageModel], key="image_model")
animation_probability = st.slider(label="Animation Probability", min_value=0, max_value=10, key="animation_probability")
image_style = st.selectbox(label="Image Style", options=image_style_options.keys(), key="image_style")
voice_model = st.selectbox(label="Voice Model", options=[voice_model.value for voice_model in VoiceModel], key="voice_model")
voice_model_version = st.selectbox(label="Voice Model Version", options=["elevenlabs_multilingual_v2", "elevenlabs_v3"], key="voice_model_version")
voice_actor  = st.selectbox(label="Voice Actor", options=voice_actor_options.keys(), key="voice_actor")
use_enhanced_script_for_audio_generation = st.toggle(label="use enhanced script for audio", key="use_enhanced_script_for_audio_generation")

one_or_multi_shot = ["one-shot", "multi-shot"]
audio_generation_method = st.selectbox(label="Audio Generation Method", options=one_or_multi_shot, key="audio_generation_method")
script_generation_method = st.selectbox(label="Script Generation Method", options=one_or_multi_shot, key="script_generation_method")

if st.button("Create Video BluePrint"):
    create_video()

if st.session_state.video.topics:
    if st.button("Generate Video"):
        with st.spinner("Generating Video..."):
            asyncio.run(st.session_state.video.generate_video(audio_generation_method=audio_generation_method,
                                                              script_generation_method=script_generation_method,
                                                              ))

if st.session_state.video.final_video_path:
    final_video_path = st.session_state.video.get_final_video_path()
    st.video(final_video_path)
    if st.session_state.video.video_caption:
        st.write(st.session_state.video.video_caption)



