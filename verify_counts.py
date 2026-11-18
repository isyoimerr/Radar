import json
import sys
sys.path.insert(0, '.')
from radar import store

store.init()
out = {
    'sources': store.row("SELECT COUNT(*) as c FROM sources")['c'],
    'all_news': store.row("SELECT COUNT(*) as c FROM news")['c'],
    'approved_news': store.row("SELECT COUNT(*) as c FROM news WHERE approved=1")['c'],
    'approved_with_image': store.row("SELECT COUNT(*) as c FROM news WHERE approved=1 AND image_url <> ''")['c'],
    'latest': store.rows("SELECT id, headline, topic FROM news WHERE approved=1 ORDER BY published_at DESC LIMIT 5")
}
with open(r'c:\temp\radar_counts.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('done')
