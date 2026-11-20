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
    for(const v of [device,d.session_id||'—',d.aps_ventana||0,d.prediction_status||'—',ageText(ageSeconds(d.ultima_lectura_iso))])tr.appendChild(mk('td','',v));
    root.appendChild(tr)}if(!identities.length){const tr=mk('tr');const td=mk('td','', 'Sin datos todavía');td.colSpan=5;tr.appendChild(td);root.appendChild(tr)}}
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
    const [r,h,d]=await Promise.all([fetch('/api/v1/devices',{cache:'no-store'}),fetch('/api/v1/history?limit=50',{cache:'no-store'}),fetch('/api/v1/diagnostics',{cache:'no-store'})]);
    if(!r.ok||!h.ok||!d.ok)throw new Error('Respuesta HTTP incorrecta');
    const devices=await r.json(), records=await h.json(), live=await d.json();
    const data={dispositivos:[...new Set([...devices.map(x=>x.device_id),...Object.keys(live.devices||{})])],ubicaciones:{},diagnostico:live.devices||{},lecturas:records.length};
    for(const record of devices){const p=record.prediction, id=record.device_id;
      if(p.status==='estimated')data.ubicaciones[id]={salon:p.room,punto:p.point,zona:p.zone,aps:p.aps,confianza:p.confidence,fecha_iso:record.received_at};
      const seen=data.diagnostico[id]?.ultima_lectura_iso;
      data.diagnostico[id]={...data.diagnostico[id],ultima_lectura_iso:seen&&Date.parse(seen)>Date.parse(record.received_at)?seen:record.received_at,aps_ventana:p.aps,session_id:record.session_id,prediction_status:p.status};}
    const history=records.filter(x=>x.prediction.status==='estimated').map(x=>({
      fecha:x.received_at,dispositivo:x.device_id,salon:x.prediction.room,punto:x.prediction.point,
      aps:x.prediction.aps,confianza:x.prediction.confidence}));
    const next=[...(data.dispositivos||[])].sort((a,b)=>a.localeCompare(b));
    const changed=JSON.stringify(next)!==JSON.stringify(identities);identities=next;
    if(changed)syncFilter();window.lastData=data;
    renderAll(data);renderHistory(history);el('conn').textContent='● Conectado al servidor · '+new Date().toLocaleTimeString();el('conn').className='ok-text';
  }catch(err){el('conn').textContent='● Sin conexión al servidor. Comprueba que Python sigue ejecutándose.';el('conn').className='bad-text'}finally{requestBusy=false}}
async function init(){try{const r=await fetch('/api/v1/meta',{cache:'no-store'});const status=await r.json();layout=status.layout||{};
    el('knownAP').textContent=status.bssids;el('windowInfo').textContent='Últimos escaneos guardados';buildMap();
  }catch(e){el('conn').textContent='No se pudo cargar el plano.';el('conn').className='bad-text'}
  await update();setInterval(update,1500)}
init();
