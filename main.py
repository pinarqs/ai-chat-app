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

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key="supersecretkey",
    same_site="lax",
    https_only=False,
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

# ---------------- HOME ----------------

@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>AI Chat 🎉</h1><a href='/login'>Google ile giriş</a>"

# ---------------- LOGIN ----------------

@app.get("/login")
async def login(request: Request):
    return await oauth.google.authorize_redirect(request, os.getenv("REDIRECT_URI"))

# ---------------- CALLBACK ----------------

@app.get("/auth/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")

    db_user = db.query(models.User).filter(models.User.email == user["email"]).first()

    if not db_user:
        db_user = models.User(email=user["email"], password="google")
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

    request.session["user"] = {
        "id": db_user.id,
        "name": user["name"],
        "email": user["email"],
        "picture": user.get("picture")
    }

    return RedirectResponse("/chat")

# ---------------- CHAT PAGE ----------------

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
        title = c.user_message[:20]

        chat_html += f"""
        <div class="msg fade">
            <div class="title">{title}</div>
            <div class="user">{c.user_message}<span>{time_str}</span></div>
            <div class="ai">{c.ai_response}<span>{time_str}</span></div>
        </div>
        """

    return HTMLResponse(f"""
<html>
<head>
<style>
body {{
    margin:0;
    font-family: Arial;
    background: linear-gradient(135deg,#667eea,#764ba2);
    display:flex;
}}

body.dark {{
    background:#0f0f0f;
    color:white;
}}

.sidebar {{
    width:220px;
    background:rgba(0,0,0,0.2);
    backdrop-filter: blur(10px);
    padding:15px;
    color:white;
}}

.sidebar h3 {{
    margin-top:0;
}}

.container {{
    flex:1;
    padding:20px;
}}

.header {{
    display:flex;
    align-items:center;
    margin-bottom:10px;
}}

.avatar {{
    width:40px;
    height:40px;
    border-radius:50%;
    margin-right:10px;
}}

.chat-box {{
    background:white;
    height:65vh;
    overflow-y:auto;
    border-radius:15px;
    padding:15px;
}}

body.dark .chat-box {{
    background:#1e1e1e;
}}

.msg {{
    margin-bottom:15px;
}}

.fade {{
    animation:fadeIn 0.3s ease;
}}

@keyframes fadeIn {{
    from {{opacity:0; transform:translateY(10px);}}
    to {{opacity:1; transform:translateY(0);}}
}}

.user {{
    background:linear-gradient(45deg,#6ee7b7,#3b82f6);
    color:white;
    padding:10px;
    margin:5px;
    border-radius:15px;
    text-align:right;
}}

.ai {{
    background:#eee;
    padding:10px;
    margin:5px;
    border-radius:15px;
}}

body.dark .ai {{
    background:#333;
}}

span {{
    font-size:10px;
    display:block;
}}

form {{
    display:flex;
    margin-top:10px;
}}

input {{
    flex:1;
    padding:12px;
    border-radius:15px;
    border:none;
}}

button {{
    margin-left:5px;
    padding:12px;
    border:none;
    border-radius:15px;
    background:#667eea;
    color:white;
    cursor:pointer;
}}

#typing {{
    display:none;
    color:gray;
}}

.search {{
    width:100%;
    padding:8px;
    margin-bottom:10px;
    border-radius:10px;
    border:none;
}}

.toggle {{
    position:absolute;
    top:10px;
    right:10px;
}}

.footer {{
    text-align:center;
    margin-top:10px;
    font-size:12px;
    color:white;
}}
</style>
</head>

<body>

<div class="sidebar">
<h3>💬 Sohbetler</h3>
<p>Yeni sohbet yakında 😏</p>
</div>

<div class="container">

<button class="toggle" onclick="toggleDark()">🌙</button>

<div class="header">
<img src="{user.get('picture') or 'https://i.pravatar.cc/40'}" class="avatar">
<div>
<div>{user['name']}</div>
<div style="font-size:12px;color:lightgreen;">🟢 Online</div>
</div>
</div>

<input class="search" id="search" placeholder="Ara...">

<div id="chatBox" class="chat-box">
{chat_html}
</div>

<p id="typing">AI yazıyor...</p>

<form id="chatForm">
<input id="msg" placeholder="Mesaj yaz...">
<button>Gönder</button>
</form>

<div class="footer">✨ Pınar tarafından üretildi.</div>

</div>

<script>
const form=document.getElementById("chatForm");
const input=document.getElementById("msg");
const chatBox=document.getElementById("chatBox");
const typing=document.getElementById("typing");

form.addEventListener("submit",async(e)=>{{
e.preventDefault();
let message=input.value;
if(!message)return;

let time=new Date().toLocaleTimeString().slice(0,5);

chatBox.innerHTML+=`
<div class="msg fade">
<div class="user">${{message}}<span>${{time}}</span></div>
</div>`;

input.value="";
typing.style.display="block";

let res=await fetch("/chat",{{method:"POST",body:new URLSearchParams({{message}})}});

let data=await res.json();

typing.style.display="none";

chatBox.innerHTML+=`
<div class="msg fade">
<div class="ai">${{data.ai}}<span>${{time}}</span></div>
</div>
`;

chatBox.scrollTop=chatBox.scrollHeight;
}});

input.addEventListener("keypress",e=>{{
if(e.key==="Enter"){{e.preventDefault();form.dispatchEvent(new Event("submit"));}}
}});

function toggleDark(){{
document.body.classList.toggle("dark");
localStorage.setItem("dark",document.body.classList.contains("dark"));
}}

if(localStorage.getItem("dark")==="true")document.body.classList.add("dark");

document.getElementById("search").addEventListener("input",function(){{
let val=this.value.toLowerCase();
document.querySelectorAll(".msg").forEach(m=>{{
m.style.display=m.innerText.toLowerCase().includes(val)?"block":"none";
}});
}});

chatBox.scrollTop=chatBox.scrollHeight;
</script>

</body>
</html>
""")

# ---------------- CHAT POST ----------------

@app.post("/chat")
async def chat(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    message = form.get("message")

    user = request.session.get("user")

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role":"user","content":message}]
    )

    ai_text = response.choices[0].message.content

    db.add(models.Chat(
        user_id=user["id"],
        user_message=message,
        ai_response=ai_text
    ))
    db.commit()

    return JSONResponse({"ai": ai_text})
