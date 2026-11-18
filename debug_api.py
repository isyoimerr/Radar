import json, sys, sqlite3
from pathlib import Path
sys.path.insert(0, '.')
from radar import config, store

print('ROOT', config.ROOT)
print('DB', config.DB_PATH)
print('NEWS_COUNT', store.row('SELECT COUNT(*) AS c FROM news')['c'])
rows = store.rows('SELECT id, slug, headline, image_url, video_url, media_type, approved, status FROM news ORDER BY id DESC LIMIT 10')
Path('debug_news_rows.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
print('WROTE', 'debug_news_rows.json')
