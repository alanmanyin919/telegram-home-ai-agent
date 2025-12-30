import json
import requests

SYSTEM_PROMPT = """You are a personal task assistant.
Decide if the user message is about todo tasks.

If it is task-related, respond ONLY with valid JSON in this schema:
{
  "intent": "add_task" | "list_tasks" | "complete_task" | "none",
  "task": string | null,
  "id": number | null
}

Rules:
- If user asks to add a task/reminder: intent=add_task, task=short title.
- If user asks to list/show tasks: intent=list_tasks.
- If user asks to complete/finish/mark done with a number: intent=complete_task, id=that number.
- Otherwise intent=none.
No extra keys. No commentary. JSON only.
"""


def classify_message(ollama_url: str, model: str, user_text: str) -> dict:
    prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_text}\nAssistant:"
    r = requests.post(
        f"{ollama_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    r.raise_for_status()
    raw = r.json()["response"].strip()

    # Try to parse JSON robustly (sometimes models add whitespace/newlines)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat as normal chat
        return {"intent": "none", "task": None, "id": None}


def chat(ollama_url: str, model: str, user_text: str) -> str:
    prompt = f"You are a helpful assistant.\nUser: {user_text}\nAssistant:"
    r = requests.post(
        f"{ollama_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["response"].strip()
