import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
load_dotenv()

base = os.environ["OLLAMA_BASE_URL"].rstrip("/") + "/v1/"
llm = ChatOpenAI(model=os.environ["OLLAMA_MODEL"], base_url=base,
                 api_key=os.environ["OLLAMA_API_KEY"], streaming=False)
print(llm.invoke("Say hello in two word.").content)