# agent.py
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pipeline.sql_tool import reset_retry_guard
import os

SYSTEM = (
    "You are an operations assistant. Today is 2026-11-02. "
    "You have run_sql(query, question) for the shop database and tools for "
    "payments/shipping. Write SQL to answer questions about orders and customers.\n\n"
    "IMPORTANT RULES:\n"
    "1. Always pass the user's original question verbatim as the `question` argument.\n"
    "2. If run_sql returns {rejected, problem, suggestion}, read `problem` and "
    "`suggestion` carefully. Change the specific thing named. Never resubmit the "
    "same SQL.\n"
    "3. For 'every/all/only/never' questions, express the aggregation in SQL "
    "using HAVING or NOT EXISTS. Do not pull raw rows and reason in your head.\n"
    "4. Answer from tool results, not prior knowledge."
)

TRACE = []

def get_llm(model_tools=None):
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1/")
    if not base_url.endswith("/v1/"):
        base_url = base_url.rstrip("/") + "/v1/"
    return ChatOpenAI(
        model=os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M"),
        base_url=base_url,
        api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        temperature=0,
        streaming=False,
    ).bind_tools(model_tools)

def main(task: str, tools: list, system_prompt: str):
    reset_retry_guard()
    TRACE.clear()

    llm = get_llm(model_tools=tools)
    tools_by_name = {t.name: t for t in tools}
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=task)]

    for _ in range(12):
        response = llm.invoke(messages)
        messages.append(response)
        if not getattr(response, "tool_calls", None):
            print("\n=== FINAL ===\n", response.content)
            return response.content
        for call in response.tool_calls:
            fn = tools_by_name[call["name"]]
            args = dict(call["args"])
            # inject the original question for run_sql if the model omitted it
            if call["name"] == "run_sql" and not args.get("question"):
                args["question"] = task
            try:
                result = fn.invoke(args)
            except Exception as e:
                result = {"rejected": True, "class": "tool_error",
                          "problem": str(e), "suggestion": "Fix args and retry."}
            TRACE.append({"tool": call["name"], "args": args, "result": result})
            print(f"[tool] {call['name']}({args}) -> {result}")
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    print("\n[hit step limit]")
    return None