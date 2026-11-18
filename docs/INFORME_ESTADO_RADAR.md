# Informe técnico del estado de RADAR

## 1. Descripción del proyecto

### Qué es RADAR
RADAR es una aplicación web local en español para vigilar noticias públicas, agrupar coberturas similares, conservar la atribución a las fuentes, preparar un boletín editorial y exportar una edición visual. La base del proyecto está construida en Python con FastAPI, SQLite y una interfaz web estática en HTML/CSS/JavaScript.

### Problema que resuelve
El proyecto busca dar respuesta a la necesidad de:
- consultar fuentes RSS de manera automatizada;
- detectar titulares repetidos o cercanos entre distintos medios;
- clasificar noticias por tema y sensibilidad;
- conservar enlaces, fechas y nombres de medios;
- preparar un boletín útil para lectura y revisión editorial;
- permitir una forma reproducible de trabajo académico y experimental sin depender de un servicio externo obligatorio.

### Objetivos declarados
El README del proyecto indica que la intención es:
- recoger titulares desde RSS reales o en simulación;
- agrupar noticias por evento o cobertura;
- evitar la pérdida de atribución a la fuente;
- generar un boletín Top 5 o selección editorial;
- explorar el resto de noticias y fuentes;
- ofrecer un panel administrativo local;
- exportar boletines en HTML, PNG y JSON;
- mantener la IA como opción complementaria, no como requisito obligatorio.

### Funcionalidades principales
Entre las funciones documentadas y observadas en el código, destacan:
- lectura de feeds RSS/Atom;
- normalización de URLs y limpieza de contenido;
- agrupación de noticias por similitud;
- puntuación editorial por cobertura, recencia y claridad;
- revisión de contenido sensible;
- registro e inicio de sesión con cookies firmadas;
- guardado de noticias por usuario;
- administración de fuentes RSS;
- revisión de noticias pendientes;
- generación de carrusel/editorial para redes;
- exportación de boletín HTML/PNG/JSON;
- automatización programada por cron con token.

---

## 2. Estado real del desarrollo

### Estado objetivo según la evidencia
El proyecto está en una fase de “base ejecutable local” y no en “servicio periodístico validado”. Esto se expresa explícitamente en el README y en el código: la aplicación puede arrancar, consultar, agrupar y exportar, pero no se presenta como una publicación periodística verificable en producción.

### Funcionalidades implementadas
Se observan implementadas las siguientes capacidades:
- servidor FastAPI con rutas de frontend y API;
- base de datos SQLite con tablas reales de noticias, fuentes, usuarios, bookmarks, ediciones, auditoría, runs;
- semilla de fuentes por defecto;
- autenticación local con hash PBKDF2 y cookies firmadas;
- enrutado SPA para páginas del frontend;
- panel de administración con fuentes y revisión;
- recolección RSS y actualización automática si hace falta;
- generación de boletín y carrusel;
- endpoints de exportación.

### Funcionalidades probadas
El repositorio incluye tests automatizados. La evidencia del proyecto indica:
- 10 pruebas en `tests/test_app.py` y otras pruebas de pipeline/editorial;
- el artefacto `pytest_out.txt` muestra: 9 pruebas aprobadas y 1 fallida;
- la prueba fallida es `test_news_refreshes_when_cache_is_stale`.

### Funcionalidades no concluidas o pendientes
Se identifican estas limitaciones reales:
- no hay verificación jurídica final de fotogalerías, derechos de imagen y uso de noticias; el código avisa que la atribución no sustituye la legalidad;
- no hay despliegue público real de GitHub/Supabase/Vercel configurado como producción;
- la IA (Gemini) es opcional y no se valida con una cuenta real ni con flujo de negocio completo;
- no hay estrategia de privacidad, DPO, cookies o avisos legales listos para publicación pública;
- no hay caché o base de datos externa escalable para producción masiva;
- la UI parece funcional pero no hay evidencia formal de validación de usabilidad, accesibilidad o navegadores reales;
- la comprobación visual en navegador no está consolidada como prueba automática.

### Limitaciones comprobadas por el código
El propio proyecto deja claro que:
- la ingestión RSS depende de acceso a Internet y de la disponibilidad de feeds públicos;
- si falla una fuente, se conserva el estado previo y se registra el error;
- no se garantiza cero duplicados conceptuales ni veracidad de hechos;
- la aplicación está pensada para un entorno local y no como servicio con réplicas multiinstancia;
- el README indica que Vercel estático no sirve para esta implementación sin un rediseño de arquitectura.

---

## 3. Arquitectura y tecnologías

### Frontend
El frontend se observa en:
- `static/index.html`
- `static/app.js`
- `static/styles.css`

Características reales:
- SPA con navegación básica por rutas: `/`, `/radar`, `/boletines`, `/fuentes`, `/metodologia`, `/acceso` y otros;
- CSS y JS nativos, sin dependencias externas de npm;
- diseño responsive y etiquetas accesibles (skip link, navegación por teclado, aria-labels);
- animaciones y estados con JavaScript y CSS;
- enfoque “single page app” con Fetch a la API.

### Backend Python
El backend central está en `radar/app.py` y módulos de `radar/`:
- `app.py`: FastAPI app, middleware, autenticación, rutas públicas y admin, generación de boletín y carrusel;
- `config.py`: rutas, sesión, claves, origenes permitidos;
- `store.py`: esquema SQLite, tablas y semilla de fuentes;
- `feeds.py`: solicitud y parseo RSS/Atom, validación seguridad, URLs, extracción de imágenes;
- `pipeline.py`: flujo de ingestión, deduplicación, clasificación, imagen fallback, almacenamiento de noticias;
- `editorial.py`: clasificación por tema, detección de sensibilidad, agrupación y ranking;
- `gemini.py`: generación opcional de contenido con IA, con fallo seguro y fallback a titular atribuido;
- `security.py`: hash PBKDF2 y cookies firmadas;
- `export.py`: composición de carruseles y exportación ZIP/PNG/HTML.

### RSS y scraping
Se observa que la ingestión RSS no se apoya en un framework pesado; usa:
- `urllib.request`;
- `xml.etree.ElementTree`;
- `feedparser` no se usa en el código actual de la aplicación, pero la guía del profesor sí lo menciona;
- validación de URLs públicas;
- normalización de canonical URLs para eliminar query params innecesarios;
- extracción de imágenes desde HTML o metadatos.

### Almacenamiento
El almacenamiento oficial es SQLite:
- `data/radar.sqlite3` en la carpeta `data/`;
- tablas: `sources`, `news`, `users`, `bookmarks`, `editions`, `pipeline_runs`, `audit_log`;
- `store.init()` crea índices y semillas fuentes por defecto;
- `PRAGMA journal_mode=WAL` está habilitada;
- el `README` recalca que SQLite es una solución local y no un despliegue multiinstancia.

### Verificación editorial y boletines
La lógica no trata una noticia como verdadera solo por ser popular. El sistema:
- agrupa múltiples fuentes;
- evalúa cantidad de fuentes independientes;
- marca `review_needed` y `sensitivity_reason`;
- acepta noticias no sensibles con menos revisión;
- mantiene `draft_headline`, `draft_summary`, `draft_evidence` como borrador en caso de IA;
- requiere aprobación humana antes de publicar con IA, o bien mantiene el titular atribuido si no hay suficiente base.

### Automatización y cronograma
Existe un workflow programado en `.github/workflows/poll-rss.yml`:
- ejecuta cada 15 minutos;
- usa `RADAR_DEPLOY_URL` y `RADAR_CRON_TOKEN`;
- hace POST a `POST /api/internal/collect`;
- requiere token para evitar accesos no autorizados.

### GeminI como opción
`radar/gemini.py` define `generate(...)`. La aplicación:
- comprueba la clave `GEMINI_API_KEY`;
- si no hay clave, no hace IA;
- si falla la API, cae a modo seguro con titular y resumen atribuidos;
- no inventa hechos ni atribuciones.

---

## 4. Funcionamiento del sistema

### Proceso completo observado
1. Inicio de la app
   - `store.init()` crea tablas y fuentes por defecto.
   - `bootstrap_news_if_empty()` elimina placeholders y, si no hay noticias aprobadas, programa una recolección inicial.
   - si no existe administrador, se crea usuario admin y se escribe `data/admin_credentials.txt` con el email y la contraseña temporales.

2. Consulta de fuentes RSS
   - `collect()` lee todas las fuentes activas de `sources`.
   - `fetch_feed(source)` valida la URL pública y extrae el RSS.
   - `parse_feed()` convierte XML en entradas con título, enlace, fecha, resumen, imagen o video.

3. Limpieza y deduplicación
   - se normalizan URLs con `canonical()`;
   - se eliminan URLs repetidas por distintas cadenas de consulta;
   - se agrupan titulares por similitud usando `difflib` y `cluster_articles()`;
   - se ordenan por fecha y cobertura.

4. Clasificación editorial
   - `topic()` detecta categoría por palabras claves;
   - `sensitive()` marca texto sensible;
   - `rank()` asigna valor según recencia y cobertura;
   - `grouping_status()` señala si es cobertura múltiple o fuente única.

5. Decisión de publicación
   - si no hay sensibilidad grave y hay cobertura suficiente, la noticia puede quedar aprobada;
   - si hay duda, se marca `review_needed` o se usa `draft_pending`;
   - cuando hay IA, el borrador se guarda pero sigue requiriendo revisión humana.

6. Persistencia en base de datos
   - cada noticia guarda: `slug`, `headline`, `original_headline`, `summary`, `topic`, `sources_json`, `timeline_json`, `evidence_json`, `status`, `approved`, `review_needed`, `image_url`, `video_url`, `draft_*`.

7. Generación de boletines y carruseles
   - `top_five()` prepara la selección más relevante;
   - `/api/boletin.html`, `/api/boletin.json` y `/api/boletin.png` exportan contenido editorial;
   - `/api/carousel/generate` y `/api/carousel/export` generan un deck y lo exportan en ZIP.

8. Publicación web y acceso por rutas
   - la aplicación sirve la SPA desde `/` y rutas de frontend;
   - las rutas de API exponen la funcionalidad para frontend y administración.

### Evidencias operativas reales observadas
Los endpoints principales que existen en el código y se usan desde la interfaz son:
- `/api/health`
- `/api/news`
- `/api/news/{slug}`
- `/api/sources`
- `/api/runs`
- `/api/boletin.html`
- `/api/boletin.png`
- `/api/boletin.json`
- `/api/carousel/generate`
- `/api/carousel/export`
- `/api/auth/register`
- `/api/auth/login`
- `/api/auth/logout`
- `/api/bookmarks`
- `/api/admin/pending`
- `/api/admin/collect`
- `/api/internal/collect`

---

## 5. Aspectos legales y open source

### Licencia
El repositorio incluye `LICENSE`, y la licencia es MIT. Esto significa:
- el código puede reutilizarse, distribuirse y adaptararse con la nota de copyright;
- la licencia no elimina responsabilidad ni sustituye revisión legal;
- la licencia cubre el código del proyecto, no el contenido periodístico ni derechos de terceros.

### Derechos de noticias y fotografías
La intención del sistema es explícitamente respetuosa con la propiedad de terceros:
- el README afirma que los titulares, artículos e imágenes de otros medios conservan los derechos de sus respectivos titulares;
- `feeds.py` señala el principio: “The publisher, not RADAR, owns referenced articles.”
- la aplicación genera imágenes SVG de fallback para evitar depender de fotografías ajenas sin permiso;
- la exportación de carrusel usa composición local y no se basa en fotografías de terceros de forma automática.

### Privacidad y atribución
Hay elementos de privacidad y seguridad implementados:
- `security.py` usa PBKDF2 con sal aleatoria;
- `config.py` guarda la clave de sesión en `data/` con permisos restringidos;
- `app.py` fija cabeceras de seguridad para cookies y navegador;
- existe un aviso de privacidad y un flujo de registro con aceptación de términos;
- `static/index.html` incluye enlaces a páginas de privacidad y términos.

### Limitaciones legales reales
Antes de una publicación pública o institucional, faltan tareas legales y de política:
- revisar términos de uso reales;
- revisar permisos para cada fuente RSS y cada imagen usada;
- definir política de tratamiento de datos de usuario;
- establecer mecanismo para eliminación de cuenta real y recuperación de contraseña;
- auditar la base de datos y las cookies en entorno real de producción.

---

## 6. Estado del repositorio y GitHub

### Evidencia del repositorio local
Se observa lo siguiente:
- existe `.gitignore`; protege `.env`, `__pycache__`, `data/`, etc.;
- existe `LICENSE` en raíz;
- existe `.github/workflows/poll-rss.yml` con automatización; 
- existe `README.md` con instrucciones, limitaciones y despliegue;
- no se observa un directorio `.git` en este proyecto local, por lo que no se puede afirmar que haya un repositorio Git activo en este checkout;
- el proyecto está preparado como carpeta de código, pero no necesariamente como repositorio de GitHub ya conectado.

### Documentación existente
Hay documentación relevante y real:
- `README.md` — guía principal del proyecto;
- `docs/Colab_original_profesor.ipynb` — cuaderno base del profesor con la guía original;
- `scripts/academic_rounds.py` — generación de tres rondas académicas;
- `validate_radar.ipynb` — validación y comprobación del sistema;
- `pytest_out.txt` — evidencia de pruebas ejecutadas con resultados reales.

### Archivos para colaboradores y contribuciones
El proyecto no presenta un `CONTRIBUTING.md` ni una guía formal de colaboración visible. Lo que sí existe es:
- documentación técnica;
- una guía de arranque local;
- un workflow de GitHub Actions;
- estructura por módulos y tests.

### Estado de contribución
La base del proyecto está preparada para ser compartida con un equipo, pero aún requiere:
- definir política de ramas y despliegue;
- establecer un repositorio remoto claro;
- separar entorno de desarrollo y producción;
- decidir si la publicación se hará en GitHub+Docker o en otro servicio.

---

## 7. Evidencias disponibles del proyecto

### Rutas relevantes del repositorio
- `README.md`
- `radar/app.py`
- `radar/store.py`
- `radar/feeds.py`
- `radar/pipeline.py`
- `radar/editorial.py`
- `radar/gemini.py`
- `radar/export.py`
- `radar/security.py`
- `static/index.html`
- `static/app.js`
- `static/styles.css`
- `tests/test_app.py`
- `tests/test_pipeline.py`
- `tests/test_editorial.py`
- `docs/Colab_original_profesor.ipynb`
- `.github/workflows/poll-rss.yml`
- `data/admin_credentials.txt`
- `data/radar.sqlite3`

### Rutas reales de la aplicación
El archivo `static/index.html` expone la navegación principal; la UI del proyecto usa rutas como:
- `/`
- `/radar`
- `/boletines`
- `/fuentes`
- `/metodologia`
- `/acceso`
- `/guardados`

La API real del backend ofrece endpoints de salud, noticias, fuentes, boletines y administración. La evidencia más clara de funcionamiento disponible reside en los endpoints y los tests, no en capturas visuales guardadas en el repositorio.

### Estado de capturas reales
No hay evidencia documental de capturas en formato PNG/JPG dentro del proyecto. Lo que sí existe son:
- rutas del frontend;
- endpoints activos ya definidos;
- test de exportación PNG (`/api/boletin.png`);
- exportación ZIP del carrusel;
- evidencia del código de renderizado y diseño.

---

## 8. Relación con la guía del profesor

El cuaderno `docs/Colab_original_profesor.ipynb` organiza el trabajo en cinco pasos, que son la base del proyecto 3. La relación con el código implementado es la siguiente:

### Paso A — Leer fuentes RSS en vivo
Cumplido parcialmente:
- el código del proyecto sí consulta feeds RSS publicados en la web;
- hay validación de URLs y parsing del XML;
- la semilla de fuentes se crea por defecto.

Pendiente o no validado:
- no hay verificación real con Internet y credenciales del entorno actual en un contexto de producción;
- los feeds públicos pueden fallar o no estar disponibles;
- no se ha confirmado la obtención exitosa de noticias reales en todos los medios configurados.

### Paso B — Limpiar, eliminar duplicados y ordenar
Cumplido en la lógica principal:
- `canonical()` limpia URLs;
- `cluster_articles()` agrupa titulares parecidos;
- `editorial.py` compara textos con `difflib`;
- `rank()` ordena por recencia, cobertura y relevancia.

Pendiente:
- no hay prueba formal de que la lógica resuelva todos los duplicados semánticos del mundo real;
- la documentación reconoce que no se promete “cero duplicados conceptuales”.

### Paso C — Redactar un boletín con citas y fuentes
Cumplido parcialmente:
- `gemini.py` implementa redacción basada en titulares y fuentes;
- el sistema intenta generar resumen y evidencia;
- la lógica conserva el titular original como fallback seguro.

Pendiente:
- no está validada una publicación real con IA y flujo editorial completo;
- la revisión humana es necesaria y no se ha ejecutado como proceso de producción.

### Paso D — Tiempo real y publicación en HTML
Cumplido parcialmente:
- hay recolección periódica y API de publicación;
- la app genera boletines HTML, PNG y JSON;
- el cron de GitHub Actions intenta sondear cada 15 minutos.

Pendiente:
- no hay despliegue real y persistente publicado en un host externo;
- no hay evidencia de producción con cron real ejecutándose contra el servidor.

### Paso E — Alternativa con Gemini y grounding
Cumplido en modelo de código:
- hay flujo con búsqueda orientada a fuentes y uso de Gemini con evidencia de `source_ids`; 
- el README también menciona la alternativa de Google AI y la recomendación de no inventar hechos.

Pendiente:
- no hay validación real con un modelo de Gemini funcionando con una clave de usuario y un flujo completo de comprobación.

---

## 9. Trabajo académico disponible para el equipo

Este proyecto permite elaborar documentos académicos sin tocar el código, siempre que se basen en la evidencia disponible. Se pueden distribuir tareas así:

### 1. Documento legal y de protección de datos
Tema: privacidad, propiedad intelectual, uso de fuentes, avisos legales, derechos de imagen.
- revisar README, `feeds.py`, `static/index.html`, `security.py` y el flujo de registro;
- documentar qué sí está hecho y qué falta para una publicación pública;
- analizar riesgos legales y recomendaciones antes de abrir el proyecto.

### 2. Informe técnico de arquitectura
Tema: diseño del sistema, flujo de datos y tecnologías.
- basarse en `radar/app.py`, `radar/store.py`, `radar/pipeline.py`, `radar/feeds.py`, `radar/export.py`;
- describir flujo completo, límites y dependencias;
- diferenciar implementado, probado y planificado.

### 3. Informe de pruebas y validación académica
Tema: pruebas, resultados, errores y estado del proyecto.
- usar `tests/test_app.py`, `tests/test_pipeline.py`, `tests/test_editorial.py`, `pytest_out.txt`;
- documentar la suite actual, el fallo observado y los niveles de validación;
- contrastar lo que está cubierto con lo que sigue pendiente.

### 4. Análisis del proyecto 3 frente a la guía del profesor
Tema: cumplimiento del trabajo académico y levantamiento de brechas.
- usar `docs/Colab_original_profesor.ipynb` y comparar con el código actual;
- señalar qué pasos están presentes, qué aún no se validan y qué requeriría un siguiente ciclo.

### 5. Informe de preparación para GitHub, Supabase y Vercel
Tema: estado real de publicación.
- basarse en README, `.github/workflows/poll-rss.yml`, `Dockerfile` y `config.py`;
- identificar qué está listo para alojar código, qué no corresponde a un despliegue estático y qué requiere rediseño.

---

## 10. Estado de publicación

### Preparado
Sí hay elementos listos para publicarlos o reutilizarlos como base de trabajo:
- `LICENSE` con MIT;
- `README.md` con guía local;
- `Dockerfile` para ejecutar la aplicación en contenedor;
- `.github/workflows/poll-rss.yml` para un cron seguro;
- `.env.example` para configuración local;
- `iniciar-windows.bat` e `iniciar-linux-macos.sh` para ejecución local;
- base de datos local SQLite y archivos de datos que se mantienen en `data/`.

### Falta para GitHub
Antes de publicar en GitHub con criterio de trabajo académico o productivo:
- confirmar si el proyecto está en repositorio Git real;
- revisar que no queden secretos ni claves sensibles;
- documentar el flujo de despliegue;
- preparar esquema de ramas y release;
- revisar que `data/` no se publique ni se comparta con credenciales reales.

### Falta para Supabase
El sistema actual no está construido sobre Supabase ni sobre PostgreSQL. La documentación explícita del README indica que:
- SQLite está pensado para una instancia local o una sola instancia;
- Supabase no es la arquitectura actual del proyecto;
- para pasar a Supabase sería necesario rediseñar almacenamiento, sesiones y despliegue.

### Falta para Vercel
El README lo deja claro: Vercel estático no sirve para esta implementación actual:
- la app usa SQLite local;
- necesita un servidor Python con persistencia;
- la funcionalidad de cron y autenticación implican más que un sitio estático.

### Conclusión de publicación
El proyecto está preparado como demostración técnica local y académica. No está listo para una publicación editorial pública real ni para una plataforma estática sin adaptar la arquitectura.

---

## 11. Conclusión

RADAR es un proyecto funcional como base de trabajo académico y técnico, pero con límites claros: no es un servicio periodístico validado, no está desplegado en producción y no tiene una revisión legal completa para uso público. La evidencias reales del repositorio muestran una aplicación con backend y frontend funcionales, automatización RSS, sistema editorial, exportación de boletines y pruebas parcialmente exitosas.

El estado más preciso es:
- Implementado: flujo principal de RSS, clasificación, deduplicación, autenticación, administración, boletines y generación de carrusel.
- Probado: la base del proyecto cuenta con pruebas reales; el estado del conjunto actual no está completamente verde.
- Pendiente: publicación real, validación jurídica, despliegue persistente y validación de flujo IA en entorno real.

La intención del proyecto es clara y está bien documentada; lo que aún falta es cerrar la brecha entre una base ejecutable local y una solución editorial o pública con estándares de publicación, seguridad y legalidad.
