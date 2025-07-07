import os
import json
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def detect_intent_and_extract(user_input):
    """
    Determine intent (file_search/general_response) and extract clean search query if needed.
    Removes filler words like 'related file', 'document', 'info', etc.
    """
    system_prompt = (
        "You are an AI assistant for a file search application. Your job is to detect user intent and extract the core file keyword(s).\n"
        "You MUST reply in this strict JSON format only:\n"
        "{\"intent\": \"file_search\", \"data\": \"anup\"}\n"
        "OR\n"
        "{\"intent\": \"general_response\", \"data\": \"\"}\n\n"
        "Guidelines:\n"
        "- If the user is trying to locate or mention a document, file, or content type, return 'file_search'.\n"
        "- Extract only the specific topic, name, or keywords (e.g., 'anup', 'ai agent').\n"
        "- Remove filler words like: file, document, report, info, details, data, related, about, on, regarding, sheet, record, etc.\n"
        "- Use lowercase for all keywords but preserve proper names (e.g., 'Anup').\n"
        "- If the input is a greeting or a general question, return 'general_response'.\n"
        "- NEVER return anything except the JSON format.\n\n"
        "Now analyze this input:\n"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt + user_input}
            ],
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print("❌ GPT Error (intent detection):", e)
        return {"intent": "general_response", "data": ""}


def answer_general_query(user_input):
    """
    Use GPT to answer general (non-search) questions.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Respond clearly to user questions."},
                {"role": "user", "content": user_input}
            ],
            temperature=0.5
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("❌ GPT Error (general query):", e)
        return "⚠️ I'm having trouble answering that. Please try again later."
