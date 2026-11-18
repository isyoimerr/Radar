from radar import pipeline,store,feeds
from radar.gemini import AiFailure
from fastapi.testclient import TestClient
from radar.app import app
import secrets
import pytest
from radar import config
from datetime import datetime, timedelta, timezone

@pytest.fixture(autouse=True)
def temporary_db(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'DB_PATH',tmp_path/'pipeline_test.sqlite3')
    monkeypatch.setattr(pipeline, 'fetch_article_image', lambda *args, **kwargs: '')
    store.init()



def test_two_sources_publish_attributed_and_not_duplicate(monkeypatch):
    keyword='Ensayo de sensores de RADAR '+secrets.token_hex(3)
    def fake_feed(source):
        if source['id']>2:return []
        return [{'title':keyword,'url':f'https://example.org/{source["id"]}/{keyword.split()[-1]}',
            'description':'Resumen original de prueba suficientemente descriptivo',
            'source_name':f'Medio Prueba {source["id"]}',
            'published_at':'2026-11-11T09:00:00+00:00'}]
    monkeypatch.setattr(pipeline,'fetch_feed',fake_feed)
    one=pipeline.collect(enable_ai=False)
    assert one['new']>=1
    records=store.rows('SELECT * FROM news WHERE original_headline=?',(keyword,))
    assert len(records)==1
    assert records[0]['headline']==keyword
    assert records[0]['mode']=='titular_atribuido'
    assert records[0]['approved']==1
    two=pipeline.collect(enable_ai=False)
    assert two['new']==0


def test_ai_draft_kept_unpublished_until_editor_reviews(monkeypatch):
    keyword='Nuevas herramientas de aprendizaje '+secrets.token_hex(4)
    def fake_feed(source):
        if source['id']>2:return []
        return [{'title':keyword,'url':f'https://example.org/prototype/{source["id"]}/{keyword.split()[-1]}',
            'description':'Informe sobre herramientas de aprendizaje en escuelas',
            'source_name':f'Fuente independiente {source["id"]}',
            'published_at':'2026-11-11T10:00:00+00:00'}]
    monkeypatch.setattr(pipeline,'fetch_feed',fake_feed)
    monkeypatch.setattr(pipeline,'generate',lambda *a:{'headline':'Una propuesta editorial reformulada','summary':'Este es un borrador editorial que queda pendiente de comprobación.',
        'evidence':[{'claim':'hay herramientas','source_ids':[1,2]}],'mode':'gemini_borrador'})
    pipeline.collect(enable_ai=True)
    story=store.row('SELECT * FROM news WHERE original_headline=?',(keyword,))
    assert story is not None
    assert story['approved']==1
    assert story['headline']==keyword  # Public title remains original and attributed
    assert story['draft_pending']==1
    assert story['draft_headline']=='Una propuesta editorial reformulada'


def test_feed_parses_multimedia_metadata():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
      <channel>
        <item>
          <title>Evento clave con video</title>
          <link>https://example.com/story</link>
          <description>Resumen sobre una novedad</description>
          <pubDate>Wed, 11 Nov 2026 12:00:00 GMT</pubDate>
          <media:content url="https://example.com/cover.jpg" type="image/jpeg" />
          <media:group>
            <media:content url="https://example.com/video.mp4" type="video/mp4" />
          </media:group>
        </item>
      </channel>
    </rss>
    '''
    item = feeds.parse_feed(xml.encode('utf-8'), 'Canal prueba')[0]
    assert item['image_url'] == 'https://example.com/cover.jpg'
    assert item['video_url'] == 'https://example.com/video.mp4'
    assert item['media_type'] == 'video'


def test_feed_extracts_image_from_html_description_and_meta_tags():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Noticia con imagen en HTML</title>
          <link>https://example.com/article</link>
          <description><![CDATA[<div><img src="https://example.com/inline-image.jpg" /></div>]]></description>
          <pubDate>Wed, 11 Nov 2026 12:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    '''
    item = feeds.parse_feed(xml.encode('utf-8'), 'Canal prueba')[0]
    assert item['image_url'] == 'https://example.com/inline-image.jpg'
    assert feeds.extract_image_from_html('<meta property="og:image" content="https://example.com/meta-image.jpg">') == 'https://example.com/meta-image.jpg'
    assert feeds.extract_image_from_html(
        '<img src="/assets/publisher-logo.svg"><img src="/inline.jpg">'
        '<meta content="/article.jpg?sig=a%2Bb&amp;v=1" property="og:image">',
        'https://example.com/news/article',
    ) == 'https://example.com/article.jpg?sig=a%2Bb&v=1'
    assert feeds.extract_image_from_html(
        '<img alt="Sin foto"><img src="/assets/publisher-logo.svg">',
        'https://example.com/news/article',
    ) == ''
    google_cover = f'https://lh3.googleusercontent.com/{feeds.GOOGLE_NEWS_COVER}=s0-w300'
    assert feeds.preview_image_url(google_cover) == ''
    assert feeds.preview_image_url('https://lh3.googleusercontent.com/article-photo=s0-w300')


def test_single_source_news_is_attributed_and_flagged_for_review(monkeypatch):
    keyword='Desarrollo local con un solo dato '+secrets.token_hex(3)
    def fake_feed(source):
        if source['id']>1:return []
        return [{'title':keyword,'url':f'https://example.org/unico/{keyword.split()[-1]}',
            'description':'Un medio local reporta una iniciativa con una sola referencia.',
            'source_name':'Medio local único','published_at':'2026-11-11T08:30:00+00:00'}]
    monkeypatch.setattr(pipeline,'fetch_feed',fake_feed)
    pipeline.collect(enable_ai=False)
    story=store.row('SELECT * FROM news WHERE original_headline=?',(keyword,))
    assert story is not None
    assert story['approved']==1
    assert story['review_needed']==1
    assert story['status']=='fuente_unica'
    assert pipeline.latest_news(limit=20)[0]['status'] == 'fuente_unica'


def test_api_supports_historical_windows():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(hours=2)
    old = now - timedelta(days=40)
    store.exec_('INSERT INTO news(slug,headline,original_headline,summary,topic,editorial_tone,published_at,updated_at,sources_json,evidence_json,timeline_json,status,review_needed,approved,sensitivity_reason,score,mode,is_demo,image_url,video_url,media_type,fingerprint,draft_headline,draft_summary,draft_evidence,draft_pending) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        ('n_recent','Reciente','Reciente','Resumen reciente','Actualidad','neutral',recent.isoformat(),recent.isoformat(),'[]','[]','[]','cobertura_multiple',0,1,'',10,'titular_atribuido',0,'https://example.com/recent.jpg','','image','hashrecent','','','[]',0))
    store.exec_('INSERT INTO news(slug,headline,original_headline,summary,topic,editorial_tone,published_at,updated_at,sources_json,evidence_json,timeline_json,status,review_needed,approved,sensitivity_reason,score,mode,is_demo,image_url,video_url,media_type,fingerprint,draft_headline,draft_summary,draft_evidence,draft_pending) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        ('n_old','Antigua','Antigua','Resumen antiguo','Actualidad','neutral',old.isoformat(),old.isoformat(),'[]','[]','[]','cobertura_multiple',0,1,'',9,'titular_atribuido',0,'https://example.com/old.jpg','','image','hashold','','','[]',0))
    client = TestClient(app)
    recent_resp = client.get('/api/news?days=7')
    assert recent_resp.status_code == 200
    recent_items = recent_resp.json()['items']
    assert any(item['headline'] == 'Reciente' for item in recent_items)
    assert all(item['headline'] != 'Antigua' for item in recent_items)
