from radar.editorial import cluster_articles, topic, sensitive, similarity
from radar.feeds import canonical, parse_feed, validate_public_url
from radar.gemini import fallback
import pytest

def test_topic_tone():
    assert topic('Universidad desarrolla herramienta de inteligencia artificial')=='Tecnología'
    assert sensitive('Denuncian presunto fraude por una persona')
    assert not sensitive('Una universidad desarrolla nuevos algoritmos')

def test_dedupe_does_not_duplicate_identical_links():
    examples=[{'title':'La universidad lanza un nuevo laboratorio de IA','url':'https://example.org/a','published_at':'2026-11-11T10:00:00+00:00'},
              {'title':'La universidad lanza un nuevo laboratorio de IA','url':'https://example.org/a','published_at':'2026-11-11T11:00:00+00:00'},
              {'title':'Inauguran nuevo laboratorio de inteligencia artificial en la universidad','url':'https://example.org/b','published_at':'2026-11-11T11:00:00+00:00'}]
    groups=cluster_articles(examples)
    assert sum(len(g) for g in groups)==2
    assert similarity(examples[0]['title'],examples[1]['title'])==1

def test_canonical():
    assert canonical('https://example.org/note?utm_source=x&x=1#section')=='https://example.org/note?x=1'

def test_rss_from_bytes():
    body=b'<rss version="2.0"><channel><item><title>News headline</title><link>https://example.org/a</link><pubDate>Wed, 11 Nov 2026 12:00:00 GMT</pubDate><description>Brief description</description></item></channel></rss>'
    data=parse_feed(body,'Prueba')
    assert len(data)==1 and data[0]['description']=='Brief description'

def test_fallback_never_rewrites_without_evidence():
    sample=[{'title':'Titular de fuente original','description':'Un extracto breve','url':'https://example.org/a'}]
    result=fallback(sample)
    assert result['headline']=='Titular de fuente original'
    assert result['mode']=='titular_atribuido'
    assert not result['evidence']

def test_private_feeds_rejected():
    with pytest.raises(ValueError):validate_public_url('http://localhost:8000/private')
    with pytest.raises(ValueError):validate_public_url('https://127.0.0.1/private')
