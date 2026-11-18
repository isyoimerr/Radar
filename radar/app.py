"""RADAR application: public reading, user accounts, editorial admin and RSS pipeline."""
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote, urlparse
from fastapi import FastAPI, Request, HTTPException, Response, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import catalog, config, store, security, demo, feeds
from .pipeline import collect, latest_news, top_five, convert_row, backfill_missing_media
from .export import bulletin_html, bulletin_png, build_carousel_deck, export_carousel_zip
from .language import LANGUAGES, source_excerpt, story_language

app=FastAPI(title='RADAR News API',version='1.0.0',docs_url='/api/docs',redoc_url=None)
app.mount('/assets',StaticFiles(directory=str(config.ROOT/'static')),name='assets')
store.init()
demo.seed()
catalog.seed_bundled_catalog()


def _news_needs_refresh(min_recent_items=8, stale_seconds=None):
    stale_seconds = int(os.getenv('RADAR_STALE_SECONDS', stale_seconds or 1800))
    now = datetime.now(timezone.utc)
    latest_run = store.row('SELECT MAX(at) AS at FROM pipeline_runs')
    if latest_run and latest_run['at']:
        try:
            last_run = datetime.fromisoformat(str(latest_run['at']).replace('Z', '+00:00'))
            age = (now - last_run).total_seconds()
            if age > stale_seconds:
                return True
            if age <= stale_seconds:
                recent_cutoff = (now - timedelta(days=7)).isoformat(timespec='seconds')
                recent_count = store.row('SELECT COUNT(*) AS c FROM news WHERE approved=1 AND is_demo=0 AND published_at >= ?', (recent_cutoff,))
                return (recent_count['c'] if recent_count else 0) < min_recent_items
        except ValueError:
            pass
    recent_cutoff = (now - timedelta(days=7)).isoformat(timespec='seconds')
    recent_count = store.row('SELECT COUNT(*) AS c FROM news WHERE approved=1 AND is_demo=0 AND published_at >= ?', (recent_cutoff,))
    return (recent_count['c'] if recent_count else 0) < min_recent_items or not latest_run or not latest_run['at']


def _data_uri_for_theme(label, tone):
    svg = f'''
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 700">
      <defs>
        <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="{tone['start']}" />
          <stop offset="100%" stop-color="{tone['end']}" />
        </linearGradient>
      </defs>
      <rect width="1000" height="700" fill="url(#g)"/>
      <circle cx="170" cy="170" r="170" fill="rgba(255,255,255,0.12)"/>
      <circle cx="820" cy="140" r="180" fill="rgba(255,255,255,0.06)"/>
      <rect x="80" y="520" width="840" height="90" rx="18" fill="rgba(10,16,24,0.18)"/>
      <text x="80" y="328" font-family="Arial, Helvetica, sans-serif" font-size="54" font-weight="700" fill="#F7FAFC">RADAR</text>
      <text x="80" y="392" font-family="Arial, Helvetica, sans-serif" font-size="30" fill="#EEF8F8">{label}</text>
    </svg>
    '''.strip()
    return 'data:image/svg+xml;charset=utf-8,' + quote(svg)


def _clear_placeholder_news():
    store.exec_('DELETE FROM news WHERE lower(headline) LIKE ? OR sources_json LIKE ?', ('%fallback%', '%RADAR local fallback%'))


def _run_collect_cycle():
    try:
        result=collect(enable_ai=False)
        print(f'RADAR: ronda RSS completada -> {result.get("fetched",0)} consultadas, {result.get("new",0)} nuevas, {result.get("updated",0)} actualizadas, errores={len(result.get("errors",[]))}')
    except Exception as exc:
        msg=f'Ronda RSS fallida: {type(exc).__name__}: {exc}'
        print(msg)
        store.exec_('INSERT INTO pipeline_runs(at,fetched,new_count,errors_json,mode) VALUES(?,?,?,?,?)',
                    (store.now(), 0, 0, json.dumps([msg], ensure_ascii=False), 'error'))


def _schedule_collect(delay_seconds=0.0, name='radar-background-collect'):
    def runner():
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        _run_collect_cycle()
    thread = threading.Thread(target=runner, name=name, daemon=True)
    thread.start()
    return thread


def start_background_scheduler():
    if os.getenv('RADAR_DISABLE_BACKGROUND_SCHEDULER', '1').lower() in {'1','true','yes','on'}:
        return
    period=int(os.getenv('RADAR_COLLECT_SECONDS', '900'))
    def loop():
        time.sleep(5)
        while True:
            _run_collect_cycle()
            time.sleep(period)
    thread=threading.Thread(target=loop, name='radar-rss-scheduler', daemon=True)
    thread.start()


@app.on_event('startup')
def bootstrap_news_if_empty():
    if config.VERCEL_ENV:
        return
    try:
        _clear_placeholder_news()
        if not store.row('SELECT 1 FROM news WHERE approved=1 AND is_demo=0 LIMIT 1'):
            print('RADAR: no hay noticias aprobadas; programando recolección RSS inicial en segundo plano.')
            _schedule_collect(delay_seconds=2.0, name='radar-startup-collect')
            return
        threading.Thread(target=backfill_missing_media, name='radar-media-backfill', daemon=True).start()
    except Exception as exc:
        print(f'RADAR: bootstrap RSS fallida: {type(exc).__name__}: {exc}')

app.bootstrap_news_if_empty = bootstrap_news_if_empty
app._run_collect_cycle = _run_collect_cycle
app.start_background_scheduler = start_background_scheduler

start_background_scheduler()

# No hardcoded production administrator password.
admin_cred_file=config.DATA_DIR/'admin_credentials.txt'
if not store.row("SELECT id FROM users WHERE role='admin' LIMIT 1"):
    password=os.getenv('ADMIN_PASSWORD') or secrets.token_urlsafe(17)
    email=os.getenv('ADMIN_EMAIL','admin@radar.local').strip().lower()
    store.exec_('INSERT INTO users(email,pw_hash,role,accepted_at,created_at) VALUES(?,?,?,?,?)',
                (email,security.hash_password(password),'admin',store.now(),store.now()))
    if not os.getenv('ADMIN_PASSWORD'):
        admin_cred_file.write_text(f'Acceso inicial local a RADAR\nCorreo: {email}\nClave: {password}\nCambiar clave al preparar producción.\n',encoding='utf-8')
        try: admin_cred_file.chmod(0o600)
        except OSError: pass
        print(f'\nRADAR: usuario administrador inicial guardado en {admin_cred_file}\n')

_counter=defaultdict(list)

def rate_guard(ip,key,limit=15,window=120):
    t=time.time();bucket=_counter[ip+':'+key]
    bucket[:]=[x for x in bucket if t-x<window]
    if len(bucket)>=limit:raise HTTPException(429,'Demasiados intentos. Intenta más tarde.')
    bucket.append(t)

@app.middleware('http')
async def security_headers(request:Request,call_next):
    origin=request.headers.get('origin')
    if request.method == 'OPTIONS':
        response=Response(status_code=204)
        if origin:
            response.headers['Access-Control-Allow-Origin']=origin
            response.headers['Access-Control-Allow-Methods']='GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers']='Content-Type, Authorization'
            response.headers['Access-Control-Allow-Credentials']='true'
        return response
    # Origin check protects cookie-based write actions; local browser requests on localhost/127.0.0.1 must remain allowed.
    if request.method not in ('GET','HEAD','OPTIONS'):
        if origin:
            parsed=urlparse(origin)
            host = (parsed.hostname or '').lower()
            trusted = {urlparse(item).hostname.lower() for item in config.TRUSTED_ORIGINS if item}
            if host not in {'localhost','127.0.0.1','::1','[::1]'} and host not in trusted:
                return JSONResponse({'detail':'Origen no permitido'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-src https://www.youtube-nocookie.com; object-src 'none'; base-uri 'self'; form-action 'self'"
    if origin:
        response.headers['Access-Control-Allow-Origin']=origin
        response.headers['Access-Control-Allow-Credentials']='true'
    return response

class Credentials(BaseModel):
    email:str=Field(min_length=5,max_length=180)
    password:str=Field(min_length=8,max_length=150)

class Registration(Credentials):
    terms_accepted:bool
    privacy_acknowledged:bool

class SourceInput(BaseModel):
    name:str=Field(min_length=3,max_length=100)
    feed_url:str=Field(min_length=10,max_length=1000)
    homepage:str=''
    rights_note:str='Revisar derechos y condiciones de reutilización'

class SourceUpdate(BaseModel):
    name:str|None=None
    homepage:str|None=None
    rights_note:str|None=None
    enabled:bool|None=None

class ReviewInput(BaseModel):
    action:str

class Preferences(BaseModel):
    news_id:int

class PasswordChange(BaseModel):
    old_password:str
    new_password:str=Field(min_length=10,max_length=150)

class DeleteAccount(BaseModel):
    password:str


def current_user(req:Request):
    uid=security.parse_session(req.cookies.get('radar_session'))
    return store.row('SELECT id,email,role,created_at FROM users WHERE id=?',(uid,)) if uid else None

def require_user(req:Request):
    u=current_user(req)
    if not u:raise HTTPException(401,'Inicia sesión para continuar')
    return u

def require_admin(req:Request):
    u=require_user(req)
    if u['role']!='admin':raise HTTPException(403,'Se requiere permiso de edición')
    return u

@app.get('/api/health')
def health():return {'ok':True,'db':'sqlite','edition_size':len(top_five())}

@app.get('/api/config')
def frontend_config():
    return {'app':'RADAR','ai_configured':bool(config.GEMINI_KEY),'ai_model':config.GEMINI_MODEL if config.GEMINI_KEY else None,
        'server_mode':'local' if config.LOCAL_ONLY else 'deployment','generated_at':store.now(),
        'notice':'El número de fuentes no demuestra por sí solo la veracidad de un hecho.'}

@app.get('/api/news')
def news(topic:str='Todas',q:str='',limit:int=60,days:int|None=None,from_date:str|None=None,to_date:str|None=None,lang:str|None=None):
    try:
        if not config.VERCEL_ENV and _news_needs_refresh(min_recent_items=8):
            thread = _schedule_collect(name='radar-news-refresh-background')
            thread.join(timeout=0.25)
    except Exception:
        pass

    limit=max(1,min(int(limit or 60),200))
    items=latest_news(topic_name=topic,query=q,limit=limit,days=days,from_date=from_date,to_date=to_date,language=lang)
    if not items:
        return {'items': [], 'top': []}
    return {'items': items, 'top': top_five(language=lang)}

@app.get('/api/news/{slug}')
def story(slug:str):
    catalog.refresh_public_catalog()
    record=store.row('SELECT * FROM news WHERE slug=? AND approved=1',(slug,))
    if not record or (record['is_demo'] and not demo.is_enabled()):
        raise HTTPException(404,'Noticia no disponible')
    item = convert_row(record)
    item['language'] = story_language(item['headline'], item['summary'])
    if item['mode'] == 'titular_atribuido':
        item['summary'] = source_excerpt(item['summary'])
    return item

@app.get('/api/sources')
def sources():return store.rows('SELECT id,name,feed_url,homepage,region,rights_note,enabled FROM sources ORDER BY name')

@app.get('/api/runs')
def runs():
    records=store.rows('SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 12')
    for r in records:r['errors']=json.loads(r.pop('errors_json'))
    return records

@app.api_route('/api/boletin.html', methods=['GET','HEAD','OPTIONS'], response_class=HTMLResponse)
def html_export():return bulletin_html()

@app.api_route('/api/boletin.png', methods=['GET','HEAD','OPTIONS'])
def png_export():
    return Response(content=bulletin_png(),media_type='image/png',headers={'Content-Disposition':'attachment; filename="radar-boletin-1080x1350.png"'})

@app.api_route('/api/boletin.json', methods=['GET','HEAD','OPTIONS'])
def json_export():return {'title':'Boletín RADAR','at':store.now(),'items':top_five(),
    'notice':'La corroboración automática no equivale a verificar la verdad de los hechos.'}

@app.api_route('/api/carousel/generate', methods=['GET','POST','OPTIONS'])
def generate_carousel(request: Request, payload: dict = None):
    if request.method == 'GET':
        return {'ok': True, 'message': 'Usa POST con JSON para generar el carrusel.'}
    data = payload or {}
    store.init()
    catalog.refresh_public_catalog()
    selection = (data or {}).get('selection') or 'top5'
    slides = int((data or {}).get('slides') or 5)
    style = (data or {}).get('style') or 'Editorial'
    news_ids = (data or {}).get('news_ids') or []
    language = data.get('lang')
    selected = []
    if selection == 'manual' and news_ids:
        ordered = {int(item): idx for idx, item in enumerate(news_ids)}
        rows = store.rows(f"SELECT * FROM news WHERE id IN ({','.join('?' for _ in news_ids)}) AND approved=1 ORDER BY id DESC", tuple(news_ids))
        selected = sorted([convert_row(row) for row in rows], key=lambda item: ordered.get(item['id'], 99999))
        if language in LANGUAGES:
            selected = [item for item in selected if story_language(item['headline'], item['summary']) == language]
            for item in selected:
                if item['mode'] == 'titular_atribuido':
                    item['summary'] = source_excerpt(item['summary'])
    if not selected:
        selected = top_five(language=language)
    if not selected and language in LANGUAGES:
        return {'slides': [], 'style': style, 'count': 0}
    deck = build_carousel_deck(selected, slide_count=slides, style=style, language=language)
    return deck

@app.api_route('/api/carousel/export', methods=['GET','POST','OPTIONS'])
def export_carousel(request: Request, payload: dict = None):
    if request.method == 'GET':
        return {'ok': True, 'message': 'Usa POST con el deck generado para exportar el ZIP.'}
    data = payload or {}
    deck = (data or {}).get('deck') or []
    style = (data or {}).get('style') or 'Editorial'
    zip_bytes = export_carousel_zip(deck, style=style)
    return Response(content=zip_bytes, media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="radar-carrusel.zip"'})

@app.post('/api/auth/register')
def register(data:Registration,req:Request,response:Response):
    rate_guard(req.client.host if req.client else 'anon','register',6,600)
    mail=data.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',mail):raise HTTPException(422,'Correo inválido')
    if not data.terms_accepted or not data.privacy_acknowledged:
        raise HTTPException(422,'Debes aceptar términos y conocer la política de privacidad')
    if store.row('SELECT id FROM users WHERE email=?',(mail,)):raise HTTPException(409,'Correo ya registrado')
    uid=store.exec_('INSERT INTO users(email,pw_hash,role,accepted_at,created_at) VALUES(?,?,?,?,?)',
          (mail,security.hash_password(data.password),'reader',store.now(),store.now()))
    response.set_cookie('radar_session',security.sign_session(uid),max_age=604800,
                        httponly=True,samesite='lax',secure=not config.LOCAL_ONLY)
    return {'id':uid,'email':mail,'role':'reader'}

@app.post('/api/auth/login')
def login(data:Credentials,req:Request,response:Response):
    rate_guard(req.client.host if req.client else 'anon','login',12,300)
    u=store.row('SELECT * FROM users WHERE email=?',(data.email.lower().strip(),))
    if not u or not security.verify_password(data.password,u['pw_hash']):
        raise HTTPException(401,'Credenciales incorrectas')
    response.set_cookie('radar_session',security.sign_session(u['id']),max_age=604800,
                        httponly=True,samesite='lax',secure=not config.LOCAL_ONLY)
    return {'id':u['id'],'email':u['email'],'role':u['role']}

@app.post('/api/auth/logout')
def logout(response:Response):
    response.delete_cookie('radar_session')
    return {'ok':True}

@app.get('/api/auth/me')
def me(req:Request):return {'user':current_user(req)}

@app.post('/api/auth/change-password')
def change_password(data:PasswordChange,user=Depends(require_user)):
    full=store.row('SELECT * FROM users WHERE id=?',(user['id'],))
    if not security.verify_password(data.old_password,full['pw_hash']):
        raise HTTPException(401,'Contraseña actual incorrecta')
    store.exec_('UPDATE users SET pw_hash=? WHERE id=?',(security.hash_password(data.new_password),user['id']))
    return {'ok':True,'message':'Contraseña actualizada'}

@app.post('/api/auth/delete-account')
def delete_account(data:DeleteAccount,response:Response,user=Depends(require_user)):
    full=store.row('SELECT * FROM users WHERE id=?',(user['id'],))
    if not security.verify_password(data.password,full['pw_hash']):
        raise HTTPException(401,'Contraseña incorrecta')
    if full['role']=='admin':
        raise HTTPException(403,'No se puede eliminar el administrador desde esta pantalla')
    store.exec_('DELETE FROM users WHERE id=?',(user['id'],))
    response.delete_cookie('radar_session')
    return {'ok':True}

@app.get('/api/bookmarks')
def bookmarks(user=Depends(require_user)):
    entries = store.rows(
        '''SELECT b.news_id, n.slug, n.approved, n.is_demo FROM bookmarks b
           JOIN news n ON n.id=b.news_id WHERE b.user_id=?''', (user['id'],),
    )
    return {'ids': [entry['news_id'] for entry in entries],
            'slugs': [entry['slug'] for entry in entries if entry['approved'] and (not entry['is_demo'] or demo.is_enabled())]}

@app.post('/api/bookmarks')
def bookmark(data:Preferences,user=Depends(require_user)):
    rec=store.row('SELECT id FROM news WHERE id=? AND approved=1',(data.news_id,))
    if not rec:raise HTTPException(404,'Noticia no disponible')
    current=store.row('SELECT news_id FROM bookmarks WHERE user_id=? AND news_id=?',(user['id'],data.news_id))
    if current:
        store.exec_('DELETE FROM bookmarks WHERE user_id=? AND news_id=?',(user['id'],data.news_id))
        return {'saved':False}
    store.exec_('INSERT INTO bookmarks(user_id,news_id) VALUES(?,?)',(user['id'],data.news_id))
    return {'saved':True}

@app.get('/api/admin/pending')
def pending(user=Depends(require_admin)):
    return [convert_row(x) for x in store.rows('SELECT * FROM news WHERE (approved=0 OR draft_pending=1) AND is_demo=0 ORDER BY published_at DESC LIMIT 150')]

@app.post('/api/admin/review/{news_id}')
def review(news_id:int,data:ReviewInput,user=Depends(require_admin)):
    if data.action not in ('approve','reject'):
        raise HTTPException(422,'Acción debe ser approve o reject')
    rec=store.row('SELECT id FROM news WHERE id=?',(news_id,))
    if not rec:raise HTTPException(404,'Noticia inexistente')
    yes=data.action=='approve'
    full=store.row('SELECT * FROM news WHERE id=?',(news_id,))
    if full['draft_pending']:
        if yes:
            store.exec_('UPDATE news SET headline=?,summary=?,evidence_json=?,mode=?,draft_pending=0,review_needed=0,approved=1,status=?,updated_at=? WHERE id=?',
                (full['draft_headline'],full['draft_summary'],full['draft_evidence'],'gemini_revisado','revision_editorial',store.now(),news_id))
        else:
            store.exec_('UPDATE news SET draft_pending=0,review_needed=0,updated_at=? WHERE id=?',(store.now(),news_id))
    else:
        store.exec_('UPDATE news SET approved=?,review_needed=?,status=?,updated_at=? WHERE id=?',
          (1 if yes else 0,0 if yes else 1,'revision_editorial' if yes else 'rechazada',store.now(),news_id))
    store.exec_('INSERT INTO audit_log(user_id,at,operation,detail) VALUES(?,?,?,?)',
      (user['id'],store.now(),'review',f'{data.action} noticia {news_id}'))
    return {'ok':True,'approved':yes}

@app.post('/api/admin/sources')
def add_source(data:SourceInput,user=Depends(require_admin)):
    try:feeds.validate_public_url(data.feed_url, resolve=False)
    except ValueError as ex:raise HTTPException(422,str(ex))
    if store.row('SELECT id FROM sources WHERE feed_url=?',(data.feed_url,)):
        raise HTTPException(409,'Fuente ya registrada')
    sid=store.exec_('INSERT INTO sources(name,feed_url,homepage,region,rights_note,created_at) VALUES(?,?,?,?,?,?)',
      (data.name,data.feed_url,data.homepage,'Personalizada',data.rights_note,store.now()))
    return {'id':sid,'ok':True}

@app.patch('/api/admin/sources/{source_id}')
def update_source(source_id:int,data:SourceUpdate,user=Depends(require_admin)):
    existing=store.row('SELECT * FROM sources WHERE id=?',(source_id,))
    if not existing:raise HTTPException(404,'Fuente no encontrada')
    new_name=(data.name or existing['name']).strip()
    new_homepage=(data.homepage if data.homepage is not None else existing['homepage']).strip()
    new_rights=(data.rights_note if data.rights_note is not None else existing['rights_note']).strip()
    enabled = existing['enabled'] if data.enabled is None else int(bool(data.enabled))
    if not new_name or len(new_name)<3:raise HTTPException(422,'Nombre de fuente inválido')
    if new_homepage:
        try: feeds.validate_public_url(new_homepage, resolve=False)
        except ValueError as ex: raise HTTPException(422, str(ex))
    store.exec_('UPDATE sources SET name=?,homepage=?,rights_note=?,enabled=? WHERE id=?',
      (new_name,new_homepage,new_rights,enabled,source_id))
    return store.row('SELECT * FROM sources WHERE id=?',(source_id,))

@app.post('/api/admin/collect')
def collect_now(req:Request,user=Depends(require_admin)):
    rate_guard(str(user['id']),'collect',4,600)
    result=collect(enable_ai=True)
    store.exec_('INSERT INTO audit_log(user_id,at,operation,detail) VALUES(?,?,?,?)',
      (user['id'],store.now(),'ingest',json.dumps(result,ensure_ascii=False)[:850]))
    return result

@app.post('/api/internal/collect')
def scheduled_collect(req:Request):
    import hmac
    token=os.getenv('RADAR_CRON_TOKEN','')
    got=req.headers.get('x-radar-token','')
    if not token or not hmac.compare_digest(got,token):
        raise HTTPException(403,'Automatización no autorizada o sin configurar')
    return collect(enable_ai=True)

@app.get('/api/admin/overview')
def admin_overview(user=Depends(require_admin)):
    return {'total':store.row('SELECT COUNT(*) as count FROM news')['count'],
            'pending':store.row('SELECT COUNT(*) as count FROM news WHERE approved=0 OR draft_pending=1')['count'],
            'real':store.row('SELECT COUNT(*) as count FROM news WHERE is_demo=0')['count'],
            'users':store.row('SELECT COUNT(*) as count FROM users')['count']}

@lru_cache(maxsize=8)
def static_revision(path, modified_ns, size):
    return sha256(path.read_bytes()).hexdigest()[:12]


@app.get('/')
def home():
    static_dir = config.ROOT / 'static'
    shell = (static_dir / 'index.html').read_text(encoding='utf-8')
    for filename, placeholder in (('styles.css', '__RADAR_STYLES_VERSION__'), ('app.js', '__RADAR_SCRIPT_VERSION__'),
                                  ('i18n.js', '__RADAR_I18N_VERSION__')):
        path = static_dir / filename
        stat = path.stat()
        shell = shell.replace(placeholder, static_revision(path, stat.st_mtime_ns, stat.st_size))
    return HTMLResponse(shell, headers={'Cache-Control': 'no-cache'})

@app.get('/{route:path}')
def app_shell(route:str):
    if route.startswith('api/') or route.startswith('assets/'):
        raise HTTPException(404)
    return home()
