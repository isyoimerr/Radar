import sqlite3, json
from pathlib import Path

path = Path(r'C:\Users\ING\Desktop\RADAR_DESCARGA_NUEVA_11NOV (1)\RADAR\data\radar.sqlite3')
out = Path(r'C:\Users\ING\Desktop\RADAR_DESCARGA_NUEVA_11NOV (1)\RADAR\check_db_result.txt')
conn = sqlite3.connect(str(path))
conn.row_factory = sqlite3.Row
count = conn.execute('SELECT COUNT(*) AS c FROM news').fetchone()['c']
rows = [dict(r) for r in conn.execute('SELECT id,headline,image_url,video_url,media_type,status,approved FROM news ORDER BY id DESC LIMIT 10').fetchall()]
out.write_text(json.dumps({'count': count, 'rows': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
print('done')
