import os
from html import escape

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from dotenv import load_dotenv

from app.core.auth import UserStore
from app.core.config import ConfigStore
from app.llm.router import LLMRouter
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


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta charset='utf-8'><title>{title}</title>"
        f"<style>body{{max-width:920px;margin:40px auto;font:16px system-ui}} "
        f"input,select,textarea{{width:100%;padding:8px;margin:5px 0}}"
        f"button{{padding:8px 14px}} .card{{border:1px solid #ddd;padding:16px;margin:12px 0}}</style>"
        f"{body}"
    )


CHAT_STYLE = """
<style>
*{box-sizing:border-box}
body{margin:0;font:16px system-ui;background:#eef1f5;height:100vh;display:flex;flex-direction:column}
header{background:#fff;border-bottom:1px solid #d7dbe0;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px}
header .brand{font-weight:600}
header nav{display:flex;align-items:center;gap:12px;font-size:14px}
header form{display:inline;margin:0}
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
form.addEventListener('submit',async function(e){
  e.preventDefault();
  const text=input.value.trim();
  if(!text)return;
  input.value='';
  addMsg('user',text);
  const typing=addMsg('assistant','正在思考…');
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
    addMsg('error','请求失败：'+err.message);
  }
  sendBtn.disabled=false;
  input.focus();
});
loadHistory();
input.focus();
</script>
"""


def chat_page(user: dict, resources_html: str) -> HTMLResponse:
    admin = "<a href='/admin/config'>管理配置</a>" if user["role"] == "admin" else ""
    body = (
        CHAT_STYLE
        + "<header><span class='brand'>Company Agent</span><nav>"
        + "<span>欢迎，" + escape(user["username"]) + "</span>"
        + admin
        + "<form method='post' action='/logout'><button>退出</button></form>"
        + "</nav></header>"
        + "<main id='messages'></main>"
        + "<details><summary>可用资源</summary>" + resources_html + "</details>"
        + "<footer><form id='chat-form'><input id='message' autocomplete='off' placeholder='输入消息，Enter 发送'><button id='send'>发送</button></form></footer>"
        + CHAT_SCRIPT
    )
    return HTMLResponse("<!doctype html><meta charset='utf-8'><title>Company Agent</title>" + body)


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return page("登录", "<h1>Company Agent</h1><form method='post'><input name='username' placeholder='账号'><input name='password' type='password' placeholder='密码'><button>登录</button></form>")


@app.post("/login")
def login(request: Request, username: str = Form(), password: str = Form()):
    user = get_users().authenticate(username, password)
    if not user:
        return page("登录失败", "<p>账号或密码错误。</p><a href='/login'>重试</a>")
    request.session["user"] = user
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    resources = config_store.load()["resources"]
    cards = "".join(
        f"<div class='card'><b>{item['label']}</b> — {'启用' if resources[key]['enabled'] else '关闭'}<br>{item['description']}</div>"
        for key, item in RESOURCE_CATALOG.items()
    )
    return chat_page(user, cards)


@app.get("/api/history")
def api_history(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "请先登录")
    return {"messages": chat_history.get(user["username"], [])}


@app.post("/api/chat")
def chat(request: Request, message: str = Form()):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "请先登录")
    text = message.strip()
    if not text:
        return JSONResponse({"error": "消息不能为空"}, status_code=400)

    history = chat_history.setdefault(user["username"], [])
    history.append({"role": "user", "content": text})
    try:
        reply = LLMRouter().complete(history).choices[0].message.content or ""
    except RuntimeError:
        history.pop()
        return JSONResponse(
            {"error": "模型暂时不可用。请确认本地 Ollama 服务和已配置模型可用；若需要，也可由管理员在配置页启用 API 回退。"},
            status_code=503,
        )
    history.append({"role": "assistant", "content": reply})
    if len(history) > MAX_HISTORY:
        del history[: len(history) - MAX_HISTORY]
    return {"reply": reply}


@app.get("/admin/config", response_class=HTMLResponse)
def config_page(request: Request):
    require_admin(request)
    config = config_store.load()
    llm = config["llm"]
    toggles = "".join(
        f"<label><input type='checkbox' name='{key}' {'checked' if config['resources'][key]['enabled'] else ''}>{item['label']}</label><br>"
        for key, item in RESOURCE_CATALOG.items()
    )
    return page("管理配置", f"<h1>管理配置</h1><form method='post'><label>本地地址<input name='local_base_url' value='{escape(llm['local_base_url'])}'></label><label>本地模型<input name='local_model' value='{escape(llm['local_model'])}'></label><label><input type='checkbox' name='api_enabled' {'checked' if llm['api_enabled'] else ''}>API 回退（密钥使用环境变量 API_LLM_KEY）</label>{toggles}<button>保存</button></form><p><a href='/'>返回</a></p>")


@app.post("/admin/config")
def save_config(request: Request, local_base_url: str = Form(), local_model: str = Form(), api_enabled: str | None = Form(None), files: str | None = Form(None), web_search: str | None = Form(None), email: str | None = Form(None), crm: str | None = Form(None), website: str | None = Form(None)):
    require_admin(request)
    config = config_store.load()
    config["llm"].update({"local_base_url": local_base_url.rstrip("/"), "local_model": local_model, "api_enabled": api_enabled is not None})
    for key, value in {"files": files, "web_search": web_search, "email": email, "crm": crm, "website": website}.items():
        config["resources"][key]["enabled"] = value is not None
    config_store.save(config)
    return RedirectResponse("/admin/config", status_code=303)
