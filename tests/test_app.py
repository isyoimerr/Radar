import os
import secrets
from threading import Event
from fastapi.testclient import TestClient
from radar import config, demo, store
from radar.app import app


def test_demo_seed_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv('RADAR_ENABLE_DEMO_DATA', '0')
    db = store.connect()
    db.execute('DELETE FROM news')
    db.execute('DELETE FROM sources')
    db.commit()
    demo.seed()
    assert store.row('SELECT id FROM news LIMIT 1') is None


def test_real_sources_are_seeded_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv('RADAR_ENABLE_DEMO_DATA', '0')
    monkeypatch.setattr('radar.config.DB_PATH', tmp_path / 'sources_seed.sqlite3')
    store.init()
    names = {row['name'] for row in store.rows('SELECT name FROM sources')}
    assert any('BBC' in name or 'The Guardian' in name or 'El Tiempo' in name for name in names)


def test_placeholder_fallback_is_never_inserted():
    db = store.connect()
    db.execute('DELETE FROM news WHERE lower(headline) LIKE ? OR sources_json LIKE ?', ('%fallback%', '%RADAR local fallback%'))
    db.commit()
    app.bootstrap_news_if_empty()
    bad_rows = store.rows('SELECT id, headline, sources_json FROM news WHERE lower(headline) LIKE ? OR sources_json LIKE ?', ('%fallback%', '%RADAR local fallback%'))
    assert bad_rows == []


def test_bootstrap_starts_collection_when_news_are_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'startup.sqlite3')
    store.init()
    scheduled = []
    monkeypatch.setattr('radar.app._schedule_collect', lambda **kwargs: scheduled.append(kwargs))
    app.bootstrap_news_if_empty()
    assert scheduled == [{'delay_seconds': 2.0, 'name': 'radar-startup-collect'}]


def test_public_endpoints(monkeypatch):
    monkeypatch.setattr('radar.app._news_needs_refresh', lambda **kwargs: False)
    client=TestClient(app)
    for path in ['/', '/api/health','/api/news','/api/sources','/api/config','/api/boletin.html','/api/boletin.png']:
        assert client.get(path).status_code==200
    assert len(client.get('/api/news').json()['top'])<=10
    assert client.get('/api/boletin.png').content.startswith(b'\x89PNG')


def test_local_origins_are_allowed_for_browser_requests():
    allowed = {origin.rstrip('/') for origin in config.TRUSTED_ORIGINS}
    assert 'http://localhost:8000' in allowed
    assert 'http://127.0.0.1:8000' in allowed


def test_carousel_generation_and_zip_export(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'carousel.sqlite3')
    monkeypatch.setattr('radar.app._news_needs_refresh', lambda **kwargs: False)
    store.init()
    titles = [
        'The council has approved a new plan for public transport',
        'Researchers share the results of a study on urban trees',
        'Local schools expand access to free meals for students',
        'A museum opens an exhibition about the history of radio',
        'The city will build new bike lanes across the town',
        'La ciudad anunció un plan de movilidad para los barrios',
    ]
    ids = [
        store.exec_(
            '''INSERT INTO news(slug,headline,original_headline,summary,topic,editorial_tone,published_at,updated_at,approved)
               VALUES(?,?,?,?,?,?,?,?,1)''',
            (f'carousel-{index}', title, title, '', 'Actualidad', 'neutral', store.now(), store.now()),
        )
        for index, title in enumerate(titles)
    ]
    client = TestClient(app)
    english = client.get('/api/news?lang=en').json()
    spanish = client.get('/api/news?lang=es').json()
    assert {item['id'] for item in english['items']} == set(ids[:-1])
    assert [item['id'] for item in spanish['top']] == ids[-1:]
    gen = client.post('/api/carousel/generate', json={'news_ids': ids, 'slides': 5, 'style': 'Editorial', 'selection': 'manual', 'lang': 'en'})
    assert gen.status_code == 200, gen.text
    deck = gen.json()
    assert deck['slides']
    assert len(deck['slides']) == 5
    assert all(slide['language'] == 'en' and slide['category'] == 'Current affairs' for slide in deck['slides'])
    assert deck['slides'][0]['layout'] in {'cover', 'feature'}
    export = client.post('/api/carousel/export', json={'deck': deck['slides'], 'style': 'Editorial'})
    assert export.status_code == 200, export.text
    assert export.headers['content-type'].startswith('application/zip')
    assert export.content.startswith(b'PK')


def test_news_refreshes_when_cache_is_stale(monkeypatch, tmp_path):
    monkeypatch.setenv('RADAR_ENABLE_DEMO_DATA', '0')
    monkeypatch.setattr('radar.config.DB_PATH', tmp_path / 'stale-refresh.sqlite3')
    from radar import store
    store.init()
    store.exec_('INSERT INTO news(slug,headline,original_headline,summary,topic,editorial_tone,published_at,updated_at,sources_json,evidence_json,timeline_json,status,review_needed,approved,sensitivity_reason,score,mode,is_demo,image_url,video_url,media_type,fingerprint,draft_headline,draft_summary,draft_evidence,draft_pending) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        ('n-stale-1','Titular antiguo','Titular antiguo','Resumen antiguo','Actualidad','neutral','2024-01-01T00:00:00+00:00','2024-01-01T00:00:00+00:00','[]','[]','[]','fuente_unica',0,1,'',1.0,'sin_ia',0,'','','image','abc123','','','[]',0))
    store.exec_('INSERT INTO pipeline_runs(at,fetched,new_count,errors_json,mode) VALUES(?,?,?,?,?)',
        ('2024-01-01T00:00:00+00:00',0,0,'[]','manual'))
    calls = {'count': 0}
    def fake_collect(enable_ai=True):
        calls['count'] += 1
        store.exec_('INSERT INTO news(slug,headline,original_headline,summary,topic,editorial_tone,published_at,updated_at,sources_json,evidence_json,timeline_json,status,review_needed,approved,sensitivity_reason,score,mode,is_demo,image_url,video_url,media_type,fingerprint,draft_headline,draft_summary,draft_evidence,draft_pending) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('n-fresh-1','Titular fresco','Titular fresco','Resumen fresco','Actualidad','neutral','2026-11-11T12:00:00+00:00','2026-11-11T12:00:00+00:00','[]','[]','[]','cobertura_multiple',0,1,'',2.0,'sin_ia',0,'','','image','fresh-1','','','[]',0))
        return {'fetched': 1, 'new': 1, 'updated': 0, 'errors': []}
    monkeypatch.setattr('radar.app.collect', fake_collect)
    client = TestClient(app)
    response = client.get('/api/news?limit=10')
    assert response.status_code == 200
    assert calls['count'] == 1
    assert any(item['headline'] == 'Titular fresco' for item in response.json()['items'])


def test_five_slide_deck_uses_distinct_editorial_layouts():
    from radar.export import build_carousel_deck
    stories = [
        {'headline': 'Primera noticia', 'summary': 'Resumen largo', 'topic': 'Política', 'published_at': '2026-11-10T00:00:00+00:00', 'sources': [{'name': 'El País'}], 'image_url': 'https://example.com/a.jpg'},
        {'headline': 'Segunda noticia', 'summary': 'Resumen largo', 'topic': 'Economía', 'published_at': '2026-11-10T00:00:00+00:00', 'sources': [{'name': 'Reuters'}], 'image_url': 'https://example.com/b.jpg'},
        {'headline': 'Tercera noticia', 'summary': 'Resumen largo', 'topic': 'Salud', 'published_at': '2026-11-10T00:00:00+00:00', 'sources': [{'name': 'Nature'}], 'image_url': 'https://example.com/c.jpg'},
        {'headline': 'Cuarta noticia', 'summary': 'Resumen largo', 'topic': 'Tecnología', 'published_at': '2026-11-10T00:00:00+00:00', 'sources': [{'name': 'The Verge'}], 'image_url': 'https://example.com/d.jpg'},
        {'headline': 'Quinta noticia', 'summary': 'Resumen largo', 'topic': 'Cultura', 'published_at': '2026-11-10T00:00:00+00:00', 'sources': [{'name': 'Guardian'}], 'image_url': 'https://example.com/e.jpg'},
    ]
    deck = build_carousel_deck(stories, slide_count=5, style='Editorial')
    assert len(deck['slides']) == 5
    assert len({slide['layout'] for slide in deck['slides']}) >= 4
    assert deck['slides'][0]['layout'] == 'cover'


def test_missing_preview_is_recovered_from_original_article(monkeypatch, tmp_path):
    monkeypatch.setenv('RADAR_ENABLE_DEMO_DATA', '0')
    monkeypatch.setattr('radar.config.DB_PATH', tmp_path / 'media-normalization.sqlite3')
    from radar import store
    from radar.pipeline import backfill_missing_media, latest_news
    store.init()
    store.exec_('INSERT INTO news(slug,headline,original_headline,summary,topic,editorial_tone,published_at,updated_at,sources_json,evidence_json,timeline_json,status,review_needed,approved,sensitivity_reason,score,mode,is_demo,image_url,video_url,media_type,fingerprint,draft_headline,draft_summary,draft_evidence,draft_pending) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        ('n-bad-media','Titular con foto rota','Titular con foto rota','Resumen','Economía','neutral','2026-11-11T12:00:00+00:00','2026-11-11T12:00:00+00:00','[{"url":"https://example.com/article"}]','[]','[]','fuente_unica',0,1,'',1.0,'sin_ia',0,'data:image/svg+xml;charset=utf-8,legacy','','image','abc-bad','','','[]',0))
    assert latest_news(limit=10)[0]['image_url'] == ''

    def article_image(url, timeout):
        assert url == 'https://example.com/article'
        return 'https://example.com/photo.jpg'

    monkeypatch.setattr('radar.pipeline.fetch_article_image', article_image)
    assert backfill_missing_media() == 1
    assert latest_news(limit=10)[0]['image_url'] == 'https://example.com/photo.jpg'
    assert backfill_missing_media() == 0


def test_news_endpoint_does_not_block_on_background_refresh(monkeypatch, tmp_path):
    monkeypatch.setenv('RADAR_ENABLE_DEMO_DATA', '0')
    monkeypatch.setattr('radar.config.DB_PATH', tmp_path / 'background-refresh.sqlite3')
    store.init()
    monkeypatch.setattr('radar.app._news_needs_refresh', lambda min_recent_items=8, stale_seconds=None: True)
    started = Event()
    release = Event()
    finished = Event()
    def collect():
        started.set()
        release.wait(timeout=5)
        finished.set()
    monkeypatch.setattr('radar.app._run_collect_cycle', collect)
    try:
        response = TestClient(app).get('/api/news?limit=5')
        assert response.status_code == 200
        assert started.wait(timeout=1)
        assert not finished.is_set()
    finally:
        release.set()
        finished.wait(timeout=1)


def test_registration_bookmarks_and_auth(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'bookmarks.sqlite3')
    monkeypatch.setattr('radar.app._news_needs_refresh', lambda **kwargs: False)
    store.init()
    store.exec_(
        '''INSERT INTO news(slug,headline,original_headline,summary,topic,editorial_tone,published_at,updated_at,approved)
           VALUES(?,?,?,?,?,?,?,?,1)''',
        ('saved-story', 'Una noticia para guardar', 'Una noticia para guardar', '', 'Actualidad', 'neutral', store.now(), store.now()),
    )
    client=TestClient(app)
    email=f"qa-{secrets.token_hex(5)}@example.com"
    data={'email':email,'password':'TestPassword_123','terms_accepted':True,'privacy_acknowledged':True}
    assert client.post('/api/auth/register',json={**data,'terms_accepted':False}).status_code==422
    r=client.post('/api/auth/register',json=data)
    assert r.status_code==200
    assert client.get('/api/auth/me').json()['user']['email']==email
    story=client.get('/api/news').json()['items'][0]
    b=client.post('/api/bookmarks',json={'news_id':story['id']})
    assert b.status_code==200 and b.json()['saved']
    assert client.get('/api/bookmarks').json() == {'ids': [story['id']], 'slugs': [story['slug']]}
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/bookmarks').status_code==401
    assert client.post('/api/auth/login',json={'email':email,'password':'TestPassword_123'}).status_code==200

def test_cron_needs_token_and_admin_needs_login():
    client=TestClient(app)
    assert client.post('/api/internal/collect').status_code==403
    assert client.get('/api/admin/pending').status_code==401
    assert client.post('/api/admin/collect').status_code==401
