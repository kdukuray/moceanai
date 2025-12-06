from anthropic import Anthropic
import os
from asyncio import Semaphore
from dotenv import load_dotenv

load_dotenv()

anthropic_client = Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
anthropic_semaphore = Semaphore(3)