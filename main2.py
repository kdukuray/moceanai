import asyncio

from video import Video
from utils import MediaPlatform, MediaPurpose, MediaTone

async def main():
    # new_vid =Video(
    # central_theme="How Compound Interest Works in 60 Seconds",
    # purpose=MediaPurpose.EDUCATIONAL,
    # target_audience="Young adults new to personal finance",
    # tone=MediaTone.INFORMATIVE,
    # auxiliary_requests="Use captions, upbeat background music, and fast-paced edits. Include a call-to-action at the end.",
    # platform=MediaPlatform.INSTAGRAM_TIKTOK,
    # length=10
    # )
    new_vid = Video(
        central_theme="Why Compostable Bags Are Better for the Environment",
        purpose=MediaPurpose.EDUCATIONAL,
        target_audience="Eco-conscious consumers and young adults interested in sustainability",
        tone=MediaTone.INFORMATIVE,
        auxiliary_requests="Use captions and quick visual comparisons (e.g., compostable vs plastic). Include a call-to-action to switch to compostable bags. make it short(5) topics max. although it is an infomrative video, include a segment that promotes getting compostable bags from 'Go Gryyn' a brand that sells eco friendly alternatives to every day items.",
        platform=MediaPlatform.INSTAGRAM_TIKTOK,
        length=10
    )

    new_vid.generate_topics()
    new_vid.generate_clips()
    for clip in new_vid.clips:
        print("-"*15)
        print(f"🎬 Clip {clip.clip_id}")
        print(f"  ⏱ Duration: {clip.clip_duration_sec} seconds")
        print(f"  🗣 Voice: {clip.voice_presence}")
        print(f"  🎭 Tone: {clip.tone}")
        print(f"  📜 Script:\n    {clip.voice_script}")
        print(f"  🖼 Image Description:\n    {clip.base_image_description}\n")
        print("-" * 15)

    await new_vid.generate_clips_visuals()
    await new_vid.generate_clips_audios()
    new_vid.animate_clips_visuals()
    new_vid.merge_clips_audios_and_visuals()
    new_vid.validate_clips()
    new_vid.merge_all_clips()
    print(f"Final Video path {new_vid.get_final_video_path()}")



asyncio.run(main())