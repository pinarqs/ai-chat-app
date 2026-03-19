print("APP BAŞLADI")

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
import os

from database import get_db, engine, Base
import models

# DB oluştur
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Session
app.add_middleware(
    SessionMiddleware,
    secret_key="supersecretkey",
    same_site="none",
    https_only=True,
    max_age=3600
)

# ENV
load_dotenv()

# OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# ------------------ HOME ------------------

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <h1>AI Chat 🎉</h1>
    <a href="/login">Google ile giriş yap</a>
    """

# ------------------ LOGIN ------------------

@app.get("/login")
async def login(request: Request):
    redirect_uri = os.getenv("REDIRECT_URI")
    return await oauth.google.authorize_redirect(request, redirect_uri)

# ------------------ CALLBACK ------------------

@app.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
        user = token.get("userinfo")

        db_user = db.query(models.User).filter(models.User.email == user["email"]).first()

        if not db_user:
            db_user = models.User(
                email=user["email"],
                password="google_user"
            )
            db.add(db_user)
            db.commit()
            db.refresh(db_user)

        request.session["user"] = {
            "id": db_user.id,
            "name": user["name"],
            "email": user["email"]
        }

        return RedirectResponse("/chat")

    except Exception as e:
        return HTMLResponse(f"<h1>Hata ❌</h1><p>{str(e)}</p>")

# ------------------ CHAT PAGE ------------------

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")

    if not user:
        return RedirectResponse("/login")

    chats = db.query(models.Chat).filter(
        models.Chat.user_id == user["id"]
    ).all()

    chat_html = ""

    for c in chats:
        chat_html += f"""
        <div class="user">{c.user_message}</div>
        <div class="ai">{c.ai_response}</div>
        """

    return HTMLResponse(f"""
<html>
<head>
<style>
body {{
    margin: 0;
    font-family: Arial;
    background: linear-gradient(135deg, #667eea, #764ba2);
}}

.container {{
    max-width: 600px;
    margin: auto;
    padding: 20px;
}}

.chat-box {{
    background: #fff;
    padding: 15px;
    border-radius: 15px;
    height: 70vh;
    overflow-y: auto;
    box-shadow: 0 5px 20px rgba(0,0,0,0.2);
}}

.user {{
    background: #dcf8c6;
    padding: 10px;
    margin: 5px;
    border-radius: 10px;
    text-align: right;
}}

.ai {{
    background: #f1f0f0;
    padding: 10px;
    margin: 5px;
    border-radius: 10px;
    text-align: left;
}}

form {{
    display: flex;
    margin-top: 10px;
}}

input {{
    flex: 1;
    padding: 10px;
    border-radius: 10px;
    border: none;
}}

button {{
    padding: 10px;
    margin-left: 5px;
    border-radius: 10px;
    border: none;
    background: #667eea;
    color: white;
    cursor: pointer;
}}

button:hover {{
    background: #5a67d8;
}}

.footer {{
    text-align: center;
    margin-top: 10px;
    color: white;
    font-size: 12px;
}}
</style>
</head>

<body>

<div class="container">

<h2 style="color:white;">Hoş geldin {user['name']} 👋</h2>

<div class="chat-box">
{chat_html}
</div>

<form action="/chat" method="post">
    <input id="msg" name="message" placeholder="Mesaj yaz..." required>
    <button type="submit">Gönder</button>
</form>

<div class="footer">✨ Pınar tarafından üretildi.</div>

</div>

<script>
document.getElementById("msg").addEventListener("keypress", function(e) {{
    if (e.key === "Enter") {{
        e.preventDefault();
        this.form.submit();
    }}
}});
</script>

</body>
</html>
""")

# ------------------ CHAT POST ------------------

@app.post("/chat")
async def chat(request: Request, db: Session = Depends(get_db)):
    try:
        form = await request.form()
        message = form.get("message")

        user = request.session.get("user")

        if not user:
            return RedirectResponse("/login")

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": message}
            ]
        )

        ai_text = response.choices[0].message.content

        new_chat = models.Chat(
            user_id=user["id"],
            user_message=message,
            ai_response=ai_text
        )

        db.add(new_chat)
        db.commit()

        return RedirectResponse("/chat", status_code=303)

    except Exception as e:
        return HTMLResponse(f"<h1>HATA ❌</h1><p>{str(e)}</p>")
