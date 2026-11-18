import sys, json
sys.path.insert(0, '.')
from radar import store
from radar.feeds import fetch_feed
src = store.row("SELECT * FROM sources WHERE id=1")
print('SOURCE', src['name'], src['feed_url'])
items = fetch_feed(src, timeout=12)
print('ITEMS', len(items))
for i, x in enumerate(items[:3], 1):
    print(i, x.get('title','')[:120], '|', x.get('image_url','')[:200], '|', x.get('url','')[:200])
