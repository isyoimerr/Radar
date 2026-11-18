"""Fetch RSS/Atom feeds. The publisher, not RADAR, owns referenced articles."""
import datetime as dt
import email.utils
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser
from .store import now

USER_AGENT='RADAR-NewsMonitor/1.0 (+educational; respectful RSS polling)'
MAX_FEED_BYTES=2_000_000
TAG_RE = re.compile(r'<[^>]+>')
# Google News serves this same cover for unrelated articles.
GOOGLE_NEWS_COVER = 'J6_coFbogxhRI9iM864NL_liGXvsQp2AupsKei7z0cNNfDvGUmWUy20nuUhkREQyrpY4bEeIBuc'

def plain(text):
    text=re.sub(r'<(script|style)[^>]*>.*?</\1>',' ',text or '',flags=re.I|re.S)
    text=TAG_RE.sub(' ',text)
    return re.sub(r'\s+',' ',unescape(text)).strip()[:1300]

def canonical(url):
    try:
        p=urllib.parse.urlparse(url.strip())
        if p.scheme not in ('http','https') or not p.netloc: return ''
        blocked={'utm_source','utm_medium','utm_campaign','utm_term','utm_content','fbclid','gclid'}
        q=urllib.parse.urlencode([(k,v) for k,v in urllib.parse.parse_qsl(p.query) if k.lower() not in blocked])
        return urllib.parse.urlunparse((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/') or '/',p.params,q,''))
    except Exception:return ''


def normalize_feed_url(url):
    if not url: return url
    p=urllib.parse.urlsplit(url.strip())
    path=urllib.parse.quote(p.path, safe='/%')
    query=urllib.parse.quote(p.query, safe='=&%+?/:;')
    fragment=urllib.parse.quote(p.fragment, safe='')
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, query, fragment))


def validate_public_url(url, resolve=False):
    p=urllib.parse.urlparse(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or (p.port and p.port !=443):
        raise ValueError('Se requiere URL HTTPS pública y sin credenciales')
    host=p.hostname.lower()
    if host in {'localhost','localhost.localdomain'} or host.endswith(('.local','.internal')):
        raise ValueError('No se permiten redes privadas')
    try:
        literal = ipaddress.ip_address(host)
        if not literal.is_global: raise ValueError('No se permiten IP privadas o restringidas')
    except ValueError as exc:
        if 'No se permiten IP' in str(exc): raise
    if resolve:
        for item in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM):
            ip=ipaddress.ip_address(item[4][0])
            if not ip.is_global: raise ValueError('Dirección privada o restringida')
    return url

def when(value):
    if not value:return now()
    try:
        d=email.utils.parsedate_to_datetime(value)
        return d.astimezone(dt.timezone.utc).isoformat(timespec='seconds')
    except Exception: pass
    try:
        d=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        return d.replace(tzinfo=dt.timezone.utc).isoformat(timespec='seconds') if not d.tzinfo else d.astimezone(dt.timezone.utc).isoformat(timespec='seconds')
    except Exception:return now()

def node_text(n, suffixes):
    for el in n.iter():
        tag=el.tag.rsplit('}',1)[-1].lower()
        if tag in suffixes and (el.text or '').strip():return el.text.strip()
    return ''

def media_kind(url, hint=''):
    path = urllib.parse.urlsplit(url).path.lower()
    hint = hint.lower()
    if 'video' in hint or path.endswith(('.mp4','.webm','.mov','.m4v','.avi','.m3u8','.mkv')):
        return 'video'
    if 'audio' in hint or path.endswith(('.mp3','.wav','.ogg')):
        return 'audio'
    return 'image'


def preview_image_url(value, base_url=''):
    value = (value or '').strip()
    if not value or value.startswith(('#', '?')):
        return ''
    try:
        url = urllib.parse.urljoin(base_url, value)
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return ''
    if parsed.scheme not in {'https', 'http'} or not parsed.hostname:
        return ''
    if parsed.path in {'', '/'} and not parsed.query:
        return ''
    if parsed.hostname == 'lh3.googleusercontent.com' and parsed.path.lstrip('/').split('=', 1)[0] == GOOGLE_NEWS_COVER:
        return ''
    filename = urllib.parse.unquote(parsed.path.rsplit('/', 1)[-1]).lower()
    if filename.endswith(('.svg', '.ico', '.gif')) and (
        parsed.hostname == 'static-redesign.cnbcfm.com'
        or re.search(r'logo|lockup|favicon|placeholder|sprite|pixel', filename)
    ):
        return ''
    return url


class ArticleImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.social = []
        self.inline = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        property_name = (attrs.get('property') or attrs.get('name') or '').lower()
        if tag == 'meta' and property_name in {'og:image', 'og:image:url', 'og:image:secure_url', 'twitter:image', 'twitter:image:src'}:
            self.social.append(attrs.get('content'))
        elif tag == 'img':
            self.inline.extend(attrs.get(key) for key in ('data-src', 'data-original', 'src'))
        elif tag == 'source' and attrs.get('srcset'):
            candidates = attrs['srcset'].split(',', 1)[0].split()
            if candidates:
                self.inline.append(candidates[0])


def extract_image_from_html(fragment, base_url=''):
    if not fragment:
        return ''
    parser = ArticleImages()
    parser.feed(unescape(str(fragment)))
    for value in parser.social + parser.inline:
        if image := preview_image_url(value, base_url):
            return image
    return ''


def fetch_article_image(url, timeout=8):
    if not url:
        return ''
    try:
        p = urllib.parse.urlparse(url)
        if p.scheme not in ('http', 'https') or not p.netloc:
            return ''
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'})
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            final_url = resp.geturl()
            if urllib.parse.urlsplit(final_url).hostname == 'news.google.com':
                return ''
            html = resp.read(800_000).decode('utf-8', 'ignore')
        return extract_image_from_html(html, final_url)
    except Exception:
        return ''


def parse_feed(body, source_name):
    root=ET.fromstring(body)
    entries=[]
    for e in root.iter():
        if e.tag.rsplit('}',1)[-1] not in ('item','entry'): continue
        title=plain(node_text(e, {'title'}))
        url=node_text(e, {'link'})
        if not url:
            for child in e:
                if child.tag.rsplit('}',1)[-1]=='link' and child.attrib.get('href'):
                    if child.attrib.get('rel','alternate')=='alternate': url=child.attrib['href']; break
        url=canonical(url)
        if not title or not url:continue
        description=plain(node_text(e, {'description','summary','content'}))
        date=when(node_text(e, {'pubdate','published','updated','date'}))
        source=source_name
        image_url = ''
        video_url = ''
        for child in e.iter():
            tag = child.tag.rsplit('}', 1)[-1].lower()
            if tag == 'source' and (child.text or '').strip():
                source = plain(child.text)
            if tag not in {'enclosure', 'thumbnail', 'content'} or not child.get('url'):
                continue
            media_url = preview_image_url(child.get('url'), url)
            if not media_url:
                continue
            kind = media_kind(media_url, child.get('type', ''))
            if kind == 'video' and not video_url:
                video_url = canonical(media_url)
            elif kind == 'image' and not image_url:
                image_url = media_url
        if not image_url:
            item_xml = ET.tostring(e, encoding='unicode', method='xml')
            image_url = extract_image_from_html(item_xml, url)
        media_type = 'video' if video_url else 'image'
        entries.append({'title':title[:250],'url':url,'description':description,'published_at':date,
            'source_name':source[:100],'via_feed':source_name,'image_url':image_url,'video_url':video_url,'media_type':media_type})
    return entries

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirección bloqueada por seguridad; use la URL RSS final')

def fetch_feed(source, timeout=9):
    clean_url = normalize_feed_url(source['feed_url'])
    validate_public_url(clean_url, resolve=True)
    request=urllib.request.Request(clean_url,headers={'User-Agent':USER_AGENT,'Accept':'application/rss+xml,application/atom+xml,application/xml,text/xml'})
    opener=urllib.request.build_opener(NoRedirect())
    with opener.open(request,timeout=timeout) as resp:
        data=resp.read(MAX_FEED_BYTES+1)
        if len(data)>MAX_FEED_BYTES:raise ValueError('RSS demasiado grande')
        return parse_feed(data,source['name'])
