"""SQLite repository; safe bind parameters and short-lived connections."""
import json
import sqlite3
from datetime import datetime, timezone
from . import config

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

def connect():
    c=sqlite3.connect(str(config.DB_PATH), timeout=20)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA journal_mode=WAL')
    return c

def init():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS sources(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, feed_url TEXT NOT NULL UNIQUE,
            homepage TEXT NOT NULL DEFAULT '', region TEXT NOT NULL DEFAULT 'Internacional',
            enabled INTEGER NOT NULL DEFAULT 1, rights_note TEXT NOT NULL DEFAULT 'Consultar términos del medio', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS news(
            id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, headline TEXT NOT NULL,
            original_headline TEXT NOT NULL, summary TEXT NOT NULL,
            topic TEXT NOT NULL, editorial_tone TEXT NOT NULL, published_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, sources_json TEXT NOT NULL DEFAULT '[]',
            evidence_json TEXT NOT NULL DEFAULT '[]', timeline_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'fuente_unica',
            review_needed INTEGER NOT NULL DEFAULT 1, approved INTEGER NOT NULL DEFAULT 0,
            sensitivity_reason TEXT NOT NULL DEFAULT '', score REAL NOT NULL DEFAULT 0,
            mode TEXT NOT NULL DEFAULT 'sin_ia', is_demo INTEGER NOT NULL DEFAULT 0,
            image_url TEXT NOT NULL DEFAULT '', video_url TEXT NOT NULL DEFAULT '',
            media_type TEXT NOT NULL DEFAULT 'image', fingerprint TEXT NOT NULL DEFAULT '',
            draft_headline TEXT NOT NULL DEFAULT '', draft_summary TEXT NOT NULL DEFAULT '',
            draft_evidence TEXT NOT NULL DEFAULT '[]', draft_pending INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, pw_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'reader', accepted_at TEXT NOT NULL,
            created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bookmarks(
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            news_id INTEGER NOT NULL REFERENCES news(id) ON DELETE CASCADE,
            PRIMARY KEY(user_id,news_id));
        CREATE TABLE IF NOT EXISTS editions(
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL,
            news_ids_json TEXT NOT NULL, mode TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pipeline_runs(
            id INTEGER PRIMARY KEY, at TEXT NOT NULL, fetched INTEGER NOT NULL,
            new_count INTEGER NOT NULL, errors_json TEXT NOT NULL, mode TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY, user_id INTEGER, at TEXT NOT NULL,
            operation TEXT NOT NULL, detail TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_news_topic ON news(topic);
        ''')
        existing_columns={r[1] for r in db.execute('PRAGMA table_info(news)').fetchall()}
        for col, typ in [('draft_headline',"TEXT NOT NULL DEFAULT ''"),('draft_summary',"TEXT NOT NULL DEFAULT ''"),('draft_evidence',"TEXT NOT NULL DEFAULT '[]'"),('draft_pending','INTEGER NOT NULL DEFAULT 0'),('video_url',"TEXT NOT NULL DEFAULT ''"),('media_type',"TEXT NOT NULL DEFAULT 'image'")]:
            if col not in existing_columns: db.execute(f'ALTER TABLE news ADD COLUMN {col} {typ}')
        default_sources=[
            ('BBC Mundo','https://feeds.bbci.co.uk/mundo/rss.xml','https://www.bbc.com/mundo','Internacional','BBC Mundo RSS'),
            ('BBC News','https://feeds.bbci.co.uk/news/world/rss.xml','https://www.bbc.com/news','Internacional','BBC News RSS'),
            ('The Guardian World','https://www.theguardian.com/world/rss','https://www.theguardian.com/world','Internacional','The Guardian RSS'),
            ('Al Jazeera','https://www.aljazeera.com/xml/rss/all.xml','https://www.aljazeera.com/','Internacional','Al Jazeera RSS'),
            ('DW Español','https://rss.dw.com/rdf/rss-sp-all','https://www.dw.com/es/','Internacional','DW Español RSS'),
            ('Google Noticias Colombia','https://news.google.com/rss/search?q=Colombia&hl=es-419&gl=CO&ceid=CO:es-419','https://news.google.com/','Colombia','Google Noticias RSS'),
            ('TechCrunch','https://techcrunch.com/feed/','https://techcrunch.com/','Tecnología','TechCrunch RSS'),
            ('The Verge','https://www.theverge.com/rss/index.xml','https://www.theverge.com/','Tecnología','The Verge RSS'),
            ('CNBC','https://www.cnbc.com/id/100003114/device/rss/rss.html','https://www.cnbc.com/','Economía','CNBC RSS'),
        ]
        bad_urls={
            'https://feeds.reuters.com/reuters/worldNews',
            'https://feeds.reuters.com/reuters/technologyNews',
            'https://feeds.reuters.com/reuters/businessNews',
            'https://feeds.apnews.com/rss/apf-topnews.xml',
            'https://www.elespectador.com/rss/',
            'https://www.eltiempo.com/rss/colombia.xml',
            'https://www.nasa.gov/rss/dyn/breaking_news.rss',
            'https://www.jpl.nasa.gov/feeds/news/',
            'https://www.wired.com/feed/rss',
            'https://www.nytimes.com/section/world',
            'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
        }
        if bad_urls:
            db.execute('UPDATE sources SET enabled=0 WHERE feed_url IN (%s)' % ','.join('?' for _ in bad_urls), tuple(sorted(bad_urls)))
        existing_sources={row['feed_url'] for row in db.execute('SELECT feed_url FROM sources').fetchall()}
        for name, feed_url, homepage, region, rights_note in default_sources:
            if feed_url not in existing_sources:
                db.execute('INSERT INTO sources(name,feed_url,homepage,region,rights_note,enabled,created_at) VALUES(?,?,?,?,?,?,?)',
                    (name, feed_url, homepage, region, rights_note, 1, now()))
        for name, feed_url, homepage, region, rights_note in default_sources:
            if not db.execute('SELECT 1 FROM sources WHERE feed_url=?',(feed_url,)).fetchone():
                db.execute('INSERT INTO sources(name,feed_url,homepage,region,rights_note,enabled,created_at) VALUES(?,?,?,?,?,?,?)',
                    (name, feed_url, homepage, region, rights_note, 1, now()))
        db.execute('UPDATE sources SET enabled=1 WHERE feed_url IN (%s)' % ','.join('?' for _ in [url for _, url, _, _, _ in default_sources]), tuple(url for _, url, _, _, _ in default_sources))

def rows(query, args=()):
    with connect() as db: return [dict(x) for x in db.execute(query,args).fetchall()]

def row(query,args=()):
    with connect() as db:
        r=db.execute(query,args).fetchone()
        return dict(r) if r else None

def exec_(query,args=()):
    with connect() as db:
        r=db.execute(query,args)
        return r.lastrowid
