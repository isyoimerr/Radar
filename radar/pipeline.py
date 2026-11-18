"""News pipeline from professor's Colab: RSS -> cleaning -> de-dupe -> bulletin."""
import hashlib, json, re
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from . import catalog, demo, store
from .feeds import fetch_feed, canonical, fetch_article_image, preview_image_url
from .editorial import cluster_articles, grouping_status, independent_source_count, rank, sensitive, topic, TONE, similarity
from .gemini import generate, fallback, AiFailure
from .language import LANGUAGES, source_excerpt, story_language

MAX_ITEMS_PER_SOURCE = 30
MAX_GROUPS = 120


def fallback_image_data(topic='Actualidad', headline='RADAR'):
    label = (headline or topic or 'RADAR').strip()
    label = re.sub(r'\s+', ' ', label)[:34]
    topic_name = (topic or 'Actualidad').strip() or 'Actualidad'
    palette = {
        'Política': ('#0F172A', '#1D4ED8', '#7DD3FC'),
        'Economía': ('#073B4C', '#2EC4B6', '#F4D35E'),
        'Cultura': ('#3F2B56', '#F15BB5', '#FFD166'),
        'Salud': ('#0F766E', '#14B8A6', '#DCFCE7'),
        'Tecnología': ('#111827', '#4F46E5', '#67E8F9'),
        'Ciencia': ('#0F172A', '#2563EB', '#A7F3D0'),
        'Urbanismo': ('#164E63', '#14B8A6', '#CCFBF1'),
        'Actualidad': ('#1F2937', '#0EA5E9', '#F8FAFC'),
    }
    start, end, accent = palette.get(topic_name, palette['Actualidad'])
    svg = f'''
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 900">
      <defs>
        <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="{start}" />
          <stop offset="100%" stop-color="{end}" />
        </linearGradient>
      </defs>
      <rect width="1200" height="900" fill="url(#g)"/>
      <circle cx="930" cy="210" r="220" fill="rgba(255,255,255,0.12)"/>
      <circle cx="250" cy="680" r="260" fill="rgba(255,255,255,0.08)"/>
      <rect x="80" y="690" width="1040" height="120" rx="20" fill="rgba(7,12,18,0.18)"/>
      <text x="90" y="420" font-family="Arial, Helvetica, sans-serif" font-size="72" font-weight="700" fill="#F8FAFC">RADAR</text>
      <text x="90" y="510" font-family="Arial, Helvetica, sans-serif" font-size="30" fill="{accent}">{topic_name.upper()}</text>
      <text x="90" y="627" font-family="Arial, Helvetica, sans-serif" font-size="42" font-weight="700" fill="#F8FAFC">{label}</text>
    </svg>
    '''.strip()
    return 'data:image/svg+xml;charset=utf-8,' + quote(svg)


def normalize_image_url(image_url):
    value = (image_url or '').strip()
    if value.startswith(('data:image/png;', 'data:image/jpeg;', 'data:image/webp;', 'data:image/avif;')):
        return value
    return preview_image_url(value)


def convert_row(record):
    rec=dict(record)
    for k in ('sources_json','evidence_json','timeline_json'):
        rec[k.removesuffix('_json')]=json.loads(rec.pop(k) or '[]')
    for k in ('approved','review_needed','is_demo','draft_pending'): rec[k]=bool(rec[k])
    rec['image_url'] = normalize_image_url(rec.get('image_url'))
    if rec['is_demo'] and not rec['image_url']:
        rec['image_url'] = fallback_image_data(rec['topic'], rec['headline'])
    return rec


def latest_news(topic_name=None, query=None, limit=100, include_sensitive=False, days=None, from_date=None, to_date=None, language=None):
    catalog.refresh_public_catalog()
    sql='SELECT * FROM news WHERE (approved=1 OR review_needed=1)'
    if not demo.is_enabled():
        sql+=' AND is_demo=0'
    args=[]
    if topic_name and topic_name!='Todas':sql+=' AND topic=?';args.append(topic_name)
    if query: sql+=' AND (headline LIKE ? OR summary LIKE ?)';args.extend(('%'+query[:90]+'%','%'+query[:90]+'%'))
    if not include_sensitive: sql+=' AND sensitivity_reason=?';args.append('')
    if days is not None:
        try:
            window=int(days)
        except (TypeError, ValueError): window=0
        if window>0:
            cutoff=(datetime.now(timezone.utc)-timedelta(days=window)).isoformat(timespec='seconds')
            sql+=' AND published_at >= ?'; args.append(cutoff)
    if from_date:
        sql+=' AND published_at >= ?'; args.append(str(from_date))
    if to_date:
        sql+=' AND published_at <= ?'; args.append(str(to_date))
    if language in LANGUAGES:
        sql += ' AND story_language(headline,summary)=?'
        args.append(language)
    sql+=' ORDER BY is_demo ASC, score DESC, published_at DESC LIMIT ?';args.append(max(1,min(limit,200)))
    if language in LANGUAGES:
        with closing(store.connect()) as db:
            db.create_function('story_language', 2, story_language, deterministic=True)
            records = [convert_row(row) for row in db.execute(sql, args)]
        for record in records:
            record['language'] = language
            if record['mode'] == 'titular_atribuido':
                record['summary'] = source_excerpt(record['summary'])
    else:
        records=[convert_row(x) for x in store.rows(sql,args)]
    return [record for record in records if not record['is_demo']] or records

def top_five(language=None):
    records=latest_news(limit=10, language=language)
    return records[:10]


def find_story_image(row):
    for source in json.loads(row['sources_json'] or '[]')[:3]:
        if image := fetch_article_image(source.get('url'), timeout=5):
            return image
    return ''


def backfill_missing_media(limit=50):
    rows = store.rows('SELECT id, sources_json, image_url FROM news WHERE approved=1 AND is_demo=0 ORDER BY published_at DESC')
    missing = [row for row in rows if not normalize_image_url(row['image_url'])][:limit]
    if not missing:
        return 0

    updated = 0
    with ThreadPoolExecutor(max_workers=6) as executor:
        for row, image in zip(missing, executor.map(find_story_image, missing)):
            if image:
                store.exec_('UPDATE news SET image_url=? WHERE id=? AND image_url IS ?', (image, row['id'], row['image_url']))
                updated += 1
    return updated


def collect(enable_ai=True):
    store.init()
    sources=store.rows('SELECT * FROM sources WHERE enabled=1 ORDER BY id')
    ingested=[]; errors=[]
    for src in sources:
        try:ingested.extend(fetch_feed(src)[:MAX_ITEMS_PER_SOURCE])
        except Exception as ex: errors.append(f"{src['name']}: {type(ex).__name__}: {str(ex)[:90]}")
    original_count=len(ingested)
    # Keep the live pass bounded so startup remains fast and the dedupe stage stays responsive.
    groups=cluster_articles(sorted(ingested, key=lambda x: x.get('published_at',''), reverse=True)[:MAX_GROUPS*3])[:MAX_GROUPS]
    inserted=0; updated=0; ai_used=0
    for group in groups:
        first=group[0]; headline=first['title']; date=first['published_at']
        is_sensitive=sensitive(' '.join(x['title']+' '+x['description'][:240] for x in group))
        cat=topic(' '.join(x['title'] for x in group))
        unique_sources=[]; seen=set()
        for x in group:
            key=canonical(x['url'])
            if key not in seen:
                seen.add(key)
                unique_sources.append({'name':x['source_name'],'url':x['url'],
                  'original_title':x['title'],'published_at':x['published_at'],
                  'domain':__import__('urllib.parse',fromlist=['urlparse']).urlparse(x['url']).hostname or ''})
        independent=independent_source_count(group)
        # A single source is not ideal, but in a local monitoring workflow a valid, non-sensitive story
        # still needs to be visible for editorial review rather than silently disappearing from the feed.
        needs_review = is_sensitive or independent < 2
        # Avoid recurring calls to Gemini for items already known.
        existing=None
        current=store.rows('SELECT * FROM news WHERE is_demo=0 ORDER BY updated_at DESC LIMIT 400')
        links={canonical(s['url']) for s in unique_sources}
        for old in current:
            old_sources=json.loads(old['sources_json'])
            old_links={canonical(s['url']) for s in old_sources}
            if links & old_links or similarity(headline,old['original_headline']) >= .86:
                existing=old;break
        image_url=next((x['image_url'] for x in group if x.get('image_url')), '')
        if existing:
            if image_url and not normalize_image_url(existing['image_url']):
                store.exec_('UPDATE news SET image_url=? WHERE id=? AND image_url IS ?', (image_url, existing['id'], existing['image_url']))
            old_sources=json.loads(existing['sources_json'])
            merged=old_sources + [s for s in unique_sources if canonical(s['url']) not in {canonical(z['url']) for z in old_sources}]
            if len(merged)>len(old_sources):
                status='cobertura_multiple' if independent >= 2 else 'fuente_unica'
                store.exec_('UPDATE news SET sources_json=?,updated_at=?,score=?,status=?,review_needed=? WHERE id=?',
                    (json.dumps(merged,ensure_ascii=False),store.now(),max(float(existing['score']),rank(group)),
                     status,1 if needs_review else 0,existing['id']))
                updated+=1
            continue
        safe_version=fallback(group)
        candidate=None
        if enable_ai and not is_sensitive and independent >= 2:
            try:
                candidate=generate(group,cat,TONE.get(cat,TONE['Actualidad']))
                ai_used+=1
            except AiFailure as ex:
                errors.append(f'IA: {str(ex)[:100]}')
        video_url=next((x.get('video_url','') for x in group if x.get('video_url')), '')
        media_type='video' if video_url else 'image'
        fingerprint=hashlib.sha256(first['url'].encode()).hexdigest()
        slug='n-'+fingerprint[:14]
        state=grouping_status(group)
        timeline=[{'at':s['published_at'],'label':'Publicación registrada: '+s['name']} for s in unique_sources[:7]]
        approved = 1 if not is_sensitive and independent >= 1 else 0
        review_needed = 1 if needs_review else 0
        draft_pending = 1 if candidate and not is_sensitive and independent >= 1 else 0
        # Source-attributed headlines are visible; AI rewrites require editorial review.
        try:
            store.exec_('''INSERT INTO news(slug,headline,original_headline,summary,topic,editorial_tone,published_at,updated_at,sources_json,evidence_json,timeline_json,status,review_needed,approved,sensitivity_reason,score,mode,is_demo,image_url,video_url,media_type,fingerprint,draft_headline,draft_summary,draft_evidence,draft_pending)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (slug,safe_version['headline'],headline,safe_version['summary'],cat,TONE.get(cat,'neutral'),date,store.now(),
                json.dumps(unique_sources,ensure_ascii=False),'[]',
                json.dumps(timeline,ensure_ascii=False),state,review_needed,approved,
                'Revisión obligatoria por contenido sensible' if is_sensitive else '',rank(group),safe_version['mode'],0,image_url,video_url,media_type,fingerprint,
                candidate['headline'] if candidate else '',candidate['summary'] if candidate else '',
                json.dumps(candidate['evidence'],ensure_ascii=False) if candidate else '[]',draft_pending))
            inserted+=1
        except Exception as ex:errors.append(f'Al guardar: {type(ex).__name__}: {str(ex)[:120]}')
    if inserted:
        # Edition is editorial selection of eligible, non-sensitive published stories only.
        ids=[x['id'] for x in top_five() if not x['is_demo']]
        if ids:
            store.exec_('INSERT INTO editions(created_at,title,news_ids_json,mode) VALUES(?,?,?,?)',
                (store.now(),'Boletín de actualidad',json.dumps(ids),'automatico_con_fuentes'))
    backfill_missing_media(limit=50)
    run={'fetched':original_count,'new':inserted,'updated':updated,'ai':ai_used,'errors':errors[:30],
         'mode':'gemini_y_respaldo' if ai_used else 'sin_ia_o_respaldo','at':store.now()}
    store.exec_('INSERT INTO pipeline_runs(at,fetched,new_count,errors_json,mode) VALUES(?,?,?,?,?)',
        (run['at'],original_count,inserted,json.dumps(run['errors'],ensure_ascii=False),run['mode']))
    return run
