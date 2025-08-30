from google import genai
from dotenv import load_dotenv
import os
from asyncio import Semaphore
load_dotenv()

gemini_client = genai.Client(
    vertexai=True,
    location=os.environ.get("GCP_PROJECT_LOCATION", ""),
    project=os.environ.get("GCP_PROJECT_ID", ""),
)

gemini_semaphore = Semaphore(1)

