"""Password hashing + short-lived signed sessions; never store plaintext passwords."""
import os, hashlib, hmac, base64, json, time, secrets
from . import config

def hash_password(password):
    salt=os.urandom(16)
    d=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,330_000)
    return 'pbkdf2_sha256$330000$'+base64.urlsafe_b64encode(salt).decode()+'$'+base64.urlsafe_b64encode(d).decode()

def verify_password(pw, stored):
    try:
        _,rounds,salt_b,hash_b=stored.split('$')
        salt=base64.urlsafe_b64decode(salt_b)
        actual=hashlib.pbkdf2_hmac('sha256',pw.encode(),salt,int(rounds))
        return hmac.compare_digest(actual,base64.urlsafe_b64decode(hash_b))
    except Exception: return False

def sign_session(user_id):
    data={'uid':user_id,'exp':int(time.time())+7*24*3600,'nonce':secrets.token_hex(6)}
    b=base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode().rstrip('=')
    sig=hmac.new(config.SESSION_KEY.encode(),b.encode(),hashlib.sha256).hexdigest()
    return b+'.'+sig

def parse_session(cookie):
    if not cookie: return None
    try:
        body,sig=cookie.rsplit('.',1)
        check=hmac.new(config.SESSION_KEY.encode(),body.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,check): return None
        data=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        return data.get('uid') if data.get('exp',0)>time.time() else None
    except Exception: return None
