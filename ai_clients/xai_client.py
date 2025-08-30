from xai_grok_sdk import XAI
from dotenv import load_dotenv
import os
from asyncio import Semaphore

load_dotenv()
xai_client = XAI(
    api_key=os.environ.get("XAI_API_KEY"),
    model="grok-2-1212",
)
xai_semaphore = Semaphore(3)