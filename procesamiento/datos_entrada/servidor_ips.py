"""IPS Hospitalario UNSA — dashboard MULTIPACIENTE en vivo.

Compatible con la aplicacion ScanWifi existente (no requiere modificar Android).
La app envia: POST /api/reading
    {"device_id":"paciente_01","router_bssid":"aa:bb:cc:dd:ee:ff","rssi":-62}

Ejecutar: python servidor_ips.py
Colocar fingerprint.csv junto a este archivo o en la carpeta superior.
Abrir: http://127.0.0.1:8000 (dashboard local)

NOTA: prototipo docente sin autenticacion ni cifrado HTTPS. No utilizar con
identidades reales de pacientes o en redes publicas sin seguridad adicional.
"""

import csv
import json
import math
import re
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
PORT = 8000
WINDOW_SECONDS = 15.0  # Android puede enviar un BSSID por solicitud
MIN_APS = 2             # No localizar con una sola red
ABSENT = -100.0
HISTORY_EVERY_SECONDS = 8.0
LOG_EACH_READING = False  # Cambiar a True para ver BSSID y RSSI en PowerShell
METADATA = {
    'archivo', 'ubicacion', 'salon', 'punto', 'zona', 'fila', 'columna',
    'x', 'y', 'scan_id', 'timestamp_inicio_ms', 'cantidad_escaneos'
}
DB = BASE / 'ips_hospital.sqlite3'
BSSID_REGEX = re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')
lock = threading.RLock()
recepciones = defaultdict(dict)  # device -> bssid -> (rssi, monotonic_time)
ultimas = {}                     # device -> ultima prediccion
ultimo_global = None
estadisticas = {}                # device -> diagnostico
contador = 0
ultimo_guardado = {}
ultimo_mensaje = {}


def locate_file(name):
    for path in (BASE / name, BASE.parent / name):
        if path.is_file():
            return path
    return None


def load_fingerprints():
    path = locate_file('fingerprint.csv')
    if path is None:
        raise FileNotFoundError('No se encontro fingerprint.csv junto al servidor o en la carpeta superior.')

    with path.open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        fields = reader.fieldnames or []
        mapping = {
            field: field.strip().lower() for field in fields
            if field.strip().lower() not in METADATA and BSSID_REGEX.fullmatch(field.strip().lower())
        }
        rows = []
        for r in reader:
            try:
                room = r['salon'].strip()
                point = int(r['punto'])
                signals = {}
                for original, normalized in mapping.items():
                    raw = r.get(original, '').strip()
                    if raw:
                        value = float(raw)
                        if math.isfinite(value):
                            signals[normalized] = value
                rows.append({
                    'salon': room, 'punto': point, 'zona': r.get('zona', '').strip(),
                    'x': r.get('x', '').strip(), 'y': r.get('y', '').strip(),
                    'signals': signals
                })
            except (KeyError, ValueError):
                continue
    if not rows or not mapping:
        raise ValueError('fingerprint.csv debe tener salon, punto y columnas BSSID validas.')
    return rows, set(mapping.values()), path


REFERENCES, BSSIDS, FP_PATH = load_fingerprints()


def build_layout():
    layout = {}
    for ref in REFERENCES:
        room = ref['salon']
        if room not in layout:
            layout[room] = {'interior': [], 'pasillo': []}
        lane = 'pasillo' if ('pasillo' in ref['zona'].lower() or ref['punto'] >= 10) else 'interior'
        point = ref['punto']
        if point not in layout[room][lane]:
            layout[room][lane].append(point)
    for segments in layout.values():
        for lane in segments:
            segments[lane].sort()
    return layout


LAYOUT = build_layout()

with sqlite3.connect(DB, timeout=10) as db:
    db.execute('''CREATE TABLE IF NOT EXISTS historial (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        dispositivo TEXT NOT NULL,
        salon TEXT NOT NULL,
        punto INTEGER NOT NULL,
        zona TEXT,
        aps INTEGER NOT NULL,
        confianza REAL NOT NULL
    )''')


def predict(signals):
    """k-NN ponderado (k=3), distancia RSSI normalizada sobre AP compartidos."""
    candidates = []
    for ref in REFERENCES:
        overlap = [(value, ref['signals'][b]) for b, value in signals.items()
                   if b in ref['signals'] and ref['signals'][b] > ABSENT]
        if len(overlap) < MIN_APS:
            continue
        dist = math.sqrt(sum((a - b) ** 2 for a, b in overlap) / len(overlap))
        candidates.append((dist, ref))
    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[0])
    votes = defaultdict(float)
    for distance, ref in candidates[:3]:
        key = (ref['salon'], ref['punto'], ref['zona'])
        votes[key] += 1.0 / (distance + 0.001)
    (room, point, zone), strength = max(votes.items(), key=lambda pair: pair[1])
    # Este valor NO es una probabilidad estadistica calibrada.
    return {
        'salon': room, 'punto': point, 'zona': zone,
        'confianza': round(strength / sum(votes.values()), 3),
        'aps': len(signals), 'vecinos': min(3, len(candidates)),
    }


def iso_now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def device_summary(now):
    diagnostics = {}
    for device, s in estadisticas.items():
        active = {b for b, (_, stamp) in recepciones[device].items()
                  if now - stamp <= WINDOW_SECONDS}
        diagnostics[device] = {
            'lecturas': s['lecturas'], 'conocidas': s['conocidas'],
            'desconocidas': s['desconocidas'], 'aps_ventana': len(active),
            'ultima_lectura_iso': s['ultima_lectura_iso'],
            'ultimo_bssid': s['ultimo_bssid'],
            'bssid_reconocido': s['bssid_reconocido'],
        }
    return diagnostics


HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPS Hospitalario · Monitoreo multipaciente</title>
<style>
:root{color-scheme:light;--ink:#1b2a42;--sub:#64748b;--line:#dce5f0;--bg:#f5f7fb;--accent:#155dcc;--green:#15734c;--warn:#ac6810}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,Arial,sans-serif}
header{background:#142f53;color:white;padding:22px max(20px,calc((100% - 1200px)/2))}header h1{font-size:24px;letter-spacing:-.025em;margin:0}
header .subtitle{color:#c1d5ee;margin-top:5px}header .topline{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
header .pill{border:1px solid #49698d;border-radius:22px;padding:5px 11px;font-size:12px;color:#d7e9ff}
main{max-width:1240px;margin:24px auto;padding:0 19px 30px}.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:14px}
.card,.panel{background:white;border:1px solid var(--line);border-radius:13px;box-shadow:0 3px 12px #142b4f09}
.card{padding:15px 17px}.card .kpi-label{color:var(--sub);font-size:12px}.card .value{font-size:28px;font-weight:750;letter-spacing:-.03em;margin-top:5px}
.grid-layout{display:grid;grid-template-columns:minmax(0,2fr) minmax(300px,1fr);gap:13px}.panel{padding:18px;min-width:0}
.panel-head{display:flex;gap:15px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:14px}.panel h2{font-size:17px;margin:0;letter-spacing:-.015em}
.muted{color:var(--sub);font-size:12px}select{max-width:100%;background:white;color:var(--ink);border:1px solid #cbd5e1;border-radius:7px;padding:8px;font:inherit}
.rooms{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.room{border:1px solid #bed1ea;background:#eef4fc;border-radius:10px;padding:10px;min-width:0}.room h3{margin:0 0 10px;font-size:15px;color:#234b78}
.tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
.tile{position:relative;min-height:68px;background:white;border:1px solid #cfdbeb;border-radius:7px;padding:6px;display:flex;flex-direction:column;align-items:center;justify-content:space-between}
.tile .num{color:#8aa0b9;font-size:11px;align-self:flex-start}.tile .dots{display:flex;gap:3px;flex-wrap:wrap;justify-content:center;min-height:23px;align-content:center}
.tile.occupied{border-color:#5c96e3;background:#f3f8ff}.tile.empty{border-style:dashed;background:#f7f9fc;color:#c5cedb}
.dot{display:inline-flex;min-width:22px;height:22px;align-items:center;justify-content:center;color:white;border-radius:40px;border:2px solid white;box-shadow:0 0 0 1px #0001;font-size:10px;font-weight:750;line-height:1}
.dot.stale{opacity:.44;filter:grayscale(1)}.corridor{border:1px dashed #83b6a5;background:#edf8f4;border-radius:10px;margin-top:13px;padding:10px}
.corridor>strong{font-size:13px;color:#245f4c}.lanes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:9px}
.lane{min-width:0}.lane-name{font-size:11px;font-weight:650;color:#5b8071;margin-bottom:6px}
.lane .tile{min-height:50px}.lane .tile .num{font-size:10px}
.list{display:flex;flex-direction:column;gap:8px;max-height:560px;overflow:auto}
.person{display:flex;gap:10px;align-items:flex-start;border:1px solid var(--line);border-radius:10px;padding:11px;background:#fff;cursor:pointer;text-align:left;width:100%;color:var(--ink);font:inherit}
.person:hover,.person.selected{border-color:#83acf3;background:#f6f9ff}.person .avatar{flex:0 0 30px;height:30px;border-radius:100px;display:grid;place-items:center;color:white;font-size:12px;font-weight:800}
.person .info{min-width:0;flex:1}.person .name{font-weight:750;overflow-wrap:anywhere}.person .meta{color:var(--sub);font-size:12px;margin-top:2px}
.state{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;border-radius:12px;padding:3px 7px;white-space:nowrap;background:#fff2dc;color:#986010}
.state.live{background:#e5f6ed;color:#167047}.state.off{background:#f0f2f5;color:#697789}.empty-state{padding:28px 8px;text-align:center;color:var(--sub)}
.tables{margin-top:13px}.scroll{overflow:auto;max-height:250px}table{width:100%;border-collapse:collapse;font-size:12px;white-space:nowrap}th,td{text-align:left;padding:9px 8px;border-bottom:1px solid #e9eef4}th{color:#596c84;background:#f8fafd;position:sticky;top:0}
.footer-note{font-size:12px;color:var(--sub);margin:12px 0 0}.warning{margin-top:12px;padding:10px 12px;border:1px solid #f0d8a7;border-radius:8px;background:#fff9ec;color:#845600;font-size:12px}
#conn{font-size:12px;margin-bottom:10px}.ok-text{color:#17734b}.bad-text{color:#b33b3b}
@media(max-width:950px){.grid-layout{grid-template-columns:1fr}.rooms,.lanes{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:620px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.rooms,.lanes{grid-template-columns:1fr}.tile{min-height:52px}header h1{font-size:20px}}
</style></head><body>
<header><div class="topline"><div><h1>IPS Hospitalario · Monitoreo multipaciente</h1><div class="subtitle">Posicionamiento Wi-Fi por fingerprinting y k-NN · UNSA</div></div><span class="pill">Servidor local · Puerto 8000</span></div></header>
<main>
<div id="conn" class="muted">Conectando con el servidor...</div>
<div class="stats"><div class="card"><div class="kpi-label">Dispositivos detectados</div><div id="totalDevices" class="value">0</div></div>
<div class="card"><div class="kpi-label">Con ubicación reciente</div><div id="online" class="value">0</div></div>
<div class="card"><div class="kpi-label">Lecturas RSSI recibidas</div><div id="readings" class="value">0</div></div>
<div class="card"><div class="kpi-label">BSSID calibrados</div><div id="knownAP" class="value">0</div></div></div>
<div class="grid-layout"><section class="panel"><div class="panel-head"><div><h2>Mapa de ubicaciones</h2><span class="muted">Todos los pacientes aparecen al mismo tiempo. Marcadores grises = ubicación antigua.</span></div>
<select id="filter" aria-label="Filtrar paciente"><option value="">Todos los pacientes</option></select></div>
<div id="rooms" class="rooms"></div><div class="corridor"><strong>Pasillo compartido</strong><div id="lanes" class="lanes"></div></div>
<p class="footer-note">Plano esquemático, no a escala. Los puntos 10–12 se representan en el tramo de pasillo asociado a cada salón.</p>
<div class="warning">Prototipo de demostración. No usar para seguimiento clínico o decisiones de seguridad sin verificar precisión, cobertura, autenticación y protección de datos.</div>
</section>
<aside class="panel"><div class="panel-head"><h2>Pacientes / dispositivos</h2><span class="muted">Actualiza cada 1,5 s</span></div><div id="people" class="list"><div class="empty-state">Esperando mediciones desde Android...</div></div>
<p class="footer-note">Si un dispositivo recibe señales pero no aparece en el mapa, comprueba sus BSSID reconocidos en la tabla de diagnóstico.</p></aside></div>
<div class="panel tables"><div class="panel-head"><h2>Diagnóstico de recepción</h2><span id="windowInfo" class="muted">Ventana de mediciones</span></div><div class="scroll"><table><thead><tr><th>Dispositivo</th><th>Lecturas</th><th>Conocidas</th><th>Desconocidas</th><th>APs recientes</th><th>Último BSSID</th></tr></thead><tbody id="diag"></tbody></table></div></div>
<div class="panel tables"><div class="panel-head"><h2>Historial de predicciones</h2><span class="muted">Guardado en ips_hospital.sqlite3</span></div><div class="scroll"><table><thead><tr><th>Fecha</th><th>Dispositivo</th><th>Ambiente</th><th>Punto</th><th>APs</th><th>Consenso k-NN</th></tr></thead><tbody id="history"></tbody></table></div></div>
</main>
<script>
'use strict';
const palette=['#1b75d0','#e64e67','#16886e','#a359bd','#e28a25','#4269ac','#bc5b9b','#75943a'];
let layout={}, filter='', requestBusy=false;
let identities=[];
const el=id=>document.getElementById(id);
function colorFor(name){const index=identities.indexOf(name);return palette[(index<0?0:index)%palette.length]}
function numberFor(name){const index=identities.indexOf(name);return String(index+1)}
function ageSeconds(iso){if(!iso)return Infinity;const t=Date.parse(iso);return Number.isNaN(t)?Infinity:Math.max(0,(Date.now()-t)/1000)}
function ageText(sec){if(!Number.isFinite(sec))return 'sin datos';if(sec<3)return 'ahora';if(sec<60)return 'hace '+Math.floor(sec)+' s';return 'hace '+Math.floor(sec/60)+' min'}
function mk(tag, cls, content){const n=document.createElement(tag);if(cls)n.className=cls;if(content!==undefined)n.textContent=String(content);return n}
function tile(room,point,isCorridor){const n=mk('div','tile');n.dataset.room=room;n.dataset.point=String(point);n.dataset.zone=isCorridor?'pasillo':'interior';n.appendChild(mk('span','num','P'+point));n.appendChild(mk('div','dots'));return n}
function buildMap(){const rooms=el('rooms'),lanes=el('lanes');rooms.replaceChildren();lanes.replaceChildren();
  for(const [room,data] of Object.entries(layout)){
    const box=mk('section','room');box.appendChild(mk('h3','',room));const grid=mk('div','tiles');
    // Orden segun disposicion del conjunto de puntos de calibracion.
    const order=[3,2,1,6,5,4,9,8,7];
    const points=new Set(data.interior||[]);
    for(const p of order){const t=tile(room,p,false);if(!points.has(p))t.classList.add('empty');grid.appendChild(t)}
    box.appendChild(grid);rooms.appendChild(box);
    const lane=mk('div','lane');lane.appendChild(mk('div','lane-name',room));const row=mk('div','tiles');
    const corridorSet=new Set(data.pasillo||[]);
    for(const p of [12,11,10]){const t=tile(room,p,true);if(!corridorSet.has(p))t.classList.add('empty');row.appendChild(t)}
    lane.appendChild(row);lanes.appendChild(lane);
  }
}
function renderMap(positions,diagnostics){document.querySelectorAll('.tile .dots').forEach(x=>x.replaceChildren());document.querySelectorAll('.tile').forEach(x=>x.classList.remove('occupied'));
  for(const device of identities){if(filter && device!==filter)continue;
    const p=positions[device];if(!p)continue;
    const isCorridor=String(p.zona||'').toLowerCase().includes('pasillo')||Number(p.punto)>=10;
    const target=Array.from(document.querySelectorAll('.tile')).find(t=>t.dataset.room===p.salon&&t.dataset.point===String(p.punto)&&t.dataset.zone===(isCorridor?'pasillo':'interior'));
    if(!target)continue;
    const dot=mk('span','dot',numberFor(device));dot.style.background=colorFor(device);
    const recent=ageSeconds(diagnostics[device]?.ultima_lectura_iso)<25 && ageSeconds(p.fecha_iso)<35;
    if(!recent)dot.classList.add('stale');
    dot.title=device+' · '+p.salon+' · punto '+p.punto+(recent?' · reciente':' · última ubicación conocida');
    target.querySelector('.dots').appendChild(dot);target.classList.add('occupied');
  }
}
function statusFor(device,position,diagnostic){const since=ageSeconds(diagnostic?.ultima_lectura_iso);
  if(since>=25)return ['Sin señal','off'];
  if(!position)return ['Sin ubicación',''];
  if(ageSeconds(position.fecha_iso)>=35)return ['Sin ubicación reciente',''];
  return ['En vivo','live'];
}
function renderPeople(positions,diag){const root=el('people');root.replaceChildren();if(!identities.length){root.appendChild(mk('div','empty-state','Esperando mediciones desde Android...'));return}
  for(const device of identities){if(filter && filter!==device)continue;
    const p=positions[device],d=diag[device]||{};
    const button=mk('button','person'+(filter===device?' selected':''));button.type='button';
    button.onclick=()=>{filter=filter===device?'':device;el('filter').value=filter;renderAll(window.lastData)};
    const avatar=mk('div','avatar',numberFor(device));avatar.style.background=colorFor(device);button.appendChild(avatar);
    const info=mk('div','info');info.appendChild(mk('div','name',device));
    info.appendChild(mk('div','meta',p?p.salon+' · Punto '+p.punto+' · '+p.aps+' APs':'Ubicación pendiente'));
    info.appendChild(mk('div','meta','Última lectura: '+ageText(ageSeconds(d.ultima_lectura_iso))));
    const [name,status]=statusFor(device,p,d);const label=mk('span','state '+status,name);
    button.append(info,label);root.appendChild(button);
  }
}
function renderDiagnostic(diag){const root=el('diag');root.replaceChildren();for(const device of identities){const d=diag[device]||{};const tr=mk('tr');
    for(const v of [device,d.lecturas||0,d.conocidas||0,d.desconocidas||0,d.aps_ventana||0,d.ultimo_bssid||'—'])tr.appendChild(mk('td','',v));
    root.appendChild(tr)}if(!identities.length){const tr=mk('tr');const td=mk('td','', 'Sin datos todavía');td.colSpan=6;tr.appendChild(td);root.appendChild(tr)}}
function renderHistory(rows){const root=el('history');root.replaceChildren();for(const h of rows){const tr=mk('tr');
    for(const v of [h.fecha,h.dispositivo,h.salon,h.punto,h.aps,Math.round(h.confianza*100)+' %'])tr.appendChild(mk('td','',v));root.appendChild(tr)}
  if(!rows.length){const tr=mk('tr');const td=mk('td','','Aún no existen predicciones');td.colSpan=6;tr.appendChild(td);root.appendChild(tr)}
}
function syncFilter(){const sel=el('filter');const previous=filter;sel.replaceChildren();const all=mk('option','', 'Todos los pacientes');all.value='';sel.appendChild(all);
  for(const name of identities){const item=mk('option','',name);item.value=name;sel.appendChild(item)}
  if(previous && identities.includes(previous)){sel.value=previous}else{filter='';sel.value=''}
}
function renderAll(data){if(!data)return;const positions=data.ubicaciones||{},diagnostics=data.diagnostico||{};
  el('totalDevices').textContent=identities.length;
  el('online').textContent=identities.filter(d=>positions[d]&&ageSeconds(diagnostics[d]?.ultima_lectura_iso)<25&&ageSeconds(positions[d]?.fecha_iso)<35).length;
  el('readings').textContent=data.lecturas||0;
  renderMap(positions,diagnostics);renderPeople(positions,diagnostics);renderDiagnostic(diagnostics);
}
el('filter').onchange=e=>{filter=e.target.value;renderAll(window.lastData)};
async function update(){if(requestBusy)return;requestBusy=true;try{
    const [r,h]=await Promise.all([fetch('/api/ubicacion',{cache:'no-store'}),fetch('/api/historial',{cache:'no-store'})]);
    if(!r.ok||!h.ok)throw new Error('Respuesta HTTP incorrecta');
    const data=await r.json(), history=await h.json();
    const next=[...(data.dispositivos||[])].sort((a,b)=>a.localeCompare(b));
    const changed=JSON.stringify(next)!==JSON.stringify(identities);identities=next;
    if(changed)syncFilter();window.lastData=data;
    renderAll(data);renderHistory(history);el('conn').textContent='● Conectado al servidor · '+new Date().toLocaleTimeString();el('conn').className='ok-text';
  }catch(err){el('conn').textContent='● Sin conexión al servidor. Comprueba que Python sigue ejecutándose.';el('conn').className='bad-text'}finally{requestBusy=false}}
async function init(){try{const r=await fetch('/api/estado',{cache:'no-store'});const status=await r.json();layout=status.plano||{};
    el('knownAP').textContent=status.bssids;el('windowInfo').textContent='Agrupación de '+status.ventana_segundos+' segundos · mínimo '+status.min_aps+' APs conocidos';buildMap();
  }catch(e){el('conn').textContent='No se pudo cargar el plano.';el('conn').className='bad-text'}
  await update();setInterval(update,1500)}
init();
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Evita inundar la consola con consultas automaticas del dashboard.
        if self.path.startswith('/api/ubicacion') or self.path.startswith('/api/historial'):
            return
        super().log_message(fmt, *args)

    def respond(self, payload, status=200, html=False):
        body = (payload if html else json.dumps(payload, ensure_ascii=False)).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            return self.respond(HTML, html=True)
        if path == '/api/estado':
            return self.respond({
                'listo': True, 'referencias': len(REFERENCES), 'bssids': len(BSSIDS),
                'lista_bssids': sorted(BSSIDS), 'plano': LAYOUT,
                'puerto': PORT, 'ventana_segundos': WINDOW_SECONDS, 'min_aps': MIN_APS,
            })
        if path == '/api/ubicacion':
            with lock:
                return self.respond({
                    'ultima': ultimo_global,
                    'ubicaciones': dict(ultimas),
                    'dispositivos': list(estadisticas),
                    'diagnostico': device_summary(time.monotonic()),
                    'lecturas': contador,
                })
        if path == '/api/historial':
            with sqlite3.connect(DB, timeout=10) as db:
                db.row_factory = sqlite3.Row
                history = [dict(x) for x in db.execute(
                    'SELECT fecha,dispositivo,salon,punto,zona,aps,confianza FROM historial ORDER BY id DESC LIMIT 50')]
            return self.respond(history)
        return self.respond({'error': 'Ruta inexistente'}, 404)

    def do_POST(self):
        global contador, ultimo_global
        if urlparse(self.path).path != '/api/reading':
            return self.respond({'error': 'Ruta inexistente. Usa POST /api/reading'}, 404)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                return self.respond({'error': 'Tamano de JSON invalido'}, 400)
            payload = json.loads(self.rfile.read(length))
            device = str(payload['device_id']).strip()[:80]
            bssid = str(payload['router_bssid']).strip().lower()
            rssi = float(payload['rssi'])
            if not device or not BSSID_REGEX.fullmatch(bssid) or not math.isfinite(rssi) or not -120 <= rssi <= 0:
                raise ValueError('Valores invalidos')
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return self.respond({'error': 'JSON esperado: device_id, router_bssid, rssi'}, 400)

        now = time.monotonic()
        current_iso = iso_now()
        with lock:
            contador += 1
            matched = bssid in BSSIDS
            if device not in estadisticas:
                estadisticas[device] = {
                    'lecturas': 0, 'conocidas': 0, 'desconocidas': 0,
                    'ultima_lectura_iso': '', 'ultimo_bssid': '', 'bssid_reconocido': False,
                }
            stats = estadisticas[device]
            stats['lecturas'] += 1
            stats['conocidas' if matched else 'desconocidas'] += 1
            stats['ultima_lectura_iso'] = current_iso
            stats['ultimo_bssid'] = bssid
            stats['bssid_reconocido'] = matched

            if LOG_EACH_READING:
                print(f'[ANDROID] {device} | BSSID={bssid} | RSSI={rssi:g} | Reconocido={matched}', flush=True)
            if not matched:
                return self.respond({'estado': 'recibido', 'usado': False,
                                     'motivo': 'BSSID fuera del fingerprint', 'dispositivo': device})

            recepciones[device][bssid] = (rssi, now)
            for b, (_, timestamp) in list(recepciones[device].items()):
                if now - timestamp > WINDOW_SECONDS:
                    del recepciones[device][b]
            signals = {b: r for b, (r, _) in recepciones[device].items()}

            if len(signals) < MIN_APS:
                return self.respond({'estado': 'recibido', 'usado': True, 'dispositivo': device,
                                     'aps': len(signals), 'esperando': 'mas BSSID conocidos'})

            result = predict(signals)
            if result is None:
                return self.respond({'estado': 'recibido', 'usado': True, 'dispositivo': device,
                                     'aps': len(signals), 'esperando': 'fingerprints comparables'})
            timestamp = datetime.now().astimezone()
            result.update({
                'dispositivo': device, 'fecha': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'fecha_iso': timestamp.isoformat(timespec='seconds'),
            })
            previous = ultimas.get(device)
            ultimas[device] = result
            ultimo_global = result
            changed = (previous is None or previous['salon'] != result['salon'] or
                       previous['punto'] != result['punto'])
            if changed or now - ultimo_guardado.get(device, 0) >= HISTORY_EVERY_SECONDS:
                ultimo_guardado[device] = now
                with sqlite3.connect(DB, timeout=10) as db:
                    db.execute(
                        'INSERT INTO historial (fecha,dispositivo,salon,punto,zona,aps,confianza) '
                        'VALUES (?,?,?,?,?,?,?)',
                        (result['fecha'], device, result['salon'], result['punto'],
                         result['zona'], result['aps'], result['confianza'])
                    )
            if changed or now - ultimo_mensaje.get(device, 0) >= 12:
                ultimo_mensaje[device] = now
                print(f'[POSICION] {device}: {result["salon"]}, punto {result["punto"]} '
                      f'({len(signals)} APs, consenso {result["confianza"]:.0%})', flush=True)
            return self.respond({'estado': 'recibido', 'usado': True, 'ubicacion': result})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    print(f'Fingerprints: {len(REFERENCES)} | BSSID: {len(BSSIDS)} | Archivo: {FP_PATH}')
    print(f'Mapa: {", ".join(LAYOUT)}')
    print(f'Dashboard: http://127.0.0.1:{PORT}')
    print(f'Android: http://IP_DE_TU_PC:{PORT} (no escribas /api/reading en ScanWifi)')
    print(f'Ventana={WINDOW_SECONDS:g}s | Minimo={MIN_APS} BSSID conocidos')
    print('Ctrl+C para detener. Prototipo para red local de confianza.')
    try:
        Server(('0.0.0.0', PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print('\nServidor detenido.')
