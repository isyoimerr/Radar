"""Deterministic Instagram carousel exports using local composition and PIL."""
import io
import json
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .pipeline import top_five

WIDTH = 1080
HEIGHT = 1350

PALETTES = {
    'Editorial': {'bg': '#0B1220', 'card': '#142238', 'accent': '#64E3CC', 'ink': '#F9F6F0', 'muted': '#C7D1D8', 'alt': '#FF8F70', 'secondary': '#C5C9FF', 'paper': '#F7F5F0', 'navy': '#13304A', 'coral': '#FF8268', 'lavender': '#C9B7FF', 'mint': '#8DECD0'},
    'Moderno': {'bg': '#101B2C', 'card': '#1A2D3E', 'accent': '#64E3CC', 'ink': '#F5F8FF', 'muted': '#BFD1E6', 'alt': '#F6B3C3', 'secondary': '#A5D9FF', 'paper': '#F4F6FB', 'navy': '#0D2034', 'coral': '#FF8F70', 'lavender': '#D7C5FF', 'mint': '#87E7D1'},
    'Minimalista': {'bg': '#F5F1E8', 'card': '#E8E2D5', 'accent': '#0B1220', 'ink': '#0B1220', 'muted': '#49586A', 'alt': '#8CC8B7', 'secondary': '#D7C7FF', 'paper': '#F7F5F0', 'navy': '#162A46', 'coral': '#F06D59', 'lavender': '#D9C7F7', 'mint': '#89D7C7'},
}


def _font_candidates(serif=False, bold=False):
    family = 'DejaVuSerif' if serif else 'DejaVuSans'
    suffix = 'Bold' if bold else ''
    patterns = [
        f'/usr/share/fonts/truetype/dejavu/{family}{suffix}.ttf',
        f'/usr/share/fonts/truetype/dejavu/{family}{suffix}.ttc',
        f'C:/Windows/Fonts/{family}{suffix}.ttf',
        f'C:/Windows/Fonts/{family}{suffix}.ttc',
        f'C:/Program Files/Google/Roboto/{family}{suffix}.ttf',
    ]
    return [p for p in patterns if p]


def _font(size, bold=False, serif=False):
    for path in _font_candidates(serif=serif, bold=bold):
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size)
    except Exception:
        return ImageFont.load_default()


def _compact_title(value, limit=52):
    text = (value or 'Sin titular disponible').strip()
    if len(text) <= limit:
        return text
    if ' ' not in text:
        return text[:limit - 1] + '…'
    words = text.split()
    compact = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                compact.append(current)
                current = word
            else:
                compact.append(word)
    if current:
        compact.append(current)
    joined = ' '.join(compact)
    return joined[:limit - 1] + '…' if len(joined) > limit else joined


def _compact_summary(value, limit=120):
    text = (value or '').strip()
    if not text:
        return 'Contexto disponible en la fuente original.'
    if len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(' ', 1)[0] + '…'


def _source_label(story):
    sources = story.get('sources') or []
    names = [s.get('name') or 'Fuente original' for s in sources if isinstance(s, dict)]
    if names:
        return names[0]
    return 'RADAR · Fuentes registradas'


def _story_datetime(story, language=None):
    value = story.get('published_at') or story.get('updated_at') or story.get('at') or ''
    if not value:
        return ''
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.strftime('%d/%m/%Y' if language == 'es' else '%d %b %Y')
    except ValueError:
        return value[:10]


def _normalize_story(item):
    if not isinstance(item, dict):
        return {}
    story = dict(item)
    story['headline'] = (story.get('headline') or story.get('original_headline') or 'Sin titular disponible').strip()
    story['summary'] = (story.get('summary') or '').strip() or story['headline']
    story['topic'] = story.get('topic') or 'Actualidad'
    story['image_url'] = story.get('image_url') or ''
    story['published_at'] = story.get('published_at') or story.get('updated_at') or ''
    story['sources'] = story.get('sources') or []
    return story


def _safe_url(url):
    if not url:
        return ''
    return str(url).strip()


def _decode_color(hex_color):
    hex_color = str(hex_color).lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(ch * 2 for ch in hex_color)
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _hex_to_rgba(hex_color, alpha=255):
    r, g, b = _decode_color(hex_color)
    return (r, g, b, alpha)


def _fetch_image(url):
    image_url = _safe_url(url)
    if not image_url:
        return None
    try:
        req = Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req, timeout=12) as response:
            payload = response.read()
        if not payload:
            return None
        with Image.open(io.BytesIO(payload)) as img:
            return img.convert('RGB')
    except Exception:
        return None


def _wrap_lines(draw, font, text, max_width, max_lines=3):
    if not text:
        return ['']
    words = text.split()
    if not words:
        return ['']
    lines = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1]
        last = lines[-1]
        if len(last) > 8:
            lines[-1] = last[:len(last) - 6] + '…'
    return lines[:max_lines]


def _story_palette(style):
    return PALETTES.get(style, PALETTES['Editorial'])


def _make_slide(stories, index, total, layout, style, language=None):
    stories = [_normalize_story(s) for s in stories if isinstance(s, dict)]
    if not stories:
        stories = [{
            'headline': 'RADAR actualiza la edición local',
            'summary': 'Sin titulares disponibles, se conserva la referencia editorial del sistema.',
            'topic': 'Actualidad',
            'sources': [{'name': 'RADAR'}],
            'published_at': '',
            'image_url': ''
        }]
    first = stories[0]
    palette = _story_palette(style)
    headline = _compact_title(first['headline'], 44 if layout == 'cover' else 52)
    if layout == 'close':
        headline = _compact_title(first['headline'], 36)
    topic = first.get('topic', 'Actualidad')
    english_topics = {'Actualidad': 'Current affairs', 'Tecnología': 'Technology', 'Ciencia': 'Science', 'Economía': 'Business',
                      'Clima': 'Climate', 'Salud': 'Health', 'Educación': 'Education', 'Política': 'Politics',
                      'Cultura': 'Culture', 'Deportes': 'Sports', 'Urbanismo': 'Urban planning'}
    return {
        'index': index,
        'layout': layout,
        'headline': headline,
        'summary': _compact_summary(first['summary'], 110 if layout == 'cover' else 135),
        'category': english_topics.get(topic, 'Current affairs') if language == 'en' else topic,
        'source': (_source_label(first) if first.get('sources') else 'Original source') if language == 'en' else _source_label(first),
        'date': _story_datetime(first, language),
        'language': language or 'es',
        'image_url': next((s.get('image_url') for s in stories if s.get('image_url')), ''),
        'stories': stories,
        'total': total,
        'style': style,
        'palette': palette,
        'brand': 'RADAR'
    }


def build_carousel_deck(stories, slide_count=5, style='Editorial', language=None):
    items = [_normalize_story(s) for s in (stories or [])]
    if not items:
        fallback = [{
            'headline': 'RADAR actualiza la edición local',
            'summary': 'Sin titulares disponibles, se conserva una referencia editorial del sistema.',
            'topic': 'Actualidad',
            'sources': [{'name': 'RADAR'}],
            'published_at': '',
            'image_url': ''
        }]
        return {'slides': [_make_slide(fallback, 1, 1, 'cover', style, language)], 'style': style, 'count': 1}
    selected = items[:10]
    slide_count = max(3, min(10, int(slide_count or 5)))

    if slide_count == 5:
        layouts = ['cover', 'feature', 'editorial', 'minimal', 'close']
        return {'slides': [_make_slide([selected[i]], i + 1, slide_count, layouts[i % len(layouts)], style, language) for i in range(min(len(selected), slide_count))], 'style': style, 'count': min(len(selected), slide_count)}

    if slide_count == 3:
        layouts = ['cover', 'editorial', 'close']
        return {'slides': [_make_slide([selected[i]], i + 1, slide_count, layouts[i % len(layouts)], style, language) for i in range(min(len(selected), slide_count))], 'style': style, 'count': min(len(selected), slide_count)}

    layouts = ['cover', 'feature', 'editorial', 'minimal', 'close', 'feature', 'editorial', 'minimal', 'close', 'feature']
    deck = [_make_slide([selected[i]], i + 1, slide_count, layouts[i % len(layouts)], style, language) for i in range(min(len(selected), slide_count))]
    return {'slides': deck, 'style': style, 'count': len(deck)}


def _add_photo(img, photo, x, y, w, h, radius=26):
    if photo is None:
        return
    crop = photo.resize((w, h), Image.Resampling.LANCZOS)
    mask = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    masked = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    masked_paste = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    masked_paste.paste(crop.convert('RGBA'), (0, 0))
    masked = Image.composite(masked_paste, Image.new('RGBA', (w, h), (0, 0, 0, 0)), mask)
    img.paste(masked, (x, y), mask=masked.getchannel('A'))


def _paint_fallback_panel(draw, x, y, w, h, color_a, color_b, label):
    panel = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(panel)
    pdraw.rounded_rectangle((0, 0, w, h), radius=28, fill=_hex_to_rgba(color_a, 180))
    pdraw.rounded_rectangle((26, 46, w - 26, h - 46), radius=24, fill=_hex_to_rgba(color_b, 100))
    pdraw.text((40, 62), label, fill=(255, 255, 255, 200), font=_font(22, bold=True))
    return panel


def _draw_slide(slide, output_path):
    palette = slide.get('palette', PALETTES['Editorial'])
    bg = palette['bg']
    img = Image.new('RGB', (WIDTH, HEIGHT), bg)
    draw = ImageDraw.Draw(img)
    layout = slide.get('layout', 'cover')
    paper = palette['paper']
    navy = palette['navy']
    light_ink, light_muted, light_accent = '#F8FAFC', '#D5E0E4', '#A0FFE7'
    paper_muted, paper_accent = '#405452', '#176659'

    if layout == 'cover':
        photo = _fetch_image(slide.get('image_url'))
        if photo is not None:
            photo = photo.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            img = Image.blend(img, photo, 0.58)
        overlay = Image.new('RGBA', (WIDTH, HEIGHT), (11, 17, 26, 150))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((60, 60, WIDTH - 60, HEIGHT - 60), radius=28, outline=(_decode_color(light_accent) + (80,)), width=2)
        draw.text((76, 80), 'RADAR', fill=light_accent, font=_font(54, serif=True))
        headline_font = _font(96, bold=True, serif=True)
        for idx, line_text in enumerate(_wrap_lines(draw, headline_font, slide.get('headline', 'RADAR'), 900, max_lines=4)):
            draw.text((76, 430 + idx * 105), line_text, fill=light_ink, font=headline_font)
        draw.text((76, 1170), slide.get('source', 'RADAR'), fill=light_muted, font=_font(22, bold=True))
        draw.text((760, 1170), slide.get('date', ''), fill=light_muted, font=_font(22))
        return _save_png(img, output_path)

    if layout == 'feature':
        bg = paper
        img = Image.new('RGB', (WIDTH, HEIGHT), bg)
        draw = ImageDraw.Draw(img)
        panel = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(panel)
        pdraw.rounded_rectangle((60, 64, WIDTH - 60, HEIGHT - 48), radius=30, fill=_hex_to_rgba('#F3F1EA', 255))
        img = Image.alpha_composite(img.convert('RGBA'), panel).convert('RGB')
        draw = ImageDraw.Draw(img)
        top = Image.new('RGB', (WIDTH, 100), '#F8F6F2')
        img.paste(top, (0, 0))
        draw.text((78, 80), 'RADAR', fill=navy, font=_font(26, bold=True))
        draw.text((890, 82), f'{slide["index"]:02d}/{slide["total"]:02d}', fill=navy, font=_font(18, bold=True))
        photo = _fetch_image(slide.get('image_url'))
        if photo is not None:
            _add_photo(img, photo, 70, 180, 480, 980, radius=26)
        draw.rounded_rectangle((620, 180, 1010, 950), radius=26, fill=(255, 255, 255, 60))
        draw.text((660, 240), slide.get('category', 'Actualidad').upper(), fill=paper_accent, font=_font(24, bold=True))
        title = _wrap_lines(draw, _font(70, bold=True, serif=True), slide.get('headline', 'RADAR'), 300, max_lines=5)
        y = 320
        for line in title:
            draw.text((660, y), line, fill=navy, font=_font(70, bold=True, serif=True))
            y += 70
        draw.text((660, 950), slide.get('source', 'RADAR'), fill=navy, font=_font(20, bold=True))
        draw.text((900, 950), slide.get('date', ''), fill=navy, font=_font(20))
        return _save_png(img, output_path)

    if layout == 'editorial':
        img = Image.new('RGB', (WIDTH, HEIGHT), paper)
        draw = ImageDraw.Draw(img)
        draw.text((78, 78), 'RADAR', fill=navy, font=_font(24, bold=True))
        draw.text((890, 78), f'{slide["index"]:02d}/{slide["total"]:02d}', fill=navy, font=_font(18, bold=True))
        draw.text((78, 150), slide.get('category', 'Actualidad').upper(), fill=paper_accent, font=_font(24, bold=True))
        photo = _fetch_image(slide.get('image_url'))
        if photo is not None:
            _add_photo(img, photo, 78, 220, 920, 430, radius=28)
        draw.rounded_rectangle((78, 700, 1002, 1036), radius=32, fill=navy)
        title = _wrap_lines(draw, _font(72, bold=True, serif=True), slide.get('headline', 'RADAR'), 860, max_lines=3)
        y = 768
        for line in title:
            draw.text((118, y), line, fill=light_ink, font=_font(72, bold=True, serif=True))
            y += 78
        summary = _wrap_lines(draw, _font(32), slide.get('summary', ''), 820, max_lines=2)
        for index, line in enumerate(summary):
            draw.text((118, 1048 + index * 36), line, fill=navy, font=_font(30))
        draw.text((78, 1186), slide.get('source', 'RADAR'), fill=paper_muted, font=_font(20, bold=True))
        draw.text((820, 1186), slide.get('date', ''), fill=paper_muted, font=_font(20))
        return _save_png(img, output_path)

    if layout == 'minimal':
        img = Image.new('RGB', (WIDTH, HEIGHT), navy)
        draw = ImageDraw.Draw(img)
        draw.text((78, 88), 'RADAR', fill=light_accent, font=_font(28, bold=True))
        draw.text((908, 92), f'{slide["index"]:02d}/{slide["total"]:02d}', fill=light_ink, font=_font(18, bold=True))
        draw.rounded_rectangle((80, 200, 1000, 860), radius=26, fill=(255, 255, 255, 18))
        photo = _fetch_image(slide.get('image_url'))
        if photo is not None:
            _add_photo(img, photo, 120, 236, 840, 560, radius=26)
        title = _wrap_lines(draw, _font(88, bold=True, serif=True), slide.get('headline', 'RADAR'), 820, max_lines=4)
        y = 892
        for line in title:
            draw.text((90, y), line, fill=light_ink, font=_font(88, bold=True, serif=True))
            y += 88
        draw.text((90, 1220), slide.get('source', 'RADAR'), fill=light_ink, font=_font(22, bold=True))
        draw.text((760, 1220), slide.get('date', ''), fill=light_ink, font=_font(22))
        return _save_png(img, output_path)

    img = Image.new('RGB', (WIDTH, HEIGHT), navy)
    draw = ImageDraw.Draw(img)
    draw.text((78, 86), 'RADAR', fill=light_accent, font=_font(26, bold=True))
    draw.text((890, 86), f'{slide["index"]:02d}/{slide["total"]:02d}', fill=light_ink, font=_font(18, bold=True))
    draw.text((78, 150), slide.get('category', 'Actualidad').upper(), fill=light_accent, font=_font(22, bold=True))
    photo = _fetch_image(slide.get('image_url'))
    if photo is not None:
        _add_photo(img, photo, 86, 210, 908, 600, radius=28)
    line = Image.new('RGBA', (920, 240), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(line)
    ldraw.rounded_rectangle((0, 0, 920, 220), radius=28, fill=_hex_to_rgba('#F7F5F0', 230))
    img.paste(line, (80, 860), mask=line.getchannel('A'))
    title = _wrap_lines(draw, _font(64, bold=True, serif=True), slide.get('headline', 'RADAR'), 800, max_lines=3)
    y = 900
    for line_text in title:
        draw.text((118, y), line_text, fill=navy, font=_font(64, bold=True, serif=True))
        y += 66
    draw.text((120, 1180), slide.get('source', 'RADAR'), fill=light_muted, font=_font(20, bold=True))
    draw.text((820, 1180), slide.get('date', ''), fill=light_muted, font=_font(20))
    sources_caption = 'Explore the sources on RADAR' if slide.get('language') == 'en' else 'Consulta las fuentes en RADAR'
    draw.text((120, 1230), sources_caption, fill=light_accent, font=_font(18, bold=True))
    return _save_png(img, output_path)


def _save_png(img, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format='PNG')
    return output_path


def export_carousel_zip(deck, style='Editorial'):
    if isinstance(deck, dict) and 'slides' in deck:
        slides = deck['slides']
    else:
        slides = list(deck or [])
    if not slides:
        raise ValueError('No hay slides disponibles para exportar.')
    tmp_dir = Path(mkdtemp(prefix='radar-carousel-'))
    files = []
    for idx, slide in enumerate(slides, 1):
        slide_data = dict(slide)
        slide_data['index'] = idx
        slide_data['total'] = len(slides)
        slide_data['style'] = style
        slide_data['palette'] = PALETTES.get(style, PALETTES['Editorial'])
        safe_name = re.sub(r'[^a-z0-9]+', '-', (slide_data.get('headline') or 'slide').lower()).strip('-') or 'slide'
        output_path = tmp_dir / f'{idx:02d}-{safe_name[:28]}.png'
        _draw_slide(slide_data, output_path)
        files.append(output_path)
    zip_path = tmp_dir / 'radar-carousel.zip'
    with zipfile.ZipFile(zip_path, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    return zip_path.read_bytes()


def bulletin_html():
    stories = top_five()
    html_rows = []
    for i, news in enumerate(stories[:5], 1):
        article = _normalize_story(news)
        links = ''.join(f'<li><a href="{s.get("url", "#")}" rel="noopener noreferrer">{s.get("name", "Fuente")}</a></li>' for s in article.get('sources', []))
        html_rows.append(f'<article><small>{i:02d} · {article["topic"]}</small><h2>{article["headline"]}</h2><p>{_compact_summary(article["summary"], 160)}</p><ul>{links or "<li>Fuente no registrada</li>"}</ul></article>')
    return '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>RADAR | Boletín</title><style>body{font-family:Arial,sans-serif;background:#f5f5f0;color:#0d1727;padding:32px}main{max-width:960px;margin:0 auto}article{border-top:1px solid #d6d9d3;padding:24px 0}small{letter-spacing:.12em;opacity:.7}</style></head><body><main><h1>RADAR | Boletín</h1>' + ''.join(html_rows) + '</main></body></html>'


def bulletin_png():
    deck = build_carousel_deck(top_five()[:5], slide_count=5, style='Editorial')
    zip_bytes = export_carousel_zip(deck, style='Editorial')
    tmp_dir = Path(mkdtemp(prefix='radar-boletin-'))
    zip_path = tmp_dir / 'radar-boletin.zip'
    zip_path.write_bytes(zip_bytes)
    with zipfile.ZipFile(zip_path, 'r') as archive:
        ordered = sorted(archive.namelist(), key=lambda x: x)
        if not ordered:
            raise FileNotFoundError('No se han generado PNGs para el boletín.')
        first = archive.extract(ordered[0], str(tmp_dir / 'pngs'))
    return Path(first).read_bytes()
