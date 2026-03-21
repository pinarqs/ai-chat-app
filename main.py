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

load_dotenv()

app = FastAPI()

# ---------------- SESSION ----------------
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "supersecretkey"),
    same_site="lax",
    https_only=False,
    max_age=3600
)

# ---------------- OAUTH ----------------
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# ---------------- OPENAI CLIENT ----------------
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

    # Kullanıcının sohbet listesi (sidebar)
    user_chats = db.query(models.Chat).filter(models.Chat.user_id == user["id"]).order_by(models.Chat.timestamp.desc()).all()

    sidebar_html = ""
    for chat in user_chats:
        title = chat.user_message[:20] or "Yeni Sohbet"
        sidebar_html += f'<div class="chat-item" data-chat-id="{chat.id}">{title}</div>'

    # Varsayılan olarak en son sohbet gösterilecek
    if user_chats:
        active_chat = user_chats[0]
        active_messages = db.query(models.Chat).filter(models.Chat.user_id == user["id"], models.Chat.id == active_chat.id).order_by(models.Chat.timestamp).all()
    else:
        active_messages = []

    chat_html = ""
    for c in active_messages:
        time_str = c.timestamp.strftime("%H:%M") if hasattr(c, "timestamp") and c.timestamp else datetime.now().strftime("%H:%M")
        chat_html += f"""
        <div class="msg show">
            <div class="user">{c.user_message}<span>{time_str}</span></div>
            <div class="ai">{c.ai_response}<span>{time_str}</span></div>
        </div>
        """

    return HTMLResponse(f"""
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
/* BODY + DARK MODE */
body {{ margin:0; font-family: Arial, sans-serif; display:flex; height:100vh; background: linear-gradient(135deg,#667eea,#764ba2); }}
body.dark {{ background:#121212; color:white; }}

/* SIDEBAR */
.sidebar {{
    width:240px;
    background: rgba(255,255,255,0.15);
    backdrop-filter: blur(15px);
    padding:20px;
    display:flex;
    flex-direction: column;
    gap:10px;
}}
.sidebar h3 {{ margin-top:0; }}
.chat-item {{
    padding:10px;
    border-radius:15px;
    cursor:pointer;
    transition: background 0.3s;
}}
.chat-item:hover {{ background: rgba(255,255,255,0.25); }}
.chat-item.active {{ background: rgba(255,255,255,0.4); font-weight:bold; }}

/* CONTAINER */
.container {{ flex:1; display:flex; flex-direction: column; padding:20px; position:relative; }}
.header {{ display:flex; align-items:center; margin-bottom:10px; }}
.avatar {{ width:50px; height:50px; border-radius:50%; margin-right:10px; transition: transform 0.3s; }}
.avatar:hover {{ transform: scale(1.1); }}

/* CHAT BOX */
.chat-box {{
    flex:1;
    background: rgba(255,255,255,0.15);
    backdrop-filter: blur(10px);
    border-radius:20px;
    padding:15px;
    overflow-y:auto;
    display:flex;
    flex-direction: column;
    gap:10px;
}}
body.dark .chat-box {{ background: rgba(0,0,0,0.25); }}

/* MSG */
.msg {{ opacity:0; transform: translateY(10px); transition: all 0.3s ease; }}
.msg.show {{ opacity:1; transform: translateY(0); }}
.user {{ align-self:flex-end; background: linear-gradient(45deg,#6ee7b7,#3b82f6); color:white; padding:10px 15px; border-radius:20px; max-width:70%; }}
.ai {{ align-self:flex-start; background: rgba(255,255,255,0.6); padding:10px 15px; border-radius:20px; max-width:70%; }}
body.dark .ai {{ background: rgba(0,0,0,0.4); color:white; }}
span {{ font-size:10px; display:block; text-align:right; margin-top:3px; }}

/* FORM */
form {{ display:flex; margin-top:10px; position: sticky; bottom:0; gap:5px; }}
input {{ flex:1; padding:12px; border-radius:20px; border:none; }}
button {{ padding:12px 20px; border:none; border-radius:20px; background:#667eea; color:white; cursor:pointer; transition: background 0.3s; }}
button:hover {{ background:#5a67d8; }}

/* TYPING + SEARCH + TOGGLE */
#typing {{ display:none; color:gray; margin-top:5px; }}
.search {{ width:100%; padding:8px; margin-bottom:10px; border-radius:10px; border:none; }}
.toggle {{ position:absolute; top:10px; right:10px; cursor:pointer; }}

/* FOOTER */
.footer {{ text-align:center; margin-top:10px; font-size:12px; color:white; }}
</style>
</head>
<body>
<div class="sidebar">
<h3>💬 Sohbetler</h3>
{sidebar_html}
</div>

<div class="container">
<button class="toggle" onclick="toggleDark()">🌙</button>
<div class="header">
<img src="{user.get('picture') or 'https://i.pravatar.cc/50'}" class="avatar">
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
<input id="msg" placeholder="Mesaj yaz..." autocomplete="off">
<button>Gönder</button>
</form>

<div class="footer">✨ Pınar tarafından üretildi.</div>
</div>

<script>
const form = document.getElementById("chatForm");
const input = document.getElementById("msg");
const chatBox = document.getElementById("chatBox");
const typing = document.getElementById("typing");
const sidebar = document.querySelectorAll(".chat-item");

function scrollToBottom(){ chatBox.scrollTop = chatBox.scrollHeight; }

form.addEventListener("submit", async (e) => {{
    e.preventDefault();
    let message = input.value.trim();
    if(!message) return;

    let time = new Date().toLocaleTimeString().slice(0,5);

    let userDiv = document.createElement("div");
    userDiv.className = "msg show user";
    userDiv.innerHTML = `${{message}}<span>${{time}}</span>`;
    chatBox.appendChild(userDiv);

    input.value="";
    typing.style.display="block";
    scrollToBottom();

    try {{
        let res = await fetch("/chat", {{ method:"POST", body:new URLSearchParams({{message}})}} );
        let data = await res.json();
        typing.style.display="none";

        let aiDiv = document.createElement("div");
        aiDiv.className = "msg show ai";
        aiDiv.innerHTML = `${{data.ai}}<span>${{time}}</span>`;
        chatBox.appendChild(aiDiv);

        scrollToBottom();
    }} catch(err) {{
        typing.style.display="none";
        alert("AI cevap veremiyor 😢");
    }}
}});

// Enter key submit
input.addEventListener("keypress", e => {{
    if(e.key==="Enter"){ e.preventDefault(); form.dispatchEvent(new Event("submit")); }
}});

// Dark mode toggle
function toggleDark(){{
    document.body.classList.toggle("dark");
    localStorage.setItem("dark",document.body.classList.contains("dark"));
}}
if(localStorage.getItem("dark")==="true") document.body.classList.add("dark");

// Sidebar click - multi-chat
sidebar.forEach(item => {{
    item.addEventListener("click", async () => {{
        sidebar.forEach(i=>i.classList.remove("active"));
        item.classList.add("active");

        let chatId = item.dataset.chatId;
        let res = await fetch(`/chat/${{chatId}}`);
        let data = await res.json();
        chatBox.innerHTML = "";
        data.messages.forEach(m => {{
            let div = document.createElement("div");
            div.className = "msg show " + (m.role==="user"?"user":"ai");
            div.innerHTML = `${{m.content}}<span>${{m.time}}</span>`;
            chatBox.appendChild(div);
        }});
        scrollToBottom();
    }});
}});

// Search
document.getElementById("search").addEventListener("input", function(){{
    let val=this.value.toLowerCase();
    document.querySelectorAll(".msg").forEach(m=>{
        m.style.display=m.innerText.toLowerCase().includes(val)?"flex":"none";
    }});
}});

scrollToBottom();
</script>
</body>
</html>
""")
