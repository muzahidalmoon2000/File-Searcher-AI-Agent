from flask import Flask, render_template, request, redirect, session, jsonify
from flask_session import Session
from dotenv import load_dotenv
import os
import msal
from auth.msal_auth import get_token_from_cache
from graph_api import (
    search_all_files,
    check_file_access,
    send_notification_email,
    send_multiple_file_email
)
from openai_api import detect_intent_and_extract, answer_general_query

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("CLIENT_SECRET")

# Enable server-side sessions
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
Session(app)

@app.route("/")
def home():
    if not session.get("user_email"):
        return redirect("/login")
    session['stage'] = 'start'
    session['found_files'] = []
    return render_template("chat.html")

@app.route("/login")
def login():
    msal_app = msal.ConfidentialClientApplication(
        os.getenv("CLIENT_ID"),
        authority=os.getenv("AUTHORITY"),
        client_credential=os.getenv("CLIENT_SECRET")
    )
    auth_url = msal_app.get_authorization_request_url(
        scopes=os.getenv("SCOPE").split(),
        redirect_uri=os.getenv("REDIRECT_URI")
    )
    return redirect(auth_url)

@app.route("/getAToken")
def authorized():
    code = request.args.get("code")
    if not code:
        return "Authorization failed", 400
    msal_app = msal.ConfidentialClientApplication(
        os.getenv("CLIENT_ID"),
        authority=os.getenv("AUTHORITY"),
        client_credential=os.getenv("CLIENT_SECRET")
    )
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=os.getenv("SCOPE").split(),
        redirect_uri=os.getenv("REDIRECT_URI")
    )
    session["token"] = result["access_token"]
    session["user_email"] = result.get("id_token_claims", {}).get("preferred_username")
    return redirect("/")

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "").strip()
    is_selection = request.json.get("selectionStage", False)

    token = session.get("token")
    user_email = session.get("user_email")
    stage = session.get("stage", "start")

    if not token or not user_email:
        return jsonify(response="❌ You are not logged in.")

    if is_selection or (stage == "awaiting_selection" and is_number_selection(user_input)):
        return handle_file_selection(user_input, token, user_email)

    if stage == "start":
        session["stage"] = "awaiting_query"
        return jsonify(response="Hi there! 👋\nWhat file are you looking for today or how can I help?")

    elif stage == "awaiting_query":
        gpt_result = detect_intent_and_extract(user_input)
        intent = gpt_result.get("intent")
        query = gpt_result.get("data")
        print(f"🔍 GPT intent: {intent} | query: {query}")

        if intent == "general_response":
            gpt_reply = answer_general_query(user_input)
            return jsonify(response=gpt_reply)

        elif intent == "file_search" and query:
            session["last_query"] = query
            files = search_all_files(token, query)
            top_files = files[:5]
            session["found_files"] = top_files

            if not top_files:
                return jsonify(response="📁 No files found for your request. Try being more specific.")

            exact_matches = [f for f in top_files if f["name"].lower() == query.lower()]
            if exact_matches:
                file = exact_matches[0]
                has_access = check_file_access(token, file['id'], user_email, file.get("parentReference", {}).get("siteId"))
                session["stage"] = "awaiting_query"
                if has_access:
                    send_notification_email(token, user_email, file['name'], file['webUrl'])
                    return jsonify(response=f"✅ You have access! Here’s your file link: {file['webUrl']}\n📧 Sent to your email: {user_email}\n\n💬 Do you need anything else?")
                else:
                    return jsonify(response="❌ You don’t have access to this file.")
            else:
                session["stage"] = "awaiting_selection"
                file_list = "\n".join([f"{i+1}. {f['name']}" for i, f in enumerate(top_files)])
                return jsonify(response=f"Here are some files I found:\n{file_list}\n\nPlease select the files you want:")

        else:
            return jsonify(response="⚠️ I couldn’t understand your request. Please rephrase or provide more detail.")

    return jsonify(response="⚠️ Something went wrong. Please try again.")

def handle_file_selection(user_input, token, user_email):
    user_input_cleaned = user_input.strip().lower()

    if user_input_cleaned == "cancel":
        session["stage"] = "awaiting_query"
        return jsonify(response="❌ Selection cancelled. What else can I help you with?")

    selected_indices = [s.strip() for s in user_input_cleaned.split(',') if s.strip().isdigit()]
    selected_indices = list(set([int(i) - 1 for i in selected_indices if i.isdigit()]))

    files = session.get("found_files", [])

    print("🔎 Selected indices:", selected_indices)
    print("📁 Session files:", [f['name'] for f in files])

    if not files:
        session["stage"] = "awaiting_query"
        return jsonify(response="⚠️ The file list has expired. Please try your query again.")

    if not selected_indices or any(i < 0 or i >= len(files) for i in selected_indices):
        return jsonify(response="❌ Invalid selection. Please enter valid numbers separated by commas (e.g., 1, 3).")

    selected_files = [files[i] for i in selected_indices]
    accessible_files = []

    for file in selected_files:
        has_access = check_file_access(token, file['id'], user_email, file.get("parentReference", {}).get("siteId"))
        if has_access:
            accessible_files.append(file)

    session["stage"] = "awaiting_query"

    if not accessible_files:
        return jsonify(response="❌ You don’t have access to any of the selected files.")

    send_multiple_file_email(token, user_email, accessible_files)

    links = "\n".join([f"🔗 {file['name']}: {file['webUrl']}" for file in accessible_files])
    return jsonify(response=f"✅ You have access to the following files:\n{links}\n\n📧 Sent to your email: {user_email}\n\n💬 Need anything else?")

def is_number_selection(text):
    try:
        parts = [s.strip() for s in text.split(',')]
        return all(part.isdigit() for part in parts)
    except:
        return False

if __name__ == "__main__":
    app.run(debug=True)