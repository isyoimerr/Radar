"""Language of the published text, independent of RADAR's own labels."""
from functools import lru_cache

from langdetect import DetectorFactory, detect
from langdetect.lang_detect_exception import LangDetectException


DetectorFactory.seed = 0
LANGUAGES = ('es', 'en')
EXCERPT_PREFIX = 'Extracto proporcionado por la fuente: '
MISSING_EXCERPT = 'El medio publicó este titular. Consulta la fuente original para conocer los detalles y el contexto completo.'


def source_excerpt(summary):
    value = (summary or '').removeprefix(EXCERPT_PREFIX).strip()
    return '' if value == MISSING_EXCERPT else value


@lru_cache(maxsize=4096)
def story_language(headline, summary=''):
    try:
        return detect(f'{headline or ""}\n{source_excerpt(summary)}')
    except LangDetectException:
        return 'und'
