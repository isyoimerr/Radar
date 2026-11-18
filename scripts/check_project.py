import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from radar.app import app
c=TestClient(app)
for path in ['/','/api/health','/api/news','/api/sources','/api/config','/api/boletin.html','/api/boletin.png']:
    r=c.get(path)
    assert r.status_code==200,(path,r.status_code)
    print('OK',path,len(r.content),'bytes')
print('OK: validación de rutas principales completa')
