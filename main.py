print("APP BAŞLADI")

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from datetime import datetime
from html import escape
import os

from database import get_db, engine, Base
import models

# Eğer Render'da startup sorunu yaşarsan bu satırı yorumlu bırak.
# Base.metadata.create_all(bind=engine)

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
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

# ---------------- HELPERS ----------------

def format_time(dt_value) -> str:
    if dt_value and hasattr(dt_value, "strftime"):
        return dt_value.strftime("%H:%M")
    return datetime.now().strftime("%H:%M")

def chat_title(text: str) -> str:
    if not text:
        return "Yeni sohbet"
    cleaned = " ".join(text.strip().split())
    return cleaned[:28] + ("..." if len(cleaned) > 28 else "")

# ---------------- HOME ----------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = request.session.get("user")
    if user:
        return RedirectResponse("/chat")

    return HTMLResponse("""
    <html>
    <head>
        <title>Pınar AI</title>
        <style>
            body {
                margin: 0;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
            }
            .card {
                background: rgba(255,255,255,0.12);
                backdrop-filter: blur(12px);
                padding: 40px;
                border-radius: 24px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.25);
                text-align: center;
                width: min(90vw, 460px);
            }
            a {
                display: inline-block;
                margin-top: 20px;
                text-decoration: none;
                background: white;
                color: #5b5bd6;
                padding: 12px 18px;
                border-radius: 14px;
                font-weight: bold;
            }
            p {
                opacity: .9;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Pınar AI ✨</h1>
            <p>Google ile giriş yap ve kendi yapay zekâ sohbet alanını kullan.</p>
            <a href="/login">Google ile giriş yap</a>
        </div>
    </body>
    </html>
    """)

# ---------------- LOGIN ----------------

@app.get("/login")
async def login(request: Request):
    return await oauth.google.authorize_redirect(request, os.getenv("REDIRECT_URI"))

# ---------------- CALLBACK ----------------

@app.get("/auth/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")

    if not user:
        return HTMLResponse("<h1>Google kullanıcı bilgisi alınamadı ❌</h1>", status_code=400)

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
        "picture": user.get("picture"),
    }

    return RedirectResponse("/chat")

# ---------------- LOGOUT ----------------

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")

# ---------------- CHAT PAGE ----------------

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")

    if not user:
        return RedirectResponse("/login")

    chats = (
        db.query(models.Chat)
        .filter(models.Chat.user_id == user["id"])
        .order_by(models.Chat.id.asc())
        .all()
    )

    sidebar_html = ""
    messages_html = ""

    for c in chats:
        title = escape(chat_title(c.user_message))
        user_msg = escape(c.user_message or "")
        ai_msg = escape(c.ai_response or "")
        time_str = format_time(getattr(c, "created_at", None))
        chat_id = getattr(c, "id", 0)

        sidebar_html += f"""
        <div class="conversation-item" id="sidebar-item-{chat_id}" onclick="focusMessage('{chat_id}')">
            <div class="conversation-main">
                <div class="conversation-title">{title}</div>
                <div class="conversation-preview">{user_msg[:36]}</div>
            </div>
            <button class="delete-btn" onclick="event.stopPropagation(); deleteChat('{chat_id}')">✕</button>
        </div>
        """

        messages_html += f"""
        <div class="message-group fade" id="msg-{chat_id}">
            <div class="message-title">{title}</div>
            <div class="user-wrap">
                <div class="bubble user-bubble">
                    <div>{user_msg}</div>
                    <div class="time">{time_str}</div>
                </div>
            </div>
            <div class="ai-wrap">
                <div class="bubble ai-bubble">
                    <div>{ai_msg}</div>
                    <div class="time">{time_str}</div>
                </div>
            </div>
        </div>
        """

    avatar = escape(user.get("picture") or "https://i.pravatar.cc/100")
    name = escape(user.get("name") or "Kullanıcı")
    email = escape(user.get("email") or "")

    return HTMLResponse(f"""
    <html>
    <head>
        <title>Pınar AI</title>
        <style>
            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: #111827;
                min-height: 100vh;
                transition: background .3s ease, color .3s ease;
            }}

            body.dark {{
                background: linear-gradient(135deg, #0f172a, #111827);
                color: #f3f4f6;
            }}

            .app {{
                display: grid;
                grid-template-columns: 280px 1fr;
                min-height: 100vh;
            }}

            .sidebar {{
                backdrop-filter: blur(16px);
                background: rgba(255,255,255,0.16);
                border-right: 1px solid rgba(255,255,255,0.18);
                padding: 18px;
                display: flex;
                flex-direction: column;
                gap: 14px;
            }}

            body.dark .sidebar {{
                background: rgba(15,23,42,0.6);
                border-right: 1px solid rgba(255,255,255,0.08);
            }}

            .brand {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
            }}

            .brand-title {{
                font-size: 22px;
                font-weight: 700;
                color: white;
            }}

            .top-actions {{
                display: flex;
                gap: 8px;
            }}

            .icon-btn {{
                border: none;
                border-radius: 12px;
                padding: 9px 11px;
                cursor: pointer;
                background: rgba(255,255,255,.2);
                color: white;
                transition: .2s ease;
            }}

            .icon-btn:hover {{
                transform: translateY(-1px);
                background: rgba(255,255,255,.3);
            }}

            .profile-card {{
                display: flex;
                gap: 12px;
                align-items: center;
                background: rgba(255,255,255,0.18);
                border-radius: 18px;
                padding: 12px;
                color: white;
            }}

            .avatar {{
                width: 50px;
                height: 50px;
                border-radius: 50%;
                object-fit: cover;
                border: 2px solid rgba(255,255,255,.65);
            }}

            .profile-name {{
                font-weight: 700;
            }}

            .profile-email {{
                font-size: 12px;
                opacity: .9;
                word-break: break-word;
            }}

            .online {{
                font-size: 12px;
                color: #bbf7d0;
                margin-top: 4px;
            }}

            .search {{
                width: 100%;
                padding: 12px 14px;
                border-radius: 14px;
                border: none;
                outline: none;
            }}

            .conversation-list {{
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: 10px;
                padding-right: 4px;
            }}

            .conversation-item {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                background: rgba(255,255,255,0.16);
                border-radius: 14px;
                padding: 12px;
                color: white;
                cursor: pointer;
                transition: .2s ease;
            }}

            .conversation-item:hover {{
                transform: translateY(-1px);
                background: rgba(255,255,255,0.24);
            }}

            .conversation-main {{
                min-width: 0;
                flex: 1;
            }}

            .conversation-title {{
                font-size: 13px;
                font-weight: 700;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}

            .conversation-preview {{
                font-size: 12px;
                opacity: .85;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                margin-top: 4px;
            }}

            .delete-btn {{
                border: none;
                background: rgba(239,68,68,.9);
                color: white;
                border-radius: 10px;
                width: 28px;
                height: 28px;
                cursor: pointer;
                flex-shrink: 0;
            }}

            .delete-btn:hover {{
                background: rgb(220, 38, 38);
            }}

            .main {{
                display: flex;
                flex-direction: column;
                min-height: 100vh;
                padding: 22px;
                gap: 14px;
            }}

            .main-top {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 12px;
                color: white;
            }}

            .main-title {{
                font-size: 26px;
                font-weight: 800;
            }}

            .main-sub {{
                font-size: 13px;
                opacity: .9;
            }}

            .chat-card {{
                flex: 1;
                display: flex;
                flex-direction: column;
                backdrop-filter: blur(16px);
                background: rgba(255,255,255,.88);
                border-radius: 26px;
                box-shadow: 0 18px 50px rgba(0,0,0,.18);
                overflow: hidden;
            }}

            body.dark .chat-card {{
                background: rgba(17,24,39,.92);
            }}

            .chat-header {{
                padding: 18px 20px;
                border-bottom: 1px solid rgba(0,0,0,.08);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}

            body.dark .chat-header {{
                border-bottom: 1px solid rgba(255,255,255,.08);
            }}

            .chat-header-left {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}

            .mini-avatar {{
                width: 42px;
                height: 42px;
                border-radius: 50%;
                object-fit: cover;
            }}

            .chat-header-name {{
                font-weight: 700;
            }}

            .chat-header-status {{
                font-size: 12px;
                color: #10b981;
            }}

            .messages {{
                flex: 1;
                overflow-y: auto;
                padding: 18px;
                scroll-behavior: smooth;
            }}

            .message-group {{
                margin-bottom: 18px;
            }}

            .message-title {{
                font-size: 12px;
                color: #6b7280;
                margin: 0 0 8px 6px;
                font-weight: 700;
            }}

            .user-wrap {{
                display: flex;
                justify-content: flex-end;
            }}

            .ai-wrap {{
                display: flex;
                justify-content: flex-start;
            }}

            .bubble {{
                max-width: 78%;
                padding: 12px 14px;
                border-radius: 18px;
                margin-bottom: 8px;
                line-height: 1.45;
                box-shadow: 0 5px 16px rgba(0,0,0,.08);
                word-wrap: break-word;
            }}

            .user-bubble {{
                background: linear-gradient(135deg, #60a5fa, #8b5cf6);
                color: white;
                border-bottom-right-radius: 6px;
            }}

            .ai-bubble {{
                background: #f3f4f6;
                color: #111827;
                border-bottom-left-radius: 6px;
            }}

            body.dark .ai-bubble {{
                background: #1f2937;
                color: #f9fafb;
            }}

            .time {{
                font-size: 10px;
                opacity: .75;
                margin-top: 6px;
            }}

            .typing {{
                display: none;
                padding: 0 20px 10px;
                color: #6b7280;
                font-size: 14px;
            }}

            .input-bar {{
                position: sticky;
                bottom: 0;
                padding: 16px 18px 18px;
                border-top: 1px solid rgba(0,0,0,.08);
                background: rgba(255,255,255,.88);
            }}

            body.dark .input-bar {{
                background: rgba(17,24,39,.92);
                border-top: 1px solid rgba(255,255,255,.08);
            }}

            #chatForm {{
                display: flex;
                gap: 10px;
                align-items: center;
            }}

            #msg {{
                flex: 1;
                border: none;
                outline: none;
                padding: 14px 16px;
                border-radius: 18px;
                background: #f3f4f6;
                font-size: 14px;
            }}

            body.dark #msg {{
                background: #111827;
                color: white;
            }}

            .send-btn {{
                border: none;
                border-radius: 18px;
                padding: 14px 18px;
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                cursor: pointer;
                font-weight: 700;
                transition: .2s ease;
            }}

            .send-btn:hover {{
                transform: translateY(-1px);
                filter: brightness(1.05);
            }}

            .footer {{
                text-align: center;
                font-size: 12px;
                color: white;
                opacity: .9;
            }}

            .fade {{
                animation: fadeIn .25s ease;
            }}

            @keyframes fadeIn {{
                from {{
                    opacity: 0;
                    transform: translateY(10px);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}

            @media (max-width: 900px) {{
                .app {{
                    grid-template-columns: 1fr;
                }}

                .sidebar {{
                    display: none;
                }}

                .main {{
                    padding: 10px;
                }}

                .bubble {{
                    max-width: 88%;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="app">
            <aside class="sidebar">
                <div class="brand">
                    <div class="brand-title">Pınar AI</div>
                    <div class="top-actions">
                        <button class="icon-btn" onclick="toggleDark()">🌙</button>
                        <a href="/logout" style="text-decoration:none;">
                            <button class="icon-btn" type="button">⎋</button>
                        </a>
                    </div>
                </div>

                <div class="profile-card">
                    <img src="{avatar}" class="avatar" alt="Profil">
                    <div>
                        <div class="profile-name">{name}</div>
                        <div class="profile-email">{email}</div>
                        <div class="online">🟢 Online</div>
                    </div>
                </div>

                <input class="search" id="searchInput" placeholder="Sohbetlerde ara...">

                <div class="conversation-list" id="conversationList">
                    {sidebar_html or '<div style="color:white;opacity:.9;">Henüz sohbet yok. İlk mesajını yaz ✨</div>'}
                </div>
            </aside>

            <main class="main">
                <div class="main-top">
                    <div>
                        <div class="main-title">Yapay zekâ sohbetin hazır</div>
                        <div class="main-sub">Mesajların kaydedilir, arayabilir ve silebilirsin.</div>
                    </div>
                </div>

                <section class="chat-card">
                    <div class="chat-header">
                        <div class="chat-header-left">
                            <img src="{avatar}" class="mini-avatar" alt="Profil">
                            <div>
                                <div class="chat-header-name">{name}</div>
                                <div class="chat-header-status">🟢 Aktif</div>
                            </div>
                        </div>
                    </div>

                    <div class="messages" id="chatBox">
                        {messages_html or '<div style="text-align:center;color:#6b7280;margin-top:20px;">İlk mesajını yaz, birlikte başlayalım 💬</div>'}
                    </div>

                    <div class="typing" id="typing">AI yazıyor...</div>

                    <div class="input-bar">
                        <form id="chatForm">
                            <input id="msg" name="message" placeholder="Mesaj yaz..." autocomplete="off" required>
                            <button class="send-btn" type="submit">Gönder</button>
                        </form>
                    </div>
                </section>

                <div class="footer">✨ Pınar tarafından üretildi.</div>
            </main>
        </div>

        <script>
            const form = document.getElementById("chatForm");
            const input = document.getElementById("msg");
            const chatBox = document.getElementById("chatBox");
            const typing = document.getElementById("typing");
            const searchInput = document.getElementById("searchInput");
            const conversationList = document.getElementById("conversationList");

            function currentTime() {{
                const now = new Date();
                return now.toLocaleTimeString([], {{ hour: "2-digit", minute: "2-digit" }});
            }}

            function escapeHtml(text) {{
                const div = document.createElement("div");
                div.innerText = text;
                return div.innerHTML;
            }}

            function chatTitle(text) {{
                const clean = text.trim().replace(/\\s+/g, " ");
                return clean.length > 28 ? clean.slice(0, 28) + "..." : clean;
            }}

            function appendSidebarItem(id, message) {{
                const title = chatTitle(message);
                const preview = message.length > 36 ? message.slice(0, 36) + "..." : message;

                const wrapper = document.createElement("div");
                wrapper.className = "conversation-item fade";
                wrapper.id = `sidebar-item-${{id}}`;
                wrapper.onclick = function() {{
                    focusMessage(id);
                }};

                wrapper.innerHTML = `
                    <div class="conversation-main">
                        <div class="conversation-title">${{escapeHtml(title)}}</div>
                        <div class="conversation-preview">${{escapeHtml(preview)}}</div>
                    </div>
                    <button class="delete-btn" onclick="event.stopPropagation(); deleteChat('${{id}}')">✕</button>
                `;

                if (conversationList.innerText.includes("Henüz sohbet yok")) {{
                    conversationList.innerHTML = "";
                }}

                conversationList.appendChild(wrapper);
            }}

            function appendMessageGroup(id, userText, aiText, time) {{
                const group = document.createElement("div");
                group.className = "message-group fade";
                group.id = `msg-${{id}}`;

                group.innerHTML = `
                    <div class="message-title">${{escapeHtml(chatTitle(userText))}}</div>
                    <div class="user-wrap">
                        <div class="bubble user-bubble">
                            <div>${{escapeHtml(userText)}}</div>
                            <div class="time">${{time}}</div>
                        </div>
                    </div>
                    <div class="ai-wrap">
                        <div class="bubble ai-bubble">
                            <div>${{escapeHtml(aiText)}}</div>
                            <div class="time">${{time}}</div>
                        </div>
                    </div>
                `;

                chatBox.appendChild(group);
                chatBox.scrollTop = chatBox.scrollHeight;
            }}

            async function deleteChat(id) {{
                const ok = confirm("Bu sohbet kaydını silmek istiyor musun?");
                if (!ok) return;

                const res = await fetch(`/chat/delete/${{id}}`, {{ method: "POST" }});
                const data = await res.json();

                if (data.success) {{
                    const sidebarItem = document.getElementById(`sidebar-item-${{id}}`);
                    const msgItem = document.getElementById(`msg-${{id}}`);
                    if (sidebarItem) sidebarItem.remove();
                    if (msgItem) msgItem.remove();

                    if (!conversationList.children.length) {{
                        conversationList.innerHTML = '<div style="color:white;opacity:.9;">Henüz sohbet yok. İlk mesajını yaz ✨</div>';
                    }}
                }}
            }}

            function focusMessage(id) {{
                const el = document.getElementById(`msg-${{id}}`);
                if (el) {{
                    el.scrollIntoView({{ behavior: "smooth", block: "center" }});
                }}
            }}

            form.addEventListener("submit", async function(e) {{
                e.preventDefault();

                const message = input.value.trim();
                if (!message) return;

                const tempTime = currentTime();
                const tempGroup = document.createElement("div");
                tempGroup.className = "message-group fade";
                tempGroup.innerHTML = `
                    <div class="message-title">${{escapeHtml(chatTitle(message))}}</div>
                    <div class="user-wrap">
                        <div class="bubble user-bubble">
                            <div>${{escapeHtml(message)}}</div>
                            <div class="time">${{tempTime}}</div>
                        </div>
                    </div>
                `;

                chatBox.appendChild(tempGroup);
                chatBox.scrollTop = chatBox.scrollHeight;

                input.value = "";
                typing.style.display = "block";

                try {{
                    const res = await fetch("/chat", {{
                        method: "POST",
                        body: new URLSearchParams({{ message }})
                    }});

                    const data = await res.json();
                    typing.style.display = "none";

                    if (!data.success) {{
                        const err = document.createElement("div");
                        err.className = "ai-wrap";
                        err.innerHTML = `<div class="bubble ai-bubble">Hata oluştu: ${{escapeHtml(data.error || "Bilinmeyen hata")}}</div>`;
                        tempGroup.appendChild(err);
                        return;
                    }}

                    tempGroup.remove();
                    appendSidebarItem(data.id, message);
                    appendMessageGroup(data.id, message, data.ai, data.time);
                }} catch (err) {{
                    typing.style.display = "none";
                    const fail = document.createElement("div");
                    fail.className = "ai-wrap";
                    fail.innerHTML = `<div class="bubble ai-bubble">Bağlantı hatası oluştu.</div>`;
                    tempGroup.appendChild(fail);
                }}
            }});

            input.addEventListener("keypress", function(e) {{
                if (e.key === "Enter") {{
                    e.preventDefault();
                    form.dispatchEvent(new Event("submit"));
                }}
            }});

            function toggleDark() {{
                document.body.classList.toggle("dark");
                localStorage.setItem("dark", document.body.classList.contains("dark"));
            }}

            if (localStorage.getItem("dark") === "true") {{
                document.body.classList.add("dark");
            }}

            searchInput.addEventListener("input", function() {{
                const val = this.value.toLowerCase();
                document.querySelectorAll(".conversation-item").forEach(item => {{
                    item.style.display = item.innerText.toLowerCase().includes(val) ? "flex" : "none";
                }});

                document.querySelectorAll(".message-group").forEach(item => {{
                    item.style.display = item.innerText.toLowerCase().includes(val) ? "block" : "none";
                }});
            }});

            chatBox.scrollTop = chatBox.scrollHeight;
        </script>
    </body>
    </html>
    """)

# ---------------- CHAT POST ----------------

@app.post("/chat")
async def chat(request: Request, db: Session = Depends(get_db)):
    try:
        form = await request.form()
        message = (form.get("message") or "").strip()
        user = request.session.get("user")

        if not user:
            return JSONResponse({"success": False, "error": "Oturum bulunamadı."}, status_code=401)

        if not message:
            return JSONResponse({"success": False, "error": "Mesaj boş olamaz."}, status_code=400)

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": message}]
        )

        ai_text = response.choices[0].message.content or ""

        new_chat = models.Chat(
            user_id=user["id"],
            user_message=message,
            ai_response=ai_text
        )
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)

        return JSONResponse({
            "success": True,
            "id": new_chat.id,
            "title": chat_title(message),
            "user": message,
            "ai": ai_text,
            "time": format_time(getattr(new_chat, "created_at", None)),
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

# ---------------- DELETE CHAT ----------------

@app.post("/chat/delete/{chat_id}")
async def delete_chat(chat_id: int, request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")

    if not user:
        return JSONResponse({"success": False}, status_code=401)

    chat = db.query(models.Chat).filter(
        models.Chat.id == chat_id,
        models.Chat.user_id == user["id"]
    ).first()

    if not chat:
        return JSONResponse({"success": False}, status_code=404)

    db.delete(chat)
    db.commit()

    return JSONResponse({"success": True})