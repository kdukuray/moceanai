import openai
from dotenv import load_dotenv
import os
import asyncio

load_dotenv()
openai_client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
openai_semaphore = asyncio.Semaphore(2)
