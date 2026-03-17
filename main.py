import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from openai import OpenAI

# .env yükle
load_dotenv()

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# Ana sayfa (chat arayüzü)
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
    <head>
        <title>AI Chat</title>
        <style>
            body {
                background: #121212;
                color: white;
                font-family: Arial;
                text-align: center;
            }
            input {
                padding: 10px;
                width: 300px;
                border-radius: 10px;
                border: none;
            }
            button {
                padding: 10px;
                border-radius: 10px;
                border: none;
                cursor: pointer;
            }
        </style>
    </head>
    <body>
        <h1>AI Chat 🤖</h1>
        <input id="msg" placeholder="Bir şey yaz...">
        <button onclick="send()">Gönder</button>
        <p id="res"></p>

        <script>
            async function send() {
                let msg = document.getElementById("msg").value;

                let res = await fetch("/chat", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({message: msg})
                });

                let data = await res.json();
                document.getElementById("res").innerText = data.reply;
            }

            // ENTER ile gönderme
            document.getElementById("msg").addEventListener("keypress", function(e) {
                if (e.key === "Enter") {
                    send();
                }
            });
        </script>
    </body>
    </html>
    """

# Chat endpoint
@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_message = data["message"]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Sen Türkçe konuşan yardımcı bir asistansın."},
            {"role": "user", "content": user_message}
        ]
    )

    reply = response.choices[0].message.content

    return {"reply": reply}
