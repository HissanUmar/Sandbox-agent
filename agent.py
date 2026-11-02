# agent.py
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from agent_tools import TOOLS
from dotenv import load_dotenv
load_dotenv()



SYSTEM = (
    "You are an operations assistant. You have tools to query a shop database "
    "and to call payments and shipping APIs. Use them to complete the user's task. "
    "When you are done, reply with a short summary of what you did."
)

def _llm():
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1/")
    if not base_url.endswith("/v1/"):
        base_url = base_url.rstrip("/") + "/v1/"
    return ChatOpenAI(
        model=os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M"),
        base_url=base_url,
        api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        temperature=0,
        streaming=False,
    ).bind_tools(TOOLS)

def main(task: str):
    llm = _llm()
    tools_by_name = {t.name: t for t in TOOLS}
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=task)]

    for step in range(8):                      # cap the loop
        response = llm.invoke(messages)
        messages.append(response)
        if not getattr(response, "tool_calls", None):
            print("\n=== FINAL ===\n", response.content)
            return response.content
        for call in response.tool_calls:
            tool_fn = tools_by_name[call["name"]]
            result = tool_fn.invoke(call["args"])
            print(f"[tool] {call['name']}({call['args']}) -> {result}")
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    print("\n[hit step limit]")
    return None