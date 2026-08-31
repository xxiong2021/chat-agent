import os
from html import escape
from urllib.parse import quote, urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from dotenv import load_dotenv

from app.core.auth import UserStore
from app.core.config import ConfigStore
from app.agent.web_agent import run_agent
from app.resources.registry import RESOURCE_CATALOG

load_dotenv()

app = FastAPI(title="Company Agent")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "change-this-before-production"),
    https_only=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
)

users: UserStore | None = None
config_store = ConfigStore()
chat_history: dict[str, list[dict]] = {}
MAX_HISTORY = 30

I18N = {
    "en": {
        "lang_name": "EN",
        "lang_other_name": "中文",
        "title": "Company Agent",
        "login_title": "Sign in",
        "login_failed": "Sign-in failed",
        "login_failed_msg": "Incorrect username or password.",
        "retry": "Try again",
        "username": "Username",
        "password": "Password",
        "login": "Sign in",
        "logout": "Sign out",
        "welcome": "Welcome, {user}",
        "admin_config": "Admin settings",
        "available_resources": "Available resources",
        "input_placeholder": "Type a message, Enter to send",
        "send": "Send",
        "thinking": "Thinking…",
        "request_failed": "Request failed: ",
        "enabled": "Enabled",
        "disabled": "Disabled",
        "config_title": "Admin settings",
        "local_base_url": "Local base URL",
        "local_model": "Local model",
        "api_fallback": "API fallback (key read from environment variable API_LLM_KEY)",
        "save": "Save",
        "back": "Back",
        "login_required": "Sign in required",
        "empty_message": "Message cannot be empty.",
        "model_unavailable": "The model is temporarily unavailable. Check that the local Ollama service and the configured model are running; if needed, an admin can enable API fallback on the settings page.",
    },
    "zh": {
        "lang_name": "中文",
        "lang_other_name": "EN",
        "title": "Company Agent",
        "login_title": "登录",
        "login_failed": "登录失败",
        "login_failed_msg": "账号或密码错误。",
        "retry": "重试",
        "username": "账号",
        "password": "密码",
        "login": "登录",
        "logout": "退出",
        "welcome": "欢迎，{user}",
        "admin_config": "管理配置",
        "available_resources": "可用资源",
        "input_placeholder": "输入消息，Enter 发送",
        "send": "发送",
        "thinking": "正在思考…",
        "request_failed": "请求失败：",
        "enabled": "启用",
        "disabled": "关闭",
        "config_title": "管理配置",
        "local_base_url": "本地地址",
        "local_model": "本地模型",
        "api_fallback": "API 回退（密钥使用环境变量 API_LLM_KEY）",
        "save": "保存",
        "back": "返回",
        "login_required": "请先登录",
        "empty_message": "消息不能为空",
        "model_unavailable": "模型暂时不可用。请确认本地 Ollama 服务和已配置模型可用；若需要，也可由管理员在配置页启用 API 回退。",
    },
}


def get_lang(request: Request) -> str:
    lang = request.cookies.get("lang", "en")
    return lang if lang in I18N else "en"


def lang_link(request: Request) -> str:
    lang = get_lang(request)
    other = "zh" if lang == "en" else "en"
    name = I18N[other]["lang_name"]
    next_path = request.url.path
    params = {k: v for k, v in request.query_params.items() if k != "lang"}
    if params:
        next_path += "?" + urlencode(params)
    next_enc = quote(next_path, safe="")
    return f"<a class='lang-switch' href='/set-lang?lang={other}&amp;next={next_enc}'>{name}</a>"


def language_switcher(request: Request) -> str:
    return (
        "<span class='lang-box'>"
        + lang_link(request)
        + "</span>"
    )


def get_users() -> UserStore:
    global users
    if users is None:
        users = UserStore()
    return users


def current_user(request: Request):
    return request.session.get("user")


def require_admin(request: Request):
    user = current_user(request)
    if not user or user["role"] != "admin":
        raise HTTPException(403, "管理员权限必需")
    return user


def page(request: Request, title: str, body: str) -> HTMLResponse:
    lang = get_lang(request)
    switch = language_switcher(request)
    return HTMLResponse(
        f"<!doctype html><meta charset='utf-8'><title>{title}</title>"
        f"<style>body{{max-width:920px;margin:40px auto;font:16px system-ui}} "
        f"input,select,textarea{{width:100%;padding:8px;margin:5px 0}}"
        f"button{{padding:8px 14px}} .card{{border:1px solid #ddd;padding:16px;margin:12px 0}}"
        f".lang-switch{{color:#2563eb;text-decoration:none;font-size:14px}} .lang-switch:hover{{text-decoration:underline}}</style>"
        f"<div style='text-align:right;margin-bottom:8px'>{switch}</div>{body}"
    )


CHAT_STYLE = """
<style>
*{box-sizing:border-box}
body{margin:0;font:16px system-ui;background:#eef1f5;height:100vh;display:flex;flex-direction:column}
header{background:#fff;border-bottom:1px solid #d7dbe0;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px}
header .brand{font-weight:600}
header nav{display:flex;align-items:center;gap:12px;font-size:14px}
header form{display:inline;margin:0}
.lang-box{margin-left:4px}
.lang-switch{color:#2563eb;text-decoration:none}
.lang-switch:hover{text-decoration:underline}
main{flex:1;overflow-y:auto;padding:20px;max-width:900px;width:100%;margin:0 auto;display:flex;flex-direction:column;gap:10px}
.msg{max-width:75%;padding:10px 14px;border-radius:14px;line-height:1.55;white-space:pre-wrap;word-break:break-word}
.msg.user{align-self:flex-end;background:#2563eb;color:#fff;border-bottom-right-radius:4px}
.msg.assistant{align-self:flex-start;background:#fff;border:1px solid #d7dbe0;border-bottom-left-radius:4px}
.msg.error{align-self:flex-start;background:#fef2f2;border:1px solid #fca5a5;color:#991b1b}
details{max-width:900px;width:100%;margin:0 auto;padding:0 20px 8px;font-size:14px;color:#374151}
details .card{border:1px solid #d7dbe0;background:#fff;padding:10px 14px;margin:6px 0;border-radius:8px}
footer{background:#fff;border-top:1px solid #d7dbe0;padding:12px 20px}
footer form{max-width:900px;margin:0 auto;display:flex;gap:8px}
footer input{flex:1;padding:11px 14px;font-size:16px;border:1px solid #c7ccd4;border-radius:10px;outline:none}
footer input:focus{border-color:#2563eb}
footer button{padding:11px 20px;border:none;background:#2563eb;color:#fff;border-radius:10px;font-size:16px;cursor:pointer}
footer button:disabled{opacity:.6;cursor:default}
</style>
"""

CHAT_SCRIPT = """
<script>
const main=document.getElementById('messages');
const form=document.getElementById('chat-form');
const input=document.getElementById('message');
const sendBtn=document.getElementById('send');
function addMsg(role,text){
  const d=document.createElement('div');
  d.className='msg '+role;
  d.textContent=text;
  main.appendChild(d);
  main.scrollTop=main.scrollHeight;
  return d;
}
async function loadHistory(){
  const r=await fetch('/api/history');
  if(r.status===401){location.href='/login';return;}
  const data=await r.json();
  main.innerHTML='';
  (data.messages||[]).forEach(m=>addMsg(m.role,m.content));
}
function sendMsg(role,text){
  const d=document.createElement('div');
  d.className='msg '+role;
  d.textContent=text;
  main.appendChild(d);
  main.scrollTop=main.scrollHeight;
  return d;
}
form.addEventListener('submit',async function(e){
  e.preventDefault();
  const text=input.value.trim();
  if(!text)return;
  input.value='';
  addMsg('user',text);
  const typing=sendMsg('assistant','__THINKING__');
  sendBtn.disabled=true;
  try{
    const r=await fetch('/api/chat',{
      method:'POST',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'message='+encodeURIComponent(text)
    });
    if(r.status===401){location.href='/login';return;}
    const data=await r.json();
    typing.remove();
    if(data.error){
      addMsg('error',data.error);
    }else{
      addMsg('assistant',data.reply);
    }
  }catch(err){
    typing.remove();
    addMsg('error','__REQUEST_FAILED__'+err.message);
  }
  sendBtn.disabled=false;
  input.focus();
});
loadHistory();
input.focus();
</script>
"""


def chat_page(request: Request, user: dict, resources_html: str) -> HTMLResponse:
    lang = get_lang(request)
    t = I18N[lang]
    admin = f"<a href='/admin/config'>{escape(t['admin_config'])}</a>" if user["role"] == "admin" else ""
    script = (
        CHAT_SCRIPT.replace("__THINKING__", t["thinking"])
        .replace("__REQUEST_FAILED__", t["request_failed"])
    )
    body = (
        CHAT_STYLE
        + "<header><span class='brand'>Company Agent</span><nav>"
        + "<span>" + escape(t["welcome"].format(user=user["username"])) + "</span>"
        + admin
        + "<form method='post' action='/logout'><button>" + escape(t["logout"]) + "</button></form>"
        + language_switcher(request)
        + "</nav></header>"
        + "<main id='messages'></main>"
        + "<details><summary>" + escape(t["available_resources"]) + "</summary>" + resources_html + "</details>"
        + "<footer><form id='chat-form'><input id='message' autocomplete='off' placeholder='" + escape(t["input_placeholder"]) + "'><button id='send'>" + escape(t["send"]) + "</button></form></footer>"
        + script
    )
    return HTMLResponse("<!doctype html><meta charset='utf-8'><title>Company Agent</title>" + body)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    t = I18N[get_lang(request)]
    return page(
        request,
        t["login_title"],
        "<h1>Company Agent</h1>"
        f"<form method='post'><input name='username' placeholder='{t['username']}' autocomplete='username'>"
        f"<input name='password' type='password' placeholder='{t['password']}' autocomplete='current-password'>"
        f"<button>{t['login']}</button></form>",
    )


@app.post("/login")
def login(request: Request, username: str = Form(), password: str = Form()):
    t = I18N[get_lang(request)]
    user = get_users().authenticate(username, password)
    if not user:
        return page(request, t["login_failed"], f"<p>{t['login_failed_msg']}</p><a href='/login'>{t['retry']}</a>")
    request.session["user"] = user
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/set-lang")
def set_lang(request: Request, lang: str = "en", next: str = "/"):
    if lang not in I18N:
        lang = "en"
    target = "/"
    if next.startswith("/") and not next.startswith("//"):
        target = next.split("?")[0] or "/"
    response = RedirectResponse(target, status_code=303)
    response.set_cookie("lang", lang, max_age=31536000, httponly=True, samesite="lax")
    return response


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    lang = get_lang(request)
    t = I18N[lang]
    resources = config_store.load()["resources"]
    cards = "".join(
        f"<div class='card'><b>{escape(item.get('label_en') if lang == 'en' else item['label'])}</b> — {escape(t['enabled'] if resources[key]['enabled'] else t['disabled'])}<br>{escape(item.get('description_en') if lang == 'en' else item['description'])}</div>"
        for key, item in RESOURCE_CATALOG.items()
    )
    return chat_page(request, user, cards)


@app.get("/api/history")
def api_history(request: Request):
    t = I18N[get_lang(request)]
    user = current_user(request)
    if not user:
        raise HTTPException(401, t["login_required"])
    return {"messages": chat_history.get(user["username"], [])}


@app.post("/api/chat")
def chat(request: Request, message: str = Form()):
    t = I18N[get_lang(request)]
    user = current_user(request)
    if not user:
        raise HTTPException(401, t["login_required"])
    text = message.strip()
    if not text:
        return JSONResponse({"error": t["empty_message"]}, status_code=400)

    history = chat_history.setdefault(user["username"], [])
    history.append({"role": "user", "content": text})
    try:
        reply = run_agent(f"web:{user['username']}", history, config_store.load())
    except RuntimeError:
        history.pop()
        return JSONResponse(
            {"error": t["model_unavailable"]},
            status_code=503,
        )
    history.append({"role": "assistant", "content": reply})
    if len(history) > MAX_HISTORY:
        del history[: len(history) - MAX_HISTORY]
    return {"reply": reply}


@app.get("/admin/config", response_class=HTMLResponse)
def config_page(request: Request):
    require_admin(request)
    lang = get_lang(request)
    t = I18N[lang]
    config = config_store.load()
    llm = config["llm"]
    toggles = "".join(
        f"<label><input type='checkbox' name='{key}' {'checked' if config['resources'][key]['enabled'] else ''}>{escape(item.get('label_en') if lang == 'en' else item['label'])}</label><br>"
        for key, item in RESOURCE_CATALOG.items()
    )
    return page(
        request,
        t["config_title"],
        f"<h1>{t['config_title']}</h1><form method='post'>"
        f"<label>{t['local_base_url']}<input name='local_base_url' value='{escape(llm['local_base_url'])}'></label>"
        f"<label>{t['local_model']}<input name='local_model' value='{escape(llm['local_model'])}'></label>"
        f"<label><input type='checkbox' name='api_enabled' {'checked' if llm['api_enabled'] else ''}>{escape(t['api_fallback'])}</label>"
        f"{toggles}<button>{t['save']}</button></form><p><a href='/'>{t['back']}</a></p>",
    )


@app.post("/admin/config")
def save_config(request: Request, local_base_url: str = Form(), local_model: str = Form(), api_enabled: str | None = Form(None), files: str | None = Form(None), web_search: str | None = Form(None), email: str | None = Form(None), crm: str | None = Form(None), website: str | None = Form(None)):
    require_admin(request)
    config = config_store.load()
    config["llm"].update({"local_base_url": local_base_url.rstrip("/"), "local_model": local_model, "api_enabled": api_enabled is not None})
    for key, value in {"files": files, "web_search": web_search, "email": email, "crm": crm, "website": website}.items():
        config["resources"][key]["enabled"] = value is not None
    config_store.save(config)
    return RedirectResponse("/admin/config", status_code=303)
