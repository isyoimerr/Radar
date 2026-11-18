"""Local entrypoint. Use: python run.py"""
import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from radar.app import app  # Import the workspace app explicitly to avoid stale installed packages.

if __name__ == '__main__':
    print('\nRADAR local: http://localhost:8000')
    print('Carga fuentes RSS públicas y usa un respaldo seguro si no hay conexión.')
    print('Para la cuenta de administrador inicial, revisa data/admin_credentials.txt\n')
    uvicorn.run(app, host=os.getenv('HOST', '127.0.0.1'),
                port=int(os.getenv('PORT', '8000')), reload=False)
