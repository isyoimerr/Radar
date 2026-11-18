import json
from io import BytesIO

from fastapi.testclient import TestClient

from radar import catalog, config, store
from radar.app import app


def test_vercel_bootstrap_reads_bundled_news_without_a_remote_catalog(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'catalog.sqlite3')
    monkeypatch.setattr(config, 'VERCEL_ENV', True)
    monkeypatch.setattr(catalog, '_next_refresh', 0.0)
    def offline(*args, **kwargs):
        raise OSError('offline')

    monkeypatch.setattr(catalog, 'urlopen', offline)
    store.init()
    catalog.seed_bundled_catalog()
    client = TestClient(app)

    for language in ('es', 'en'):
        response = client.get('/api/news', params={'lang': language, 'limit': 2})
        assert response.status_code == 200
        items = response.json()['items']
        assert len(items) == 2
        assert all(item['language'] == language and not item['is_demo'] for item in items)
        article = client.get(f"/api/news/{items[0]['slug']}")
        assert article.status_code == 200
        assert article.json()['id'] == items[0]['id']


def test_vercel_refresh_merges_new_items_with_the_bundled_catalog(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'refresh.sqlite3')
    monkeypatch.setattr(config, 'VERCEL_ENV', True)
    monkeypatch.setattr(catalog, '_next_refresh', 0.0)
    store.init()
    catalog.seed_bundled_catalog()
    initial = store.row('SELECT COUNT(*) AS count FROM news')['count']

    example = json.loads(catalog.BUNDLED_CATALOG.read_bytes())['items'][0]
    example['slug'] = 'catalog-refresh-test'
    payload = json.dumps({'version': 1, 'items': [example]}).encode()
    monkeypatch.setattr(catalog, 'urlopen', lambda *args, **kwargs: BytesIO(payload))

    catalog.refresh_public_catalog()
    assert store.row('SELECT COUNT(*) AS count FROM news')['count'] == initial + 1
