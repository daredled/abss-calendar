# ABSS → Google Calendar

Sincroniza automáticamente los partidos de tu equipo (liga ABSS) desde el PDF
de programación (`https://abss.cl/campeonato/todo.php`) a un Google Calendar,
detectando altas, cambios de horario/gimnasio y bajas.

## Cómo funciona

1. Cada vez que corre (recomendado: cron cada hora), revisa la página de
   programación y descarga el/los PDF(s) más recientes.
2. Calcula el MD5 de cada PDF. Si no cambió respecto a la última corrida, no
   hace nada más (no llama a la API de Google).
3. Si cambió, extrae los partidos del equipo configurado y compara contra el
   estado anterior usando una **llave estable** por partido: el ID de partido
   del PDF cuando lo trae (formato hasta la jornada 21), o una llave sintética
   `jornada + categoría + equipos` cuando no (formato nuevo, jornada 22 en
   adelante, que dejó de publicar el ID de partido y la cancha).
4. Crea, actualiza o borra eventos en Google Calendar según corresponda.

> **Nota sobre el formato del PDF:** ABSS cambió la plantilla de la
> programación a partir de la jornada 22 (equipos separados por `VS`, árbitros
> en línea aparte, sin ID de partido ni cancha). El parser entiende ambos
> formatos. Si algún PDF se publica como imagen escaneada (sin capa de texto),
> se registra un aviso y se omite sin tocar el calendario.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (instalador y gestor de entornos de Python)
- Una cuenta de Google y acceso a [Google Cloud Console](https://console.cloud.google.com/)

Si no tienes `uv` instalado:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Instalación

```bash
git clone <este-repo>
cd abss-calendar
uv sync
```

`uv sync` crea un entorno virtual en `.venv/` (usando la versión de Python
que pida `pyproject.toml`, descargándola sola si hace falta) e instala ahí
las dependencias — no hace falta crear ni activar el venv a mano.

Para incluir además las dependencias de test:

```bash
uv sync --extra dev
```

## Configuración

### 1. Habilitar Google Calendar API y crear credenciales OAuth

1. Entra a [Google Cloud Console](https://console.cloud.google.com/) y crea un proyecto (o usa uno existente).
2. En "APIs y servicios" → "Biblioteca", busca **Google Calendar API** y habilítala.
3. En "APIs y servicios" → "Credenciales" → "Crear credenciales" → "ID de cliente de OAuth".
4. Tipo de aplicación: **Aplicación de escritorio**.
5. Descarga el JSON generado y guárdalo como `credentials.json` en la raíz del proyecto.

### 2. Crear un calendario dedicado (recomendado)

1. En Google Calendar, crea un calendario nuevo (ej. "Basquetbol Mi Equipo 45-A").
2. Entra a su configuración → "Integrar calendario" → copia el **ID de calendario**
   (algo como `xxxxxxx@group.calendar.google.com`).

### 3. Crear y editar `config.yaml`

`config.yaml` no se versiona (tiene datos propios de tu instalación, como el
ID de tu calendario). Copia el ejemplo y edítalo:

```bash
cp config.yaml.example config.yaml
```

```yaml
team_name: "MI EQUIPO 45-A"      # como aparece exactamente en el PDF
source_url: "https://abss.cl/campeonato/todo.php"
fechas_lookback: 1
google_calendar_id: "TU_CALENDAR_ID@group.calendar.google.com"
event_duration_minutes: 80
timezone: "America/Santiago"
```

### 4. Primera ejecución (login interactivo)

```bash
uv run src/main.py
```

Esto abrirá el navegador para autorizar el acceso a tu Google Calendar. Tras
autorizar, se genera `token.json` — las siguientes ejecuciones ya no piden login.

## Generar nómina de jugadores

Además de sincronizar el calendario, el proyecto puede generar el texto de
la nómina (listo para pegar en WhatsApp) del **próximo partido** del equipo
configurado (se elige automáticamente por fecha/hora, no hace falta indicar
cuál):

```bash
uv run src/generar_nomina.py
```

También se puede pedir desde `main.py` con `--nomina` (no sincroniza el
calendario, solo imprime la nómina):

```bash
uv run src/main.py --nomina
```

El resultado se ve así:

```
🏀 MI EQUIPO 45-A vs OTRO EQUIPO 45-A
📅 domingo 12 de julio de 2026
🕔 Citación: 12:30 hrs
🕔 Inicio partido: 13:00 hrs
📍 GIMNASIO EJEMPLO, CALLE FALSA 123, MI CIUDAD.

Nómina:
1.-
2.-
...
12.-
```

## Tests

El proyecto incluye una suite de unit tests (45 tests) que corren sin
necesidad de red ni credenciales de Google — cubren el parser del PDF, el
descubrimiento de links, la lógica de diff (nuevo/actualizado/borrado), la
construcción de eventos (mockeando la API de Google Calendar) y la
generación de la nómina del próximo partido.

```bash
uv sync --extra dev
uv run pytest
```

## Automatización con cron

El repo incluye `sync.sh`, un wrapper mínimo para cron: se ubica solo en la
raíz del repo y arma el `PATH` para encontrar `uv` (cron corre con un `PATH`
mínimo y no carga tu `.bashrc`/`.zshrc`). El log lo maneja el crontab.

```bash
crontab -e
```

Agregar (cada hora, en punto):

```
0 * * * * /ruta/completa/abss-calendar/sync.sh >> /ruta/completa/abss-calendar/sync.log 2>&1
```

Cualquier argumento extra se pasa tal cual a `src/main.py` (ej.
`sync.sh --nomina`).

> **Nota:** si `uv` no está en `~/.local/bin` ni `~/.cargo/bin`, agrega su
> carpeta al bucle de `PATH` en `sync.sh` o asegúrate de que `uv` esté en el
> `PATH` del entorno de cron.

## Archivos generados / propios de cada instalación (no se suben a git)

- `config.yaml` — tu configuración (equipo, calendario, etc.), a partir de `config.yaml.example`.
- `token.json` — credenciales OAuth ya autorizadas.
- `state.json` — hashes de PDFs procesados y estado de partidos sincronizados.
- `sync.log` — log de cada corrida (redirigido desde el crontab).

Si clonas este repo en otra máquina o para otro equipo, cada instalación
genera su propio `config.yaml`, `state.json` y `token.json` la primera vez
que corre.

## Reusar para otro equipo

Este repo no está atado a un equipo específico. Basta con:
1. Clonarlo (o hacer fork).
2. Cambiar `team_name` y `google_calendar_id` en `config.yaml`.
3. Generar tus propias credenciales OAuth (paso 1 de arriba).

## Estructura del proyecto

```
abss-calendar/
├── config.yaml.example  # plantilla de configuración (versionada)
├── config.yaml           # tu configuración real (no versionado)
├── credentials.json      # OAuth client (no versionado)
├── token.json              # generado en 1er login (no versionado)
├── state.json                # estado de sincronización (no versionado)
├── src/                        # código fuente
│   ├── fetch_pdf.py               # descubre y descarga el PDF vigente
│   ├── parse_pdf.py                 # extrae partidos del equipo configurado
│   ├── sync_calendar.py               # crea/actualiza/borra eventos vía API
│   ├── main.py                          # orquesta el flujo completo
│   └── generar_nomina.py                  # genera la nómina del próximo partido
├── tests/                             # unit tests (pytest)
│   ├── fixtures.py
│   ├── test_parse_pdf.py
│   ├── test_fetch_pdf.py
│   ├── test_main_diff.py
│   ├── test_sync_calendar.py
│   └── test_generar_nomina.py
├── pyproject.toml                    # dependencias + config de pytest
└── README.md
```
