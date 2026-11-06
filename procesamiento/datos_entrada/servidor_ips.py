import csv, json, math, sqlite3, time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
# Permite ejecutar el servidor en la misma carpeta que los CSV o dentro de subcarpeta.
def buscar(nombre):
    for p in (BASE/nombre, BASE.parent/nombre):
        if p.exists(): return p
    return None

def leer_csv(nombre):
    p=buscar(nombre)
    if not p: return []
    with p.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

escaneos=leer_csv('escaneos.csv')
referencias=leer_csv('fingerprint.csv')
METADATOS={'archivo','ubicacion','salon','punto','zona','fila','columna','x','y','scan_id','timestamp_inicio_ms','cantidad_escaneos'}
bssids=sorted(set(escaneos[0]) & set(referencias[0])-METADATOS) if escaneos and referencias else []
DB=BASE/'ips_demo.sqlite3'
with sqlite3.connect(DB) as db:
    db.execute('CREATE TABLE IF NOT EXISTS historial (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT DEFAULT CURRENT_TIMESTAMP, salon_real TEXT, punto_real TEXT, salon_pred TEXT, punto_pred TEXT, zona TEXT, confianza REAL, alerta TEXT)')

indice=0

def predecir(muestra):
    candidatos=[]
    for ref in referencias:
        diferencias=[]
        for b in bssids:
            try:
                a=float(muestra[b]); c=float(ref[b])
                if a > -100 and c > -100: diferencias.append((a-c)**2)
            except (ValueError,TypeError,KeyError): pass
        if diferencias:
            d=math.sqrt(sum(diferencias)/len(diferencias))
            candidatos.append((d,ref))
    candidatos.sort(key=lambda x:x[0])
    votos=defaultdict(float)
    for d,ref in candidatos[:3]: votos[(ref['salon'],ref['punto'])]+=1/(d+0.001)
    if not votos: return {'salon':'Desconocido','punto':'?','confianza':0}
    (salon,punto),peso=max(votos.items(),key=lambda x:x[1])
    return {'salon':salon,'punto':punto,'confianza':round(peso/sum(votos.values()),3)}

HTML='''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IPS Hospitalario — Demo</title><style>
body{font-family:system-ui,Arial;background:#f4f7fb;color:#14263b;margin:0}header{background:#143a5a;color:white;padding:22px 5%}main{max-width:1100px;margin:25px auto;padding:0 20px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:15px}.card,.panel{background:white;border:1px solid #dde5ee;border-radius:13px;padding:20px;box-shadow:0 2px 8px #18334a0b}.big{font-size:30px;font-weight:750;margin-top:7px}.muted{color:#617488}.layout{display:grid;grid-template-columns:2fr 1fr;gap:15px;margin-top:15px}.rooms{display:flex;gap:8px;margin:15px 0}.room{flex:1;background:#e7edf4;border:2px solid #cbd7e4;border-radius:9px;padding:12px;min-width:0}.room.active{border-color:#1874d2;background:#dbeeff}.points{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:12px}.point{background:white;text-align:center;border-radius:7px;padding:12px 2px;border:1px solid #d4dce7}.point.selected{background:#1769c0;color:white;font-weight:bold}.corridor{background:#e1e9e6;border:2px dashed #8cae9d;border-radius:8px;padding:12px;text-align:center}.alert{padding:13px;border-radius:8px;background:#e6f5ec;color:#17613c;font-weight:650}.alert.bad{background:#ffe7e7;color:#9c2222}button{background:#1769c0;color:white;border:0;border-radius:8px;padding:11px 16px;cursor:pointer}button.secondary{background:#52677e}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:9px;border-bottom:1px solid #e3eaf2}label{display:block;margin:10px 0}select{padding:8px;border-radius:6px} @media(max-width:750px){.layout{grid-template-columns:1fr}.rooms{flex-direction:column}}
</style></head><body><header><h1>IPS Hospitalario — UNSA</h1><div>Prototipo de localización Wi-Fi</div></header><main><div class="cards"><div class="card"><div class="muted">Ambiente estimado</div><div class="big" id="salon">—</div></div><div class="card"><div class="muted">Punto estimado</div><div class="big" id="punto">—</div></div><div class="card"><div class="muted">Peso relativo del voto k-NN</div><div class="big" id="conf">—</div></div><div class="card"><div class="muted">Escaneos disponibles</div><div class="big" id="total">—</div></div></div><div class="layout"><div class="panel"><h2>Plano esquemático (no a escala)</h2><div class="rooms" id="rooms"></div><div class="corridor">Pasillo compartido / puntos 10–12 según la etiqueta de cada archivo</div><p class="muted">Los puntos son relativos. No representan distancias en metros.</p></div><div class="panel"><h2>Control de demostración</h2><label>Zona autorizada <select id="autorizada"><option value="301">301</option><option value="Lab 3">Lab 3</option><option value="Lab 4">Lab 4</option></select></label><button onclick="siguiente()">Siguiente escaneo</button> <button class="secondary" onclick="alternar()" id="auto">Iniciar reproducción</button><p class="muted" id="real">Sin datos</p><div id="alerta" class="alert">Esperando escaneo</div><p class="muted">La alerta compara el salón estimado con el salón autorizado. La reproducción no demuestra latencia de captura en vivo.</p></div></div><div class="panel" style="margin-top:15px"><h2>Historial de predicciones</h2><table><thead><tr><th>Fecha</th><th>Real</th><th>Predicción</th><th>Alerta</th></tr></thead><tbody id="historial"></tbody></table></div></main><script>
let timer=null;
function dibujar(salon,punto){let h='';for(const s of ['301','Lab 3','Lab 4']){h+='<div class="room '+(salon===s?'active':'')+'"><b>'+s+'</b><div class="points">';for(const n of [3,2,1,6,5,4,9,8,7])h+='<div class="point '+(salon===s&&String(punto)===String(n)?'selected':'')+'">'+n+'</div>';h+='</div></div>'}document.getElementById('rooms').innerHTML=h}
async function actualizarHistorial(){const h=await(await fetch('/api/historial')).json();document.getElementById('historial').innerHTML=h.map(x=>'<tr><td>'+x.fecha+'</td><td>'+x.salon_real+' / '+x.punto_real+'</td><td>'+x.salon_pred+' / '+x.punto_pred+'</td><td>'+x.alerta+'</td></tr>').join('')}
async function siguiente(){const zona=document.getElementById('autorizada').value;const r=await fetch('/api/siguiente?zona='+encodeURIComponent(zona));const x=await r.json();if(x.error){alert(x.error);alternar(true);return}document.getElementById('salon').textContent=x.pred.salon;document.getElementById('punto').textContent=x.pred.punto;document.getElementById('conf').textContent=Math.round(x.pred.confianza*100)+'%';document.getElementById('total').textContent=x.total;document.getElementById('real').textContent='Dato de prueba: '+x.real.salon+' / punto '+x.real.punto+' · Escaneo '+x.indice+'/'+x.total;const a=document.getElementById('alerta');a.textContent=x.alerta;a.className='alert '+(x.alerta.startsWith('ALERTA')?'bad':'');dibujar(x.pred.salon,x.pred.punto);actualizarHistorial()}
function alternar(detener=false){if(timer){clearInterval(timer);timer=null}else if(!detener){timer=setInterval(siguiente,1500)}document.getElementById('auto').textContent=timer?'Detener reproducción':'Iniciar reproducción'}
dibujar('',0);fetch('/api/estado').then(r=>r.json()).then(x=>{document.getElementById('total').textContent=x.escaneos;if(!x.listo)document.getElementById('real').textContent='Faltan escaneos.csv y/o fingerprint.csv junto al servidor'});actualizarHistorial();
</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def responder(self,obj,estado=200,html=False):
        datos=(obj if html else json.dumps(obj,ensure_ascii=False)).encode('utf-8')
        self.send_response(estado)
        self.send_header('Content-Type','text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(datos)))
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(datos)
    def do_GET(self):
        global indice
        ruta=urlparse(self.path)
        if ruta.path=='/': return self.responder(HTML,html=True)
        if ruta.path=='/api/estado': return self.responder({'listo':bool(escaneos and referencias and bssids),'escaneos':len(escaneos),'referencias':len(referencias),'bssids':len(bssids)})
        if ruta.path=='/api/historial':
            with sqlite3.connect(DB) as db:
                db.row_factory=sqlite3.Row
                filas=[dict(r) for r in db.execute('SELECT fecha,salon_real,punto_real,salon_pred,punto_pred,alerta FROM historial ORDER BY id DESC LIMIT 20')]
            return self.responder(filas)
        if ruta.path=='/api/siguiente':
            if not escaneos or not referencias or not bssids: return self.responder({'error':'Faltan escaneos.csv o fingerprint.csv, o no coinciden los BSSID.'},400)
            from urllib.parse import parse_qs
            zona=parse_qs(ruta.query).get('zona',['301'])[0]
            muestra=escaneos[indice%len(escaneos)]
            indice+=1
            pred=predecir(muestra)
            alerta='ALERTA: zona no autorizada' if pred['salon']!=zona else 'Ubicación dentro de zona autorizada'
            with sqlite3.connect(DB) as db:
                db.execute('INSERT INTO historial (salon_real,punto_real,salon_pred,punto_pred,zona,confianza,alerta) VALUES (?,?,?,?,?,?,?)',(muestra.get('salon',''),muestra.get('punto',''),pred['salon'],pred['punto'],zona,pred['confianza'],alerta))
            return self.responder({'real':{'salon':muestra.get('salon',''),'punto':muestra.get('punto','')},'pred':pred,'alerta':alerta,'indice':indice,'total':len(escaneos)})
        self.responder({'error':'Ruta no encontrada'},404)

if __name__=='__main__':
    print('Escaneos:',len(escaneos),'Referencias:',len(referencias),'BSSID comunes:',len(bssids))
    if not escaneos or not referencias: print('AVISO: primero genera escaneos.csv y fingerprint.csv con tu script de procesamiento.')
    print('Dashboard: http://127.0.0.1:8000')
    ThreadingHTTPServer(('127.0.0.1',8000),Handler).serve_forever()
