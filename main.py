print("APP BAŞLADI")
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
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

print("CALLBACK YÜKLENDİ")
@app.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
        user = token.get("userinfo")

        if not user:
            return HTMLResponse("<h1>User bilgisi alınamadı ❌</h1>")

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

        return RedirectResponse("/profile")

    except Exception as e:
        return HTMLResponse(f"<h1>Hata oluştu ❌</h1><p>{str(e)}</p>")


    return RedirectResponse("/profile")

# ------------------ PROFILE ------------------

@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request):
    user = request.session.get("user")

    if not user:
        return RedirectResponse("/login")

    return f"""
    <h2>Hoş geldin {user['name']} 🎉</h2>
    <p>{user['email']}</p>

    <form action="/chat" method="post">
        <input name="message" placeholder="Mesaj yaz"/>
        <button type="submit">Gönder</button>
    </form>
    """

# ------------------ CHAT ------------------

@app.post("/chat", response_class=HTMLResponse)
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

        return HTMLResponse(f"""
<h2>Chat 💬</h2>

<p><b>Sen:</b> {message}</p>
<p><b>AI:</b> {ai_text}</p>

<form action="/chat" method="post">
    <input name="message" placeholder="Mesaj yaz"/>
    <button type="submit">Gönder</button>
</form>
""")

    except Exception as e:
        return HTMLResponse(f"""
        <h1>HATA YAKALANDI ❌</h1>
        <p>{str(e)}</p>
        """);