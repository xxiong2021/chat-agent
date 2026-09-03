import os
import time
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from dotenv import load_dotenv

from app.core.auth import UserStore
from app.core.config import ConfigStore
from app.agent.web_agent import run_agent
from app.resources.registry import RESOURCE_CATALOG
from app.skills.loader import discover_skills, skill_display, skill_enabled

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

LOCAL_MODELS = [
    "qwen3:0.6b",
    "qwen3:4b",
    "qwen3:8b",
    "qwen3:14b",
    "qwen2.5:7b",
    "llama3.1:8b",
]

API_MODELS = [
    "deepseek-chat",
    "deepseek-reasoner",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4.1-mini",
    "gpt-4.1",
]

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
        "upload": "Upload",
        "uploading": "Uploading…",
        "upload_ok": "Uploaded: {path}",
        "upload_fail": "Upload failed: ",
        "thinking": "Thinking…",
        "request_failed": "Request failed: ",
        "enabled": "Enabled",
        "disabled": "Disabled",
        "config_title": "Admin settings",
        "skills_section": "Skills",
        "local_section": "Local models",
        "api_section": "Use API models",
        "local_base_url": "Local base URL",
        "local_model": "Local model",
        "local_model_list": "Local model",
        "api_model": "API model",
        "api_base_url": "API base URL",
        "files_root": "Local working directory",
        "files_root_hint": "Absolute path on the server, or a path relative to the project root. Used by file tools.",
        "model_hint": "Pick from the list or type a custom model name.",
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
        "upload": "上传",
        "uploading": "上传中…",
        "upload_ok": "已上传：{path}",
        "upload_fail": "上传失败：",
        "thinking": "正在思考…",
        "request_failed": "请求失败：",
        "enabled": "启用",
        "disabled": "关闭",
        "config_title": "管理配置",
        "skills_section": "技能",
        "local_section": "本地模型",
        "api_section": "使用 API 模型",
        "local_base_url": "本地地址",
        "local_model": "本地模型",
        "local_model_list": "本地模型",
        "api_model": "API 模型",
        "api_base_url": "API 地址",
        "files_root": "本地可操作目录",
        "files_root_hint": "服务器上的绝对路径，或相对项目根目录的路径；文件工具以此为根。",
        "model_hint": "从列表选择，或直接输入自定义模型名。",
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


def ollama_models(base_url: str, timeout: float = 2.0) -> list[str]:
    """查询 Ollama 实际安装的模型列表；失败时返回空列表。"""
    if not base_url:
        return []
    api_url = base_url.replace("/v1", "").rstrip("/") + "/api/tags"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(api_url)
            resp.raise_for_status()
            return sorted(
                m.get("name", "")
                for m in resp.json().get("models", [])
                if m.get("name")
            )
    except Exception:
        return []


def model_datalist(
    datalist_id: str,
    current: str,
    models: list[str],
    extra: list[str] | None = None,
) -> str:
    """生成可输入也可选择的模型输入框 + datalist 提示。"""
    candidates = list(models)
    for m in (extra or []):
        if m and m not in candidates:
            candidates.append(m)
    if current and current not in candidates:
        candidates.insert(0, current)
    options = "".join(
        f"<option value='{escape(m)}'>{escape(m)}</option>"
        for m in candidates
    )
    return (
        f"<input id='{datalist_id}' name='{datalist_id}' list='{datalist_id}-list' "
        f"value='{escape(current)}' autocomplete='off'>"
        f"<datalist id='{datalist_id}-list'>{options}</datalist>"
    )


def get_users() -> UserStore:
    global users
    if users is None:
        users = UserStore()
    return users


def current_user(request: Request):
    return request.session.get("user")


def upload_dir() -> Path:
    """上传目录 = 配置的本地可操作目录/uploads，默认项目根/uploads。"""
    config = config_store.load()
    raw_root = config.get("resources", {}).get("files", {}).get("root") or "."
    root_path = Path(str(raw_root)).expanduser()
    if not root_path.is_absolute():
        root_path = Path(__file__).resolve().parents[1] / root_path
    uploads = root_path / "uploads"
    try:
        uploads.mkdir(parents=True, exist_ok=True)
    except OSError:
        uploads = Path(__file__).resolve().parents[1] / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
    return uploads


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
        f".field{{margin:12px 0}} .field>label{{display:block;margin-bottom:2px;font-weight:600}}"
        f".check-row{{display:flex;align-items:flex-start;gap:8px;margin:8px 0;cursor:pointer}}"
        f".check-row input{{width:auto;margin:3px 0 0;flex:none}}"
        f".checks{{margin:12px 0;padding:12px;border:1px solid #ddd;border-radius:6px}}"
        f"fieldset.group{{margin:16px 0;padding:12px 16px;border:1px solid #cbd5e1;border-radius:8px}}"
        f"fieldset.group legend{{padding:0 6px;font-weight:600}}"
        f"fieldset.group .check-row{{margin:0}}"
        f".hint{{display:block;color:#6b7280;font-size:12px;margin-top:2px}}"
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
footer .attach-btn{padding:6px 13px;border:1px solid #c7ccd4;background:#fff;border-radius:10px;font-size:22px;line-height:1;color:#000;font-weight:400;cursor:pointer;white-space:nowrap}
footer .attach-btn:hover{background:#f1f5f9}
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
const fileInput=document.getElementById('file-input');
const uploadBtn=document.getElementById('upload-btn');
let uploadedPath=null;
const UPLOAD_OK_TMPL='__UPLOAD_OK__';
function addMsg(role,text){
  const d=document.createElement('div');
  d.className='msg '+role;
  d.textContent=text;
  main.appendChild(d);
  main.scrollTop=main.scrollHeight;
  return d;
}
async function doUpload(file){
  if(!file)return;
  const fd=new FormData();
  fd.append('file',file);
  const note=addMsg('user','__UPLOADING__ '+file.name);
  uploadBtn.disabled=true;
  try{
    const r=await fetch('/api/upload',{method:'POST',body:fd});
    if(r.status===401){location.href='/login';return;}
    const data=await r.json();
    if(!r.ok||!data.ok){note.remove();addMsg('error','__UPLOAD_FAIL__'+(data.detail||data.error||''));return;}
    note.remove();
    uploadedPath=data.path;
    addMsg('assistant',UPLOAD_OK_TMPL.replace('{path}',uploadedPath));
  }catch(err){
    note.remove();
    addMsg('error','__UPLOAD_FAIL__'+err.message);
  }
  uploadBtn.disabled=false;
  fileInput.value='';
}
uploadBtn.addEventListener('click',function(){fileInput.click();});
fileInput.addEventListener('change',function(){doUpload(this.files[0]);});
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
  let prompt=text;
  if(!text&&!uploadedPath)return;
  if(uploadedPath){
    prompt=text?prompt+' ('+uploadedPath+')':'请读取并分析上传的文件：'+uploadedPath;
  }
  input.value='';
  addMsg('user',prompt);
  uploadedPath=null;
  const typing=sendMsg('assistant','__THINKING__');
  sendBtn.disabled=true;
  try{
    const r=await fetch('/api/chat',{
      method:'POST',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'message='+encodeURIComponent(prompt)
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
        .replace("__UPLOADING__", t["uploading"])
        .replace("'__UPLOAD_OK__'", "'" + t["upload_ok"] + "'")
        .replace("__UPLOAD_FAIL__", t["upload_fail"])
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
        + "<footer><form id='chat-form'><input id='file-input' type='file' accept='.pdf,.txt,.md,.csv' hidden>"
        + "<button type='button' id='upload-btn' class='attach-btn' title='" + escape(t["upload"]) + "'>+</button>"
        + "<input id='message' autocomplete='off' placeholder='" + escape(t["input_placeholder"]) + "'>"
        + "<button id='send'>" + escape(t["send"]) + "</button></form></footer>"
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
        reply = run_agent(
            f"web:{user['username']}",
            history,
            config_store.load(),
            is_admin=user.get("role") == "admin",
            config_store=config_store,
        )
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


@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    t = I18N[get_lang(request)]
    user = current_user(request)
    if not user:
        raise HTTPException(401, t["login_required"])
    filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    safe_name = "".join(
        c if c.isalnum() or c in "._-" else "_" for c in filename
    ).strip(".")
    if not safe_name or "." not in safe_name:
        raise HTTPException(400, "文件名无效")
    if not safe_name.lower().endswith((".pdf", ".txt", ".md", ".csv")):
        raise HTTPException(400, "仅支持上传 .pdf/.txt/.md/.csv 文件")
    unique = f"{user['username']}_{int(time.time())}_{safe_name}"
    dest = upload_dir() / unique
    try:
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:
            raise HTTPException(413, "文件过大（上限 50MB）")
        dest.write_bytes(content)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "文件保存失败")
    return {
        "ok": True,
        "name": safe_name,
        "path": f"uploads/{unique}",
    }


@app.get("/admin/config", response_class=HTMLResponse)
def config_page(request: Request):
    require_admin(request)
    lang = get_lang(request)
    t = I18N[lang]
    config = config_store.load()
    llm = config["llm"]
    files_root = config.get("resources", {}).get("files", {}).get("root", ".")
    local_enabled = llm.get("local_enabled", True)
    available = ollama_models(llm.get("local_base_url", ""))
    local_models = model_datalist("local_model", llm.get("local_model", ""), LOCAL_MODELS, available)
    api_models = model_datalist("api_model", llm.get("api_model", ""), API_MODELS)
    api_hidden = " style='display:none'" if not llm.get("api_enabled", False) else ""
    skills_html = "".join(
        f"<label class='check-row'><input type='checkbox' name='skill_{name}' {'checked' if skill_enabled(config, name) else ''}>"
        f"<span>{escape(info['title'])} — {escape(info['description'])}</span></label>"
        for name, manifest in sorted(discover_skills().items())
        for info in [skill_display(manifest, lang)]
    )
    skills_block = ""
    if skills_html:
        skills_block = (
            f"<div class='checks'><b>{escape(t['skills_section'])}</b><br>{skills_html}</div>"
        )
    toggles = "".join(
        f"<label class='check-row'><input type='checkbox' name='{key}' {'checked' if config['resources'][key]['enabled'] else ''}><span>{escape(item.get('label_en') if lang == 'en' else item['label'])}</span></label>"
        for key, item in RESOURCE_CATALOG.items()
    )
    return page(
        request,
        t["config_title"],
        f"<h1>{t['config_title']}</h1><form method='post'>"
        f"<fieldset class='group'><legend><label class='check-row'><input type='checkbox' name='local_enabled' {'checked' if local_enabled else ''}><span>{escape(t['local_section'])}</span></label></legend>"
        f"<div class='field'><label for='local_base_url'>{t['local_base_url']}</label>"
        f"<input id='local_base_url' name='local_base_url' value='{escape(llm['local_base_url'])}'></div>"
        f"<div class='field'><label for='local_model'>{t['local_model_list']}</label>{local_models}"
        f"<small class='hint'>{t['model_hint']}</small></div>"
        f"<div class='field'><label for='files_root'>{t['files_root']}</label>"
        f"<input id='files_root' name='files_root' value='{escape(files_root)}'>"
        f"<small class='hint'>{t['files_root_hint']}</small></div></fieldset>"
        f"<fieldset class='group'><legend><label class='check-row'><input type='checkbox' name='api_enabled' id='api_enabled' {'checked' if llm['api_enabled'] else ''}><span>{escape(t['api_section'])}</span></label></legend>"
        f"<div id='api-fields'{api_hidden}>"
        f"<div class='field'><label for='api_base_url'>{t['api_base_url']}</label>"
        f"<input id='api_base_url' name='api_base_url' value='{escape(llm.get('api_base_url', ''))}'></div>"
        f"<div class='field'><label for='api_model'>{t['api_model']}</label>{api_models}"
        f"<small class='hint'>{t['model_hint']}</small></div>"
        f"<small class='hint'>{escape(t['api_fallback'])}</small></div></fieldset>"
        f"<div class='checks'>{toggles}</div>"
        f"{skills_block}"
        f"<button>{t['save']}</button></form>"
        f"<script>var apiBox=document.getElementById('api_enabled'),apiFields=document.getElementById('api-fields');"
        f"function syncApi(){{apiFields.style.display=apiBox.checked?'':'none';}}"
        f"apiBox.addEventListener('change',syncApi);syncApi();</script>"
        f"<p><a href='/'>{t['back']}</a></p>",
    )


@app.post("/admin/config")
async def save_config(request: Request):
    require_admin(request)
    form = await request.form()
    def checked(name: str) -> bool:
        return form.get(name) is not None
    config = config_store.load()
    config["llm"].update({
        "local_base_url": str(form.get("local_base_url", "")).rstrip("/"),
        "local_model": str(form.get("local_model", "")),
        "api_base_url": str(form.get("api_base_url", "")).rstrip("/") or config["llm"].get("api_base_url", ""),
        "api_model": str(form.get("api_model", "")),
        "api_enabled": checked("api_enabled"),
        "local_enabled": checked("local_enabled"),
    })
    config["resources"]["files"]["root"] = str(form.get("files_root", ".")).strip() or "."
    for key in ("files", "web_search", "email", "crm", "website"):
        config["resources"][key]["enabled"] = checked(key)
    skills = config.setdefault("skills", {})
    for name in discover_skills():
        entry = skills.setdefault(name, {})
        entry["enabled"] = checked(f"skill_{name}")
    config_store.save(config)
    return RedirectResponse("/admin/config", status_code=303)
