from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

ai_model = init_chat_model(model_provider="google-genai", model="gemini-3-pro-preview")
class structured_output(BaseModel):
    num_ls: int = Field(..., description="Number of l's in the text")
sys_prompt = SystemMessage(content="You are a model that return the number l's in a given text.")
response: BaseModel = ai_model.with_structured_output(structured_output).invoke([sys_prompt, HumanMessage(content="lllll")])
print(response)
print(type(response))
print(response.model_dump())
print(response)

# import asyncio
# import pprint
#
# from long_form_content import video_creator
# import pprint
#
# payload = {
#     "topic": "How to Repair Your Credit Fast",
#     "purpose": "Educational",
#     "target_audience": "People with low or damaged credit scores",
#     "type": "Short-form",
#     "tone": "Informative",
#     "platform": "TikTok",
#     "duration_seconds": 600,
#     "orientation": "Portrait",
#     "model_provider": "google",
#     "image_model": "google",
#     "image_style": "Hyperrealism",
#     "voice_actor": "american_female_conversationalist",
#     "enhance_script_for_audio_generation": False,
#     "debug_mode": True
# }
#
# async def main():
#     end_state = video_creator.ainvoke(payload)
#     pprint.pprint(end_state)
#
# if __name__ == "__main__":
#     asyncio.run(main())
# from crud import get_all_profiles
# all_profiles = get_all_profiles()
# print([profile.name for profile in get_all_profiles()])
# fresh start legal, pristine

# import ffmpeg
# from pathlib import Path
#
#
# black_image = Path("pitch.png")
# output_dir = Path("utility_assets")
# output_dir.mkdir(exist_ok=True)
#
#
# def create_black_buffer(black_image: Path, width: int, height: int, output_path: Path):
#     """
#     Create a black 5-second buffer video at the given resolution.
#     """
#     (
#         ffmpeg
#         .input(str(black_image), loop=1, t=5, framerate=30)
#         .filter("scale", width, height)
#         .filter("setsar", 1)
#         .output(
#             str(output_path),
#             vcodec="libx264",
#             pix_fmt="yuv420p",
#             r=30,
#             **{"metadata:s:v:0": "rotate=0"},
#         )
#         .run(overwrite_output=True)
#     )
#
#
# def main():
#     # PORTRAIT: 1080 × 1920
#     create_black_buffer(
#         black_image,
#         width=1080,
#         height=1920,
#         output_path=output_dir / "black_buffer_portrait.mp4"
#     )
#
#     # LANDSCAPE: 1920 × 1080
#     create_black_buffer(
#         black_image,
#         width=1920,
#         height=1080,
#         output_path=output_dir / "black_buffer_landscape.mp4"
#     )
#
#     print("✔ Black buffers generated successfully!")
#
#
# if __name__ == "__main__":
#     main()
