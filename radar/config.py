"""Configuration, safe defaults and local private state."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERCEL_ENV = bool(os.getenv('VERCEL'))
if VERCEL_ENV:
    os.environ.setdefault('RADAR_DATA_DIR', '/tmp/radar')
    os.environ.setdefault('RADAR_DISABLE_BACKGROUND_SCHEDULER', '1')
    os.environ.setdefault('RADAR_LOCAL_ONLY', '0')

def load_env():
    p = ROOT / '.env'
    if not p.exists():
        return
    for raw in p.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()
DATA_DIR = Path(os.getenv('RADAR_DATA_DIR', str(ROOT/'data')))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'radar.sqlite3'
SESSION_FILE = DATA_DIR / '.session_key'
if os.getenv('RADAR_SESSION_KEY'):
    SESSION_KEY = os.getenv('RADAR_SESSION_KEY')
else:
    if not SESSION_FILE.exists():
        SESSION_FILE.write_text(secrets.token_urlsafe(48), encoding='utf-8')
        try: SESSION_FILE.chmod(0o600)
        except OSError: pass
    SESSION_KEY = SESSION_FILE.read_text(encoding='utf-8').strip()
GEMINI_KEY = os.getenv('GEMINI_API_KEY','').strip()
GEMINI_MODEL = os.getenv('GEMINI_MODEL','gemini-3.8-flash').strip()
# Gemini 3.x: leave sampling at provider default, as recommended by Google.
TEMPERATURE = os.getenv('GEMINI_TEMPERATURE','').strip()
PUBLIC_URL = os.getenv('PUBLIC_URL','http://localhost:8000').rstrip('/')
LOCAL_ONLY = os.getenv('RADAR_LOCAL_ONLY', '1') == '1'
_default_origins = {
    PUBLIC_URL,
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:8001',
    'http://127.0.0.1:8001',
    'http://[::1]:8000',
    'http://[::1]:8001',
}
trusted = {
    s.strip().rstrip('/')
    for s in os.getenv('TRUSTED_ORIGINS', '').split(',')
    if s.strip()
}
trusted |= _default_origins
for host in ('localhost', '127.0.0.1', '[::1]'):
    for port in ('8000', '8001'):
        trusted.add(f'http://{host}:{port}')
        trusted.add(f'https://{host}:{port}')
TRUSTED_ORIGINS = sorted(trusted)
