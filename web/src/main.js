import { STATUS, validateDataset, selectStations, bounds, sectors, sectorSummaries, summary,
         historySegments, relativeAge, captureFreshness, html, display, pct, localTime } from './core.js';

const $ = id => document.getElementById(id);
const COLORS = {available:'#94dabb',empty:'#efac84',unknown:'#78919c'};
const state = { dataset:null, stations:[], view:'reseau', query:'', filter:'all', sector:'all', selected:null,
                map:null, mapReady:false, mapFailed:false };

function paintStats() {
  const d=state.dataset, m=d.metrics;
  $('stat-total').textContent=display(m.stations);
  $('stat-bikes').textContent=display(m.bikes);
  $('stat-empty').textContent=display(m.empty);
  $('stat-empty-caption').textContent=`${pct(m.usable?m.empty/m.usable:null)} des ${display(m.usable)} stations qualifiées`;
  $('stat-usable').textContent=display(m.usable);
  $('stat-denominator').textContent=`/ ${display(m.observed)}`;
  $('stat-quality-caption').textContent=`${display(m.unusable)} observations non exploitables`;
  const recent=captureFreshness(d.captured_at);
  const truth=document.querySelector('.truth');truth.classList.toggle('good',recent==='recent');
  $('freshness-label').textContent=recent==='recent'?'CAPTURE RÉCENTE':recent==='aging'?'ARCHIVE EN DIFFÉRÉ':'ARCHIVE ANCIENNE';
  $('capture-time').textContent=`Capture : ${localTime(d.captured_at)} · ${relativeAge(d.captured_at)}`;
  $('top-capture').textContent=`ARCHIVE ${localTime(d.captured_at)}`;
  document.querySelector('.signal').classList.toggle('stale',recent==='stale');
}

function filtered() {
  return selectStations(state.stations,{query:state.query,filter:state.filter,sector:state.sector});
}
function geojson(stations) {
  return {type:'FeatureCollection',features:stations.map(s=>({
    type:'Feature',id:s.id,geometry:{type:'Point',coordinates:[s.lon,s.lat]},
    properties:{id:s.id,condition:s.condition,selected:s.id===state.selected?1:0},
  }))};
}
function repaintMap() {
  const filteredStations=filtered();
  $('map-count').textContent=`${display(filteredStations.length)} POINTS AFFICHÉS`;
  if(state.mapReady && state.map?.getSource('stations')) {
    state.map.getSource('stations').setData(geojson(filteredStations));
  } else if(state.mapFailed){ fallbackMap(filteredStations); }
}
function fallbackMap(points) {
  $('map').hidden=true;
  const surface=$('map-fallback');surface.hidden=false;
  const full=bounds(state.stations),pad=.05;
  const west=full.west-(full.east-full.west)*pad,east=full.east+(full.east-full.west)*pad;
  const south=full.south-(full.north-full.south)*pad,north=full.north+(full.north-full.south)*pad;
  surface.replaceChildren();
  const label=document.createElement('span');label.className='fallback-caption';
  label.textContent='POSITION RÉELLE DES STATIONS · FOND DE CARTE INDISPONIBLE';surface.append(label);
  const frag=document.createDocumentFragment();
  for (const s of points) {
    const point=document.createElement('button');point.type='button';
    point.className='fallback-point '+(s.condition==='available'?'':s.condition);
    point.style.left=(100*(s.lon-west)/(east-west)).toFixed(3)+'%';
    point.style.top=(100*(north-s.lat)/(north-south)).toFixed(3)+'%';
    point.title=s.name;point.setAttribute('aria-label',s.name);
    point.addEventListener('click',()=>selectStation(s.id));frag.append(point);
  }
  surface.append(frag);
}
function mapFallback() {
  if(state.mapFailed)return;
  state.mapFailed=true;
  try{state.map?.remove()}catch(_){/* safe fallback */}
  state.map=null;state.mapReady=false;fallbackMap(filtered());
}
function initMap() {
  const maplibre=window.maplibregl;
  if(!maplibre){mapFallback();return;}
  try {
    const map=new maplibre.Map({
      container:'map',style:'https://tiles.openfreemap.org/styles/dark',
      center:[2.348,48.856],zoom:11,attributionControl:false,pitchWithRotate:false,
      dragRotate:false,cooperativeGestures:false,
    });
    state.map=map;
    map.addControl(new maplibre.NavigationControl({showCompass:false}), 'bottom-right');
    map.on('load',()=>{
      if(state.mapFailed)return;
      state.mapReady=true;
      map.addSource('stations',{type:'geojson',data:geojson(filtered()),cluster:true,clusterRadius:29,clusterMaxZoom:13});
      map.addLayer({id:'cluster-halo',type:'circle',source:'stations',filter:['has','point_count'],paint:{
        'circle-radius':['step',['get','point_count'],18,25,23,100,29],
        'circle-color':'#1b4140','circle-stroke-color':'#9be1bb','circle-stroke-width':1.1,'circle-opacity':.94,
      }});
      map.addLayer({id:'cluster-count',type:'symbol',source:'stations',filter:['has','point_count'],layout:{'text-field':['get','point_count_abbreviated'],'text-size':11},paint:{'text-color':'#e1f3e8'}});
      map.addLayer({id:'station-circles',type:'circle',source:'stations',filter:['!', ['has','point_count']],paint:{
        'circle-color':['match',['get','condition'],'available',COLORS.available,'empty',COLORS.empty,COLORS.unknown],
        'circle-radius':['case',['==',['get','selected'],1],9,5],
        'circle-stroke-color':['case',['==',['get','selected'],1],'#fff','#06161b'],
        'circle-stroke-width':['case',['==',['get','selected'],1],2.5,1],
        'circle-opacity':.92,
      }});
      map.on('click','cluster-halo',(evt)=>{
        const feature=map.queryRenderedFeatures(evt.point,{layers:['cluster-halo']})[0];if(!feature)return;
        map.getSource('stations').getClusterExpansionZoom(feature.properties.cluster_id,(error,zoom)=>{
          if(!error)map.easeTo({center:feature.geometry.coordinates,zoom});
        });
      });
      map.on('click','station-circles',evt=>{
        const f=evt.features?.[0];if(f)selectStation(String(f.properties.id));
      });
      for (const layer of ['station-circles','cluster-halo']) {
        map.on('mouseenter',layer,()=>{map.getCanvas().style.cursor='pointer'});
        map.on('mouseleave',layer,()=>{map.getCanvas().style.cursor=''});
      }
      repaintMap();
    });
    map.on('error',event=>{
      // A basemap outage does not invent geo data: fallback plots actual coordinates only.
      if(!state.mapReady) mapFallback();
      else console.warn('Fond cartographique indisponible :',event.error?.message||'erreur cartographique');
    });
    setTimeout(()=>{if(!state.mapReady&&!state.mapFailed)mapFallback()},12000);
  }catch(err){console.warn('Map unavailable',err);mapFallback()}
}
function focusStation(station) {
  if(state.mapReady&&state.map) state.map.flyTo({center:[station.lon,station.lat],zoom:Math.max(state.map.getZoom(),14),essential:true});
}
function selectStation(id) {
  const station=state.stations.find(s=>s.id===id);
  if(!station)return;
  state.selected=station.id;state.view='reseau';state.sector='all';
  updateNav();renderInspector();repaintMap();focusStation(station);
}
function updateNav() {
  for(const nav of document.querySelectorAll('.nav'))nav.classList.toggle('active',nav.dataset.view===state.view);
  const views={reseau:['01 / 04','Disponibilité par station'],territoires:['02 / 04','Répartition géographique'],fiabilite:['03 / 04','Stations et qualité des mesures'],previsions:['04 / 04','Prévisions / en attente']};
  document.querySelector('.index').textContent=views[state.view][0];
  $('map-title').textContent=views[state.view][1];
  $('panel-state').textContent=state.view==='previsions'?'NON VALIDÉ':state.view==='fiabilite'?'CONTRÔLE':state.view==='territoires'?'ANALYSE SPATIALE':'EXPLORATION';
}
function statusChip(station){
  const category=station.condition;
  return `<span class="station-status ${category}"><i class="dot dot-${category==='available'?'good':category}"></i>${STATUS[category]}</span>`;
}
function renderStationDetail(station){
  return `<div class="station-inspect">
    <button class="back-btn" type="button" data-back="1">← RETOUR AUX STATIONS</button>
    <span class="station-kicker">STATION / ${html(station.code||station.id)}</span>
    <h3>${html(station.name)}</h3>${statusChip(station)}
    <div class="detail-split"><div class="detail-cell"><label>VÉLOS DISPONIBLES</label><strong>${station.bikes===null?'—':display(station.bikes)}</strong></div><div class="detail-cell"><label>BORNES LIBRES</label><strong>${station.docks===null?'—':display(station.docks)}</strong></div></div>
    <div class="detail-meta"><span>Vélos mécaniques</span><strong>${station.mechanical==null?'Non qualifié':display(station.mechanical)}</strong></div>
    <div class="detail-meta"><span>Vélos électriques</span><strong>${station.electric==null?'Non qualifié':display(station.electric)}</strong></div>
    <div class="detail-meta"><span>Capacité déclarée</span><strong>${display(station.capacity)} bornes</strong></div>
    <div class="detail-meta"><span>Dernier signal station</span><strong>${station.reported_at?localTime(station.reported_at):'Non disponible'}</strong></div>
    <div class="detail-meta"><span>Position</span><strong>${station.lat.toFixed(5)} / ${station.lon.toFixed(5)}</strong></div>
    <p class="detail-disclaimer" style="margin-top:18px;font-size:11px;color:var(--muted);line-height:1.6">Ces valeurs proviennent d’une capture archivée, et non d'une consultation en temps réel.</p>
  </div>`;
}
function stationRows(stations) {
  if(!stations.length)return '<div class="sidebar-placeholder">Aucune station ne correspond aux filtres.</div>';
  return stations.slice(0,250).map((s,i)=>`<button class="station-row ${s.id===state.selected?'selected':''}" type="button" data-station="${html(s.id)}" aria-label="Afficher la station ${html(s.name)}"><span class="row-count">${String(i+1).padStart(2,'0')}</span><span class="row-info"><span class="row-name">${html(s.name)}</span><span class="row-meta">#${html(s.code)} · ${html(s.sector)}</span></span><span class="row-value ${s.condition}">${s.bikes==null?'—':display(s.bikes)}<small>${s.condition==='unknown'?'': 'vélos'}</small></span></button>`).join('')+(stations.length>250?'<div class="sidebar-placeholder">Affichage limité à 250 lignes. Affinez la recherche pour trouver d’autres stations.</div>':'');
}
function renderInspector(){
  const box=$('inspector-content');
  if(state.view==='reseau' && state.selected){
    const station=state.stations.find(s=>s.id===state.selected);
    if(station){box.innerHTML=renderStationDetail(station);box.querySelector('[data-back]').onclick=()=>{state.selected=null;renderInspector();repaintMap()};return;}
  }
  if(state.view==='reseau'){
    box.innerHTML=`<div class="panel-search"><div class="search-wrap"><span>⌕</span><input id="station-search" type="search" value="${html(state.query)}" aria-label="Rechercher une station" placeholder="Nom, numéro, identifiant…" autocomplete="off"/></div><div class="list-heading"><span>STATIONS / RÉSULTATS</span><span id="station-results">${display(filtered().length)} stations</span></div></div><div class="station-list" id="station-list">${stationRows(filtered())}</div>`;
    const input=$('station-search');
    input.oninput=()=>{state.query=input.value;$('station-results').textContent=`${display(filtered().length)} stations`;$('station-list').innerHTML=stationRows(filtered());bindStationRows();repaintMap()};
    bindStationRows();return;
  }
  if(state.view==='territoires'){
    const sections=sectorSummaries(state.stations);
    box.innerHTML=`<div class="side-section"><span class="station-kicker">ANALYSE SPATIALE / 04 SECTEURS</span><h3>Une autre lecture du territoire.</h3><p>Découpage analytique en quatre quadrants autour des médianes des coordonnées enregistrées. <strong>Ce ne sont pas des arrondissements administratifs.</strong></p><button class="territory-row ${state.sector==='all'?'selected':''}" data-sector="all"><span>Tout le réseau</span><strong>${display(state.stations.length)}</strong><small>STATIONS RÉFÉRENCÉES</small></button>${sections.map(s=>`<button class="territory-row ${state.sector===s.id?'selected':''}" data-sector="${s.id}"><span>${html(s.name)}</span><strong>${display(s.bikes)} <small>VÉLOS</small></strong><small>${display(s.stations)} stations · ${pct(s.emptyRate)} sans vélo (qualifiées)</small></button>`).join('')}</div>`;
    box.querySelectorAll('[data-sector]').forEach(btn=>btn.onclick=()=>{state.sector=btn.dataset.sector;renderInspector();repaintMap()});return;
  }
  if(state.view==='fiabilite'){
    const m=state.dataset.metrics;
    box.innerHTML=`<div class="side-section"><span class="station-kicker">QUALITÉ / DERNIÈRE CAPTURE</span><h3>Une mesure, pas une promesse.</h3><p>${display(m.usable)} stations qualifiées sur ${display(m.observed)} observations au dernier instant. Les anomalies ci-dessous sont des <strong>signalements de qualité</strong>, pas nécessairement des stations uniques.</p><span class="station-kicker">SIGNALEMENTS PAR CATÉGORIE</span>${state.dataset.issues.length?state.dataset.issues.map(x=>`<div class="quality-row"><span>${html(x.code.replaceAll('_',' '))}</span><strong>${display(x.count)}</strong></div>`).join(''):'<div class="quality-row"><span>Aucun signalement enregistré</span></div>'}<p>Une capture ancienne ne décrit jamais la disponibilité actuelle des vélos.</p></div>`;return;
  }
  if(state.view==='previsions'){
    box.innerHTML='<div class="side-section"><span class="station-kicker">P5 / INTELLIGENCE PRÉDICTIVE</span><div class="p5-icon" aria-hidden="true">◇</div><span class="solid-tag">PRÉVISION NON DISPONIBLE</span><h3>La fiabilité avant la prédiction.</h3><p>Le modèle à +30 minutes est développé, mais il attend un historique réel suffisant et une validation chronologique indépendante. Aucune prévision ni score de performance n’est affiché avant cette validation.</p><div class="detail-meta"><span>Horizon visé</span><strong>+30 minutes</strong></div><div class="detail-meta"><span>Évaluation</span><strong>Baseline vs modèle</strong></div><div class="detail-meta"><span>Statut</span><strong>Non validé</strong></div></div>';
  }
}
function bindStationRows(){
  document.querySelectorAll('[data-station]').forEach(btn=>btn.onclick=()=>selectStation(btn.dataset.station));
}
function renderTimeline() {
  const history=state.dataset.history;
  $('timeline-count').textContent=display(history.length);
  const gaps=history.slice(1).map(x=>x.gap_minutes).filter(Number.isFinite);
  $('timeline-gap').textContent=gaps.length?`${Math.max(...gaps).toLocaleString('fr-FR',{maximumFractionDigits:1})}m`:'—';
  const target=$('timeline-plot');
  if(history.length<2){target.innerHTML='<div class="timeline-empty">Historique insuffisant : une seule capture. Aucune tendance calculable.</div>';return;}
  const valid=history.map(x=>x.bikes);
  const max=Math.max(...valid),min=Math.min(...valid),span=Math.max(max-min,1);
  const first=Date.parse(history[0].at),last=Date.parse(history.at(-1).at),duration=Math.max(last-first,1);
  const W=680,H=94,pad=12;
  const project=(item)=>{
    const x=pad+(W-2*pad)*(Date.parse(item.at)-first)/duration;
    const y=H-pad-(H-2*pad)*(item.bikes-min)/span;
    return [x,y];
  };
  const lines=historySegments(history).map(segment=>{
    if(segment.length<2)return '';
    return `<polyline points="${segment.map(p=>project(p).map(n=>n.toFixed(2)).join(',')).join(' ')}" fill="none" stroke="#91d9b5" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linecap="round" />`;
  }).join('');
  const dots=history.map(p=>{const [x,y]=project(p);return `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="2.8" fill="#bce6cf" stroke="#0a191c" stroke-width="1"><title>${html(localTime(p.at))} · ${display(p.bikes)} vélos qualifiés</title></circle>`}).join('');
  target.innerHTML=`<svg class="timeline-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Vélos qualifiés aux instants de collecte, lignes interrompues lors de lacunes"><line x1="${pad}" x2="${W-pad}" y1="${H/2}" y2="${H/2}" stroke="#355055" stroke-dasharray="2 8"/>${lines}${dots}<text x="${pad}" y="${H-2}" font-size="8" fill="#7b9697">${html(localTime(history[0].at))}</text><text x="${W-pad}" y="${H-2}" text-anchor="end" font-size="8" fill="#7b9697">${html(localTime(history.at(-1).at))}</text></svg>`;
  const missing=gaps.filter(x=>x>20).length;
  $('timeline-explain').textContent=missing?`${missing} interruption(s) de plus de 20 min : courbe volontairement discontinue.`:'Points réels, reliés seulement si l’écart ne dépasse pas 20 min.';
}
function renderAll(){paintStats();updateNav();renderInspector();renderTimeline();repaintMap();}
function activateView(view){
  if(!['reseau','territoires','fiabilite','previsions'].includes(view))return;
  state.view=view;state.selected=null;state.sector='all';updateNav();renderInspector();repaintMap();
}
async function refresh(){
  try {
    // The exported file is intentionally archived and immutable until a fresh CI sync.
    const response=await fetch('./data/network.json',{cache:'no-store'});
    if(!response.ok)throw new Error(`Export P6 introuvable (HTTP ${response.status}).`);
    const dataset=validateDataset(await response.json());
    state.dataset=dataset;state.stations=sectors(dataset.stations);
    state.selected=null;
    $('error-state').hidden=true;
    renderAll();
    if(!state.map&&!state.mapFailed){
      if(document.readyState==='complete')initMap();
      else window.addEventListener('load',initMap,{once:true});
    }
  }catch(error){
    $('error-message').textContent=error.message;
    $('error-state').hidden=false;
    console.error('Urban Ops failed to load verified dataset',error);
  }
}
for(const btn of document.querySelectorAll('.nav'))btn.addEventListener('click',()=>{activateView(btn.dataset.view);history.replaceState(null,'','#'+btn.dataset.view)});
for(const btn of document.querySelectorAll('.filter-pill'))btn.addEventListener('click',()=>{
  state.filter=btn.dataset.filter;document.querySelectorAll('.filter-pill').forEach(el=>el.classList.toggle('active',el===btn));
  state.selected=null;renderInspector();repaintMap();
});
$('reload').addEventListener('click',refresh);
const hash=location.hash.slice(1);if(['reseau','territoires','fiabilite','previsions'].includes(hash))state.view=hash;
refresh();