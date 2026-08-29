import os
from html import escape

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.core.auth import UserStore
from app.core.config import ConfigStore
from app.llm.router import LLMRouter
from app.resources.registry import RESOURCE_CATALOG

app = FastAPI(title="Company Agent")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "change-this-before-production"), https_only=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true")
users: UserStore | None = None
config_store = ConfigStore()

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
    return HTMLResponse(f"<!doctype html><meta charset='utf-8'><title>{title}</title><style>body{{max-width:920px;margin:40px auto;font:16px system-ui}} input,select,textarea{{width:100%;padding:8px;margin:5px 0}}button{{padding:8px 14px}} .card{{border:1px solid #ddd;padding:16px;margin:12px 0}}</style>{body}")

@app.get("/login", response_class=HTMLResponse)
def login_page():
    return page("登录", "<h1>Company Agent</h1><form method='post'><input name='username' placeholder='账号'><input name='password' type='password' placeholder='密码'><button>登录</button></form>")

@app.post("/login")
def login(request: Request, username: str = Form(), password: str = Form()):
    user = get_users().authenticate(username, password)
    if not user: return page("登录失败", "<p>账号或密码错误。</p><a href='/login'>重试</a>")
    request.session["user"] = user
    return RedirectResponse("/", status_code=303)

@app.post("/logout")
def logout(request: Request):
    request.session.clear(); return RedirectResponse("/login", status_code=303)

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    user = current_user(request)
    if not user: return RedirectResponse("/login", status_code=303)
    resources = config_store.load()["resources"]
    cards = "".join(f"<div class='card'><b>{item['label']}</b> — {'启用' if resources[key]['enabled'] else '关闭'}<br>{item['description']}</div>" for key, item in RESOURCE_CATALOG.items())
    admin = "<p><a href='/admin/config'>管理配置</a></p>" if user["role"] == "admin" else ""
    return page("工作台", f"<h1>欢迎，{escape(user['username'])}</h1>{admin}<form method='post' action='/logout'><button>退出</button></form><h2>可用资源</h2>{cards}<h2>提问</h2><form method='post' action='/api/chat'><textarea name='message' required></textarea><button>发送</button></form>")

@app.post("/api/chat", response_class=HTMLResponse)
def chat(request: Request, message: str = Form()):
    if not current_user(request): raise HTTPException(401, "请先登录")
    reply = LLMRouter().complete([{"role": "user", "content": message}]).choices[0].message.content or ""
    return page("回复", f"<p>{escape(reply)}</p><a href='/'>返回</a>")

@app.get("/admin/config", response_class=HTMLResponse)
def config_page(request: Request):
    require_admin(request); config = config_store.load(); llm = config["llm"]
    toggles = "".join(f"<label><input type='checkbox' name='{key}' {'checked' if config['resources'][key]['enabled'] else ''}>{item['label']}</label><br>" for key, item in RESOURCE_CATALOG.items())
    return page("管理配置", f"<h1>管理配置</h1><form method='post'><label>本地地址<input name='local_base_url' value='{escape(llm['local_base_url'])}'></label><label>本地模型<input name='local_model' value='{escape(llm['local_model'])}'></label><label><input type='checkbox' name='api_enabled' {'checked' if llm['api_enabled'] else ''}>API 回退（密钥使用环境变量 API_LLM_KEY）</label>{toggles}<button>保存</button></form><p><a href='/'>返回</a></p>")

@app.post("/admin/config")
def save_config(request: Request, local_base_url: str = Form(), local_model: str = Form(), api_enabled: str | None = Form(None), files: str | None = Form(None), web_search: str | None = Form(None), email: str | None = Form(None), crm: str | None = Form(None), website: str | None = Form(None)):
    require_admin(request); config = config_store.load(); config["llm"].update({"local_base_url": local_base_url.rstrip("/"), "local_model": local_model, "api_enabled": api_enabled is not None})
    for key, value in {"files": files, "web_search": web_search, "email": email, "crm": crm, "website": website}.items(): config["resources"][key]["enabled"] = value is not None
    config_store.save(config); return RedirectResponse("/admin/config", status_code=303)
