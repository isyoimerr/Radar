"""Conservative editorial rules; never equate source count with factual truth."""
import difflib
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlparse

SENSITIVE=['acusad','denunci','violaci','abuso','menor de edad','suicid','asesinat','homicid','secuestr','funa','escandalo','escándalo','agresion','agresión','fraude','terroris','tragedia','víctima','victima','presunto','presunta']
CATEGORIES={
 'Tecnología':['inteligencia artificial','software','tecnolog','robot','ciber','algorit','digital','startup','aplicacion','aplicación'],
 'Ciencia':['cienci','nasa','universo','espacial','laboratorio','investigac','cohete','misión','mision','estudio cientifico'],
 'Economía':['econom','mercado','banco','inflaci','dolar','dólar','empleo','empresa','comercio','inversi','peso colombian'],
 'Clima':['clima','ambiente','ambiental','lluvia','energía','energia','emision','océano','oceano','sostenib','huracan','huracán'],
 'Salud':['salud','médic','medic','vacuna','hospital','enfermed','tratamiento'],
 'Educación':['educac','docente','estudiant','escuela','colegio','universidad'],
 'Política':['gobierno','congreso','presidente','ministerio','eleccion','elección','senado','alcalde'],
 'Cultura':['cultura','libro','cine','música','musica','festival','arte'],
 'Deportes':['futbol','fútbol','deporte','atleta','torneo','liga','mundial'],
}
TONE={'Tecnología':'técnico y comprensible','Ciencia':'preciso, didáctico y prudente',
      'Economía':'analítico y claro, sin recomendaciones financieras','Clima':'explicativo y sustentado',
      'Salud':'riguroso, no diagnóstico y sin alarmismo','Educación':'claro y pedagógico',
      'Política':'neutral y atribuido','Cultura':'cercano y descriptivo',
      'Deportes':'informativo y dinámico, sin exagerar','Actualidad':'informativo y neutral'}

def normalize(s):
    s=unicodedata.normalize('NFKD',s.lower())
    s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9 ]',' ',s).strip()

def topic(text):
    s=normalize(text)
    best=('Actualidad',0)
    for k,terms in CATEGORIES.items():
        score=sum(1 for term in terms if normalize(term) in s)
        if score>best[1]:best=(k,score)
    return best[0]

def sensitive(text):
    s=normalize(text)
    return any(normalize(k) in s for k in SENSITIVE)

def similarity(a,b):
    a,b=normalize(a),normalize(b)
    if not a or not b:return 0
    a,b=re.sub(r'\s+',' ',a),re.sub(r'\s+',' ',b)
    return max(difflib.SequenceMatcher(None,a,b).ratio(),
        (len(set(a.split()) & set(b.split()))/max(1,len(set(a.split()) | set(b.split())))))

def source_fingerprint(item):
    source=(item.get('source_name') or '').strip().lower()
    url=(item.get('url') or '').strip()
    host=urlparse(url).hostname.lower().replace('www.','') if url else ''
    source_key=normalize(source) or 'source-desconocida'
    if host:
        return (source_key, host)
    return (source_key, 'source-desconocida')


def independent_source_count(group):
    return len({source_fingerprint(item) for item in group if source_fingerprint(item)})


def cluster_articles(items,threshold=0.78):
    """Group near-identical coverage; never claim perfect semantic event linking."""
    groups=[]; seen=set()
    for item in sorted(items,key=lambda x:x['published_at'],reverse=True):
        if item['url'] in seen:continue
        seen.add(item['url'])
        placed=False
        for group in groups:
            if max(similarity(item['title'],g['title']) for g in group)>=threshold:
                group.append(item);placed=True;break
        if not placed:groups.append([item])
    return groups

def rank(group):
    latest=max(x['published_at'] for x in group)
    try: age=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(latest)).total_seconds()/3600)
    except Exception:age=99
    independent=independent_source_count(group)
    newsworthiness=min(35,12+3*min(len(group),7))
    recency=max(0,25-age*.7)
    coverage=min(20, independent*5)
    return round(newsworthiness+recency+coverage+10+min(10,2*len(group)),1)

def grouping_status(group):
    count=independent_source_count(group)
    return 'cobertura_multiple' if count >= 2 else 'fuente_unica'
