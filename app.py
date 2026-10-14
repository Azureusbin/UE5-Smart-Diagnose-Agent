import os
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

MODEL_TEXT = os.getenv("MODEL_TEXT")
MODEL_VISION = os.getenv("MODEL_VISION")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_API_URL"))