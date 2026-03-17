from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
import requests
import os

from database import get_db, engine, Base
import models

# DB oluştur
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key="12345"
)

# ENV yükle
load_dotenv()

# OAuth
oauth = OAuth()

oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# ------------------ GOOGLE LOGIN ------------------

@app.get("/login")
async def login(request: Request):
    redirect_uri = "http://127.0.0.1:8000/auth"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth")
async def auth(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")

    # DB'de kullanıcı var mı?
    db_user = db.query(models.User).filter(models.User.email == user_info["email"]).first()

    if not db_user:
        db_user = models.User(
            email=user_info["email"],
            password="google_user"
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

    # SESSION'A KAYDET (EN ÖNEMLİ KISIM)
    request.session["user"] = {
        "id": db_user.id,
        "email": db_user.email,
        "name": user_info["name"]
    }

    return RedirectResponse("/profile")


# ------------------ PROFILE ------------------

@app.get("/profile")
async def profile(request: Request):
    user = request.session.get("user")

    if not user:
        return {"error": "Giriş yok"}

    return HTMLResponse(f"""
        <h1>Hoş geldin {user['name']} 🎉</h1>
        <p>Email: {user['email']}</p>
        <p>User ID: {user['id']}</p>
    """)


# ------------------ SCHEMAS ------------------

class UserCreate(BaseModel):
    email: str
    password: str


class ChatRequest(BaseModel):
    message: str


# ------------------ REGISTER ------------------

@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user.email).first()

    if existing:
        raise HTTPException(status_code=400, detail="Email zaten kayıtlı")

    new_user = models.User(
        email=user.email,
        password=user.password
    )

    db.add(new_user)
    db.commit()

    return {"message": "Kayıt başarılı"}


# ------------------ CHAT (SESSION'LI) ------------------

@app.post("/chat")
def chat(req: ChatRequest, request: Request, db: Session = Depends(get_db)):

    # 🔥 kullanıcıyı session'dan al
    user = request.session.get("user")

    if not user:
        raise HTTPException(status_code=401, detail="Giriş yapmamışsın")

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3",
           "prompt": "Türkçe konuş. " + req.message,
            "stream": False
        }
    )

    data = response.json()
    ai_text = data["response"]

    new_chat = models.Chat(
        user_id=user["id"],  # 🔥 OTOMATİK USER ID
        user_message=req.message,
        ai_response=ai_text
    )

    db.add(new_chat)
    db.commit()

    return {"response": ai_text}


# ------------------ SADECE KENDİ CHATLERİ ------------------

@app.get("/my-chats")
def get_my_chats(request: Request, db: Session = Depends(get_db)):

    user = request.session.get("user")

    if not user:
        raise HTTPException(status_code=401, detail="Giriş yapmamışsın")

    chats = db.query(models.Chat).filter(models.Chat.user_id == user["id"]).all()

    return chats

@app.get("/")
async def home():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Mini ChatGPT</title>
        <style>
            body {
                font-family: Arial;
                background: #0f172a;
                color: white;
            }

            #chat-box {
                height: 400px;
                overflow-y: auto;
                border: 1px solid #333;
                padding: 10px;
                background: #020617;
            }

            .user {
                text-align: right;
                margin: 10px;
            }

            .ai {
                text-align: left;
                margin: 10px;
            }

            .bubble {
                display: inline-block;
                padding: 10px;
                border-radius: 10px;
                max-width: 70%;
            }

            .user .bubble {
                background: #2563eb;
                color: white;
            }

            .ai .bubble {
                background: #1e293b;
            }

            #input-area {
                margin-top: 10px;
            }

            input {
                width: 80%;
                padding: 10px;
                background: #020617;
                border: 1px solid #333;
                color: white;
            }

            button {
                padding: 10px;
                background: #2563eb;
                color: white;
                border: none;
            }

            a {
                color: #38bdf8;
            }
        </style>
    </head>
    <body>

        <h2>Chat 💬</h2>
        <a href="/logout">Çıkış Yap</a>

        <div id="chat-box"></div>

        <div id="input-area">
            <input type="text" id="message" placeholder="Mesaj yaz..." />
            <button onclick="sendMessage()">Gönder</button>
        </div>

        <script>
            async function loadChats() {
                const res = await fetch("/my-chats");
                const data = await res.json();

                const chatBox = document.getElementById("chat-box");

                data.forEach(chat => {
                    addMessage("user", chat.user_message);
                    addMessage("ai", chat.ai_response);
                });
            }

            function addMessage(type, text) {
                const chatBox = document.getElementById("chat-box");

                const div = document.createElement("div");
                div.className = type;

                const bubble = document.createElement("div");
                bubble.className = "bubble";
                bubble.innerText = text;

                div.appendChild(bubble);
                chatBox.appendChild(div);

                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function typeEffect(text, callback) {
                let i = 0;
                function typing() {
                    if (i < text.length) {
                        callback(text.substring(0, i + 1));
                        i++;
                        setTimeout(typing, 15);
                    }
                }
                typing();
            }

            async function sendMessage() {
                const input = document.getElementById("message");
                const message = input.value;

                if (!message) return;

                addMessage("user", message);
                input.value = "";

                const chatBox = document.getElementById("chat-box");

                const loadingDiv = document.createElement("div");
                loadingDiv.className = "ai";

                const loadingBubble = document.createElement("div");
                loadingBubble.className = "bubble";
                loadingBubble.innerText = "AI yazıyor...";

                loadingDiv.appendChild(loadingBubble);
                chatBox.appendChild(loadingDiv);

                const res = await fetch("/chat", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ message: message })
                });

                const data = await res.json();

                chatBox.removeChild(loadingDiv);

                const aiDiv = document.createElement("div");
                aiDiv.className = "ai";

                const bubble = document.createElement("div");
                bubble.className = "bubble";

                aiDiv.appendChild(bubble);
                chatBox.appendChild(aiDiv);

                typeEffect(data.response, (text) => {
                    bubble.innerText = text;
                });
            }

            // 🔥 ENTER ile gönderme
            document.getElementById("message").addEventListener("keydown", function(e) {
                if (e.key === "Enter") {
                    sendMessage();
                }
            });

            loadChats();
        </script>

    </body>
    </html>
    """)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")

