"""Public RSS snapshot for deployments with an ephemeral filesystem."""

import hashlib
import json
import logging
import threading
import time
from contextlib import closing
from urllib.request import urlopen

from . import config, store
from .language import story_language

PUBLIC_CATALOG_URL = 'https://raw.githubusercontent.com/isyoimerr/Radar/radar-feed/catalog.json'
BUNDLED_CATALOG = config.ROOT / 'static' / 'catalog.json'
MAX_BYTES = 2_000_000
PUBLIC_FIELDS = (
    'slug', 'headline', 'original_headline', 'summary', 'topic', 'editorial_tone',
    'published_at', 'updated_at', 'sources_json', 'timeline_json', 'status',
    'score', 'mode', 'image_url', 'video_url', 'media_type', 'fingerprint',
)
_refresh_lock = threading.Lock()
_next_refresh = 0.0
_logger = logging.getLogger(__name__)


def export_catalog(path):
    """Write only public information, independently of local authentication data."""
    columns = ', '.join(PUBLIC_FIELDS)
    items = []
    for language in ('es', 'en'):
        with closing(store.connect()) as db:
            db.create_function('story_language', 2, story_language, deterministic=True)
            rows = db.execute(
                f"""SELECT {columns} FROM news
                    WHERE approved=1 AND is_demo=0 AND sensitivity_reason=''
                      AND mode='titular_atribuido' AND story_language(headline, summary)=?
                    ORDER BY published_at DESC LIMIT 100""",
                (language,),
            )
            items.extend(dict(row) for row in rows)
    if not items:
        raise ValueError('La ronda no produjo noticias públicas para el catálogo.')
    path.write_text(json.dumps({'version': 1, 'items': items}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return len(items)


def import_catalog(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('Catálogo público demasiado grande.')
    document = json.loads(raw)
    if document.get('version') != 1 or not isinstance(document.get('items'), list):
        raise ValueError('Formato de catálogo público desconocido.')
    rows = []
    for item in document['items']:
        if not isinstance(item.get('slug'), str) or not item['slug'] or item.get('mode') != 'titular_atribuido':
            raise ValueError('Entrada pública inválida.')
        # Use the same numeric identity when different instances handle a carousel.
        news_id = int.from_bytes(hashlib.sha256(item['slug'].encode()).digest()[:6], 'big')
        rows.append((news_id, *(item[field] for field in PUBLIC_FIELDS), int(item['status'] == 'fuente_unica')))
    if not rows:
        return
    columns = ', '.join(('id', *PUBLIC_FIELDS, 'review_needed'))
    values = ', '.join('?' for _ in range(len(PUBLIC_FIELDS) + 2))
    with closing(store.connect()) as db, db:
        db.executemany(
            f'INSERT INTO news({columns}, approved) VALUES({values}, 1) ON CONFLICT DO NOTHING',
            rows,
        )


def seed_bundled_catalog():
    if config.VERCEL_ENV:
        try:
            import_catalog(BUNDLED_CATALOG.read_bytes())
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            _logger.warning('Catálogo RSS empaquetado no disponible (%s)', type(exc).__name__)


def refresh_public_catalog():
    """Try the rolling snapshot while other requests can still read the bundled one."""
    global _next_refresh
    if not config.VERCEL_ENV or time.monotonic() < _next_refresh or not _refresh_lock.acquire(blocking=False):
        return
    try:
        if time.monotonic() < _next_refresh:
            return
        _next_refresh = time.monotonic() + 900
        with urlopen(PUBLIC_CATALOG_URL, timeout=2) as response:
            import_catalog(response.read(MAX_BYTES + 1))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        _logger.warning('Catálogo RSS remoto no disponible (%s)', type(exc).__name__)
    finally:
        _refresh_lock.release()
