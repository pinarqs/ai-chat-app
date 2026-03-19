print("APP BAŞLADI")

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
import os
from datetime import datetime

from database import get_db, engine, Base
import models

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key="supersecretkey",
    same_site="none",
    https_only=True,
    max_age=3600
)

load_dotenv()

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
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")

    db_user = db.query(models.User).filter(models.User.email == user["email"]).first()

    if not db_user:
        db_user = models.User(email=user["email"], password="google_user")
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

    request.session["user"] = {
        "id": db_user.id,
        "name": user["name"],
        "email": user["email"]
    }

    return RedirectResponse("/chat")

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
        time_str = datetime.now().strftime("%H:%M")
        chat_html += f"""
        <div class="user">{c.user_message}<span>{time_str}</span></div>
        <div class="ai">{c.ai_response}<span>{time_str}</span></div>
        """

    return HTMLResponse(f"""
<html>
<head>
<style>
body {{
    margin:0;
    font-family: Arial;
    background: linear-gradient(135deg,#667eea,#764ba2);
}}

body.dark {{
    background:#121212;
    color:white;
}}

.container {{
    max-width:600px;
    margin:auto;
    padding:20px;
}}

.chat-box {{
    background:white;
    height:70vh;
    overflow-y:auto;
    border-radius:15px;
    padding:10px;
}}

body.dark .chat-box {{
    background:#1e1e1e;
}}

.user {{
    background:#dcf8c6;
    padding:10px;
    margin:5px;
    border-radius:10px;
    text-align:right;
}}

.ai {{
    background:#eee;
    padding:10px;
    margin:5px;
    border-radius:10px;
}}

span {{
    display:block;
    font-size:10px;
    color:gray;
}}

form {{
    display:flex;
    margin-top:10px;
}}

input {{
    flex:1;
    padding:10px;
    border-radius:10px;
    border:none;
}}

button {{
    margin-left:5px;
    padding:10px;
    border:none;
    border-radius:10px;
    background:#667eea;
    color:white;
}}

#typing {{
    display:none;
    color:gray;
}}

.toggle {{
    position:absolute;
    top:10px;
    right:10px;
}}
</style>
</head>

<body>

<button class="toggle" onclick="toggleDark()">🌙</button>

<div class="container">
<h2>Hoş geldin {user['name']} 👋</h2>

<div id="chatBox" class="chat-box">
{chat_html}
</div>

<p id="typing">AI yazıyor...</p>

<form id="chatForm">
<input id="msg" name="message" placeholder="Mesaj yaz..." required>
<button>Gönder</button>
</form>

<div style="text-align:center;color:white;font-size:12px;">
✨ Pınar tarafından üretildi.
</div>

</div>

<script>
const form=document.getElementById("chatForm");
const input=document.getElementById("msg");
const chatBox=document.getElementById("chatBox");

form.addEventListener("submit",async(e)=>{{
e.preventDefault();
let message=input.value;
if(!message)return;

chatBox.innerHTML+=`<div class="user">${{message}}</div>`;
input.value="";
document.getElementById("typing").style.display="block";

let res=await fetch("/chat",{{
method:"POST",
body:new URLSearchParams({{message}})
}});

let data=await res.json();

document.getElementById("typing").style.display="none";

chatBox.innerHTML+=`<div class="ai">${{data.ai}}</div>`;
chatBox.scrollTop=chatBox.scrollHeight;
}});

input.addEventListener("keypress",function(e){{
if(e.key==="Enter"){{
e.preventDefault();
form.dispatchEvent(new Event("submit"));
}}
}});

function toggleDark(){{
document.body.classList.toggle("dark");
localStorage.setItem("dark",document.body.classList.contains("dark"));
}}

if(localStorage.getItem("dark")==="true"){{
document.body.classList.add("dark");
}}

chatBox.scrollTop=chatBox.scrollHeight;
</script>

</body>
</html>
""")

# ------------------ CHAT POST ------------------

@app.post("/chat")
async def chat(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    message = form.get("message")

    user = request.session.get("user")

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": message}]
    )

    ai_text = response.choices[0].message.content

    new_chat = models.Chat(
        user_id=user["id"],
        user_message=message,
        ai_response=ai_text
    )

    db.add(new_chat)
    db.commit()

    return JSONResponse({"ai": ai_text})
