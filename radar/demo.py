"""Explicitly fictional examples. Only enabled for local development and tests."""
import json
import os
from datetime import datetime, timedelta, timezone
from . import store

DATA = [
('La exploración espacial abre nuevas preguntas sobre las próximas misiones', 'Ciencia', 'El desarrollo de tecnologías espaciales plantea nuevas oportunidades para la investigación. Este texto es una demostración ficticia de diseño.', 'spacial'),
('Universidades exploran nuevas aplicaciones de inteligencia artificial', 'Tecnología', 'Equipos de investigación trabajan en herramientas para apoyar tareas académicas. Noticia de muestra, no corresponde a un hecho documentado.', 'technology'),
('Ciudades estudian opciones para fortalecer la movilidad sostenible', 'Clima', 'Diferentes enfoques buscan mejorar el transporte urbano y reducir emisiones. Este artículo es únicamente una demostración.', 'climate'),
('Pequeñas empresas evalúan herramientas digitales para crecer', 'Economía', 'La transformación digital aparece como un tema de interés para pequeños negocios. Contenido de prueba.', 'economy'),
('Investigadores presentan ideas para mejorar el acceso a la educación', 'Educación', 'La innovación educativa involucra tecnologías y nuevas metodologías. Información ficticia utilizada para probar esta interfaz.', 'education'),
('Nuevos proyectos culturales impulsan espacios de lectura comunitaria', 'Cultura', 'Una iniciativa cultural hipotética permite visualizar tarjetas de la plataforma. No es una noticia real.', 'culture'),
('Experiencias locales muestran interés por la protección de ecosistemas', 'Clima', 'Este es un ejemplo ficticio para ilustrar la exploración de noticias ambientales.', 'nature'),
('Laboratorios prueban herramientas para organizar información científica', 'Ciencia', 'Demostración ficticia de una noticia sobre procesamiento de datos y ciencia.', 'science'),
('El comercio electrónico sigue inspirando soluciones para emprendedores', 'Economía', 'Texto de muestra para evaluar el aspecto de un boletín digital.', 'business'),
('Comunidades diseñan propuestas para acercar la tecnología a jóvenes', 'Tecnología', 'Artículo ilustrativo de la interfaz; no debe entenderse como información verificada.', 'digital')]


def is_enabled():
    value = os.getenv('RADAR_ENABLE_DEMO_DATA', '0').strip().lower()
    return value in {'1', 'true', 'yes', 'on'}


def seed():
    if not is_enabled():
        return
    if store.row('SELECT id FROM news LIMIT 1'):
        return
    t = datetime.now(timezone.utc)
    for i, (headline, topic, summary, art) in enumerate(DATA):
        pd = (t - timedelta(hours=i * 3 + 1)).isoformat(timespec='seconds')
        src = [{'name': 'Medio ficticio de demostración', 'url': 'https://example.com/radar-demostracion', 'published_at': pd, 'original_title': headline, 'domain': 'example.com'}]
        store.exec_('''INSERT INTO news(slug,headline,original_headline,summary,topic,editorial_tone,published_at,updated_at,sources_json,evidence_json,timeline_json,status,review_needed,approved,score,mode,is_demo,image_url,fingerprint)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        ('demo-' + str(i + 1), headline, headline, summary, topic, 'informativo', pd, pd, json.dumps(src, ensure_ascii=False),
         '[]', json.dumps([{'at': pd, 'label': 'Ejemplo ficticio creado'}], ensure_ascii=False), 'demostracion', 0, 1,
         max(0, 90 - i * 6), 'demostracion', 1, art, 'demo-' + str(i)))
