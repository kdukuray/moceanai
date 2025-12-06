from short_form_content import video_creator
import asyncio

test_payload = {
    "topic": "How AI Can Reduce Classroom Workload",
    "purpose": "Educational",
    "target_audience": "Teachers",
    "type": "Short-form",
    "tone": "Informative",
    "platform": "TikTok",
    "duration_seconds": 60,
    "orientation": "Portrait",
    "model_provider": "google",
    "image_model": "google",
    "image_style": "Hyperrealism",
    "voice_actor": "american_female_conversationalist",
    "enhance_script_for_audio_generation": False
}
test_payload = {
    "topic": "How to Repair Your Credit Fast",
    "purpose": "Educational",
    "target_audience": "People with low or damaged credit scores",
    "type": "Short-form",
    "tone": "Informative",
    "platform": "TikTok",
    "duration_seconds": 60,
    "orientation": "Portrait",
    "model_provider": "google",
    "image_model": "google",
    "image_style": "Hyperrealism",
    "voice_actor": "american_female_conversationalist",
    "enhance_script_for_audio_generation": False,
    "debug_mode": True
}

end_state = asyncio.run(video_creator.ainvoke(test_payload))
print(end_state.get("final_video_path"))

