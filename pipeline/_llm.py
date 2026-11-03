# pipeline/_llm.py
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm(bind_tools=None):
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1/")
    if not base_url.endswith("/v1/"):
        base_url = base_url.rstrip("/") + "/v1/"
    llm = ChatOpenAI(
        model=os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M"),
        base_url=base_url,
        api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        temperature=0,
        streaming=False,
    )
    return llm.bind_tools(bind_tools) if bind_tools else llm