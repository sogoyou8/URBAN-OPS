import { STATUS, validateDataset, selectStations, bounds, sectors, sectorSummaries, summary,
         historySegments, assessHistory, relativeAge, captureFreshness, html, display, pct, localTime,
         layoutMapMarkers, pickMapMarker, viewportCounts, issueLabel, p5Gate, qualityReasons } from './core.js';

const $ = id => document.getElementById(id);
const COLORS = {available:'#94dabb',empty:'#efac84',unknown:'#78919c'};
const state = { dataset:null, stations:[], view:'reseau', query:'', filter:'all', sector:'all', selected:null,
                map:null, mapReady:false, mapFailed:false, markerCanvas:null, markerPositions:[], clusterIds:null };


const GUIDE_CONTEXT={
  reseau:['Réseau','Cliquez sur une station pour voir les vélos disponibles, les bornes libres et la date du dernier relevé.'],
  territoires:['Territoires','Comparez les disponibilités dans quatre zones du réseau. Ce ne sont pas les arrondissements de Paris.'],
  fiabilite:['Fiabilité','Découvrez les stations dont les chiffres manquent ou ne peuvent pas être utilisés.'],
  previsions:['Prévisions','Les prévisions à 30 minutes sont en préparation. Pour l'instant, cette section montre les données déjà rassemblées.']
};
let guideReturnFocus=null;
function updateGuideContext(){
  const [title,body]=GUIDE_CONTEXT[state.view];
  $('guide-context-title').textContent=title;
  $('guide-context-text').textContent=body;
}
function openGuide(){
  if(!$('understand-dialog').hidden)return;
  guideReturnFocus=document.activeElement;
  updateGuideContext();
  $('understand-dialog').hidden=false;
  document.querySelector('.shell').inert=true;
  $('open-guide').setAttribute('aria-expanded','true');
  $('close-guide').focus();
}
function closeGuide(){
  if($('understand-dialog').hidden)return;
  $('understand-dialog').hidden=true;
  document.querySelector('.shell').inert=false;
  $('open-guide').setAttribute('aria-expanded','false');
  (guideReturnFocus&&guideReturnFocus.isConnected?guideReturnFocus:$('open-guide')).focus();
}
function trapGuideFocus(event){
  if($('understand-dialog').hidden)return false;
  if(event.key==='Escape'){event.preventDefault();closeGuide();return true;}
  if(event.key!=='Tab')return false;
  const focusables=[...$('understand-dialog').querySelectorAll('a[href],button:not([disabled])')]
    .filter(el=>el.getClientRects().length>0);
  if(!focusables.length)return false;
  const first=focusables[0],last=focusables.at(-1);
  if(event.shiftKey&&(document.activeElement===first||!$('understand-dialog').contains(document.activeElement))){
    event.preventDefault();last.focus();
  }else if(!event.shiftKey&&(document.activeElement===last||!$('understand-dialog').contains(document.activeElement))){
    event.preventDefault();first.focus();
  }
  return true;
}

function updateFreshness() {
  if(!state.dataset)return;
  const at=state.dataset.captured_at;
  const recent=captureFreshness(at);
  const truth=document.querySelector('.truth');
  truth.classList.toggle('good',recent==='recent');
  $('freshness-label').textContent=recent==='recent'?'CAPTURE RÉCENTE':recent==='aging'?'ARCHIVE EN DIFFÉRÉ':'ARCHIVE ANCIENNE';
  $('capture-time').textContent=`Capture : ${localTime(at)} · il y a ${relativeAge(at)}`;
  $('top-capture').textContent=`ARCHIVE ${localTime(at)}`;
  document.querySelector('.signal').classList.toggle('stale',recent==='stale');
  $('reload').title='Relire le fichier de données archivé (ne lance aucune collecte Vélib’)';
}
function paintStats() {
  const d=state.dataset, m=d.metrics;
  const qualified=summary(state.sector==='all'?state.stations:state.stations.filter(s=>s.sector===state.sector));
  const issues=d.issues.reduce((n,i)=>n+i.count,0);
  const ml=p5Gate(d);
  const values={
    reseau:[
      ['STATIONS DU RÉSEAU',display(m.stations),'dans le réseau Vélib’'],
      ['VÉLOS DISPONIBLES',display(m.bikes),'dans les stations avec données utilisables'],
      ['STATIONS SANS VÉLO',display(m.empty),`${pct(m.usable?m.empty/m.usable:null)} des ${display(m.usable)} stations qualifiées`],
      ['STATIONS AVEC DONNÉES FIABLES',display(m.usable),`${display(m.unusable)} observations non exploitables`],
    ],
    territoires:[
      ['ZONES COMPARÉES', '4', '4 zones du réseau, pas des arrondissements'],
      ['VÉLOS COMPTÉS',display(qualified.bikes),'dans la zone choisie'],
      ['STATIONS SANS VÉLO',display(qualified.empty),`${pct(qualified.emptyRate)} des stations qualifiées`],
      ['STATIONS AVEC DONNÉES FIABLES',display(qualified.usable),`${display(qualified.stations)} stations dans le périmètre`],
    ],
    fiabilite:[
      ['STATIONS AVEC DONNÉES FIABLES',display(m.usable),`${pct(m.observed?m.usable/m.observed:null)} des observations`],
      ['DONNÉES INUTILISABLES',display(m.unusable),'chiffres reçus, mais non utilisables'],
      ['SIGNALEMENTS QUALITÉ',display(issues),'une station peut avoir plusieurs alertes'],
      ['CAPTURES HISTORIQUES',display(m.capture_count),'captures utilisées pour cet écran'],
    ],
    previsions:[
      ['PRÉVISION PRÉVUE','30 min','disponibilité estimée dans 30 minutes'],
      ['CAPTURES RECENSÉES',ml.available?display(ml.captures):'—','captures recensées, à vérifier avant prévision'],
      ['JOURS DE DONNÉES',ml.available?String(ml.days.toLocaleString('fr-FR',{maximumFractionDigits:1})):'—','7 jours minimum nécessaires'],
      ['FIABILITÉ DES PRÉVISIONS','—','pas encore mesurée'],
    ],
  }[state.view];
  const nodes=document.querySelectorAll('.metric');
  values.forEach(([label,value,foot],i)=>{
    nodes[i].querySelector('.metric-label').textContent=label;
    nodes[i].querySelector('.metric-figure').textContent=value;
    nodes[i].querySelector('.metric-foot').textContent=foot;
  });
  updateFreshness();
}
function filtered() {
  return selectStations(state.stations,{query:state.query,filter:state.filter,sector:state.sector});
}
function setViewportCount(filteredCount, markers, fallback=false){
  const counts=viewportCounts(filteredCount,markers);
  const label=`${display(counts.filtered)} filtrées · ${display(counts.visible)} visibles · ${display(counts.markers)} repères`;
  const el=$('map-count');
  el.textContent=label;
  el.dataset.filtered=String(counts.filtered);
  el.dataset.visible=String(counts.visible);
  el.dataset.markers=String(counts.markers);
  el.title=`${counts.filtered} stations correspondant aux filtres dans tout le réseau ; ${counts.visible} stations réellement dans la zone cartographique affichée ; ${counts.markers} repères dessinés, dont ${counts.clusters} regroupements.${fallback?' Mode de secours sans fond cartographique.':''}`;
}
function syncFilterButtons(){
  for(const pill of document.querySelectorAll('.filter-pill')){
    const active=pill.dataset.filter===state.filter;
    pill.classList.toggle('active',active);
    pill.setAttribute('aria-pressed',String(active));
  }
}
function resetInspectorScroll(){
  const inspector=$('inspector-content');
  inspector.scrollTop=0;
  inspector.querySelectorAll('.station-list').forEach(list=>{list.scrollTop=0});
}
function fitNetworkMap(){
  if(!state.mapReady || !state.map || !state.stations.length)return;
  const area=bounds(state.stations);
  state.map.fitBounds([[area.west,area.south],[area.east,area.north]],{
    padding:42,maxZoom:11.5,duration:450
  });
}
function repaintMap() {
  const stations=filtered();
  const suffix=state.mapReady?'STATIONS GÉOLOCALISÉES':state.mapFailed?'STATIONS EN MODE DE SECOURS':'STATIONS À POSITIONNER';
  $('map-count').textContent=`${display(stations.length)} ${suffix}`;
  if(state.mapReady && state.map){
    drawMapMarkers();
  } else if(state.mapFailed){
    fallbackMap(stations);
  }
}
function fallbackMap(points) {
  $('map').hidden=true;
  if(state.markerCanvas)state.markerCanvas.hidden=true;
  const surface=$('map-fallback');surface.hidden=false;
  const full=bounds(state.stations),pad=.05;
  const west=full.west-(full.east-full.west)*pad;
  const east=full.east+(full.west===full.east?0.01:full.east-full.west)*pad;
  const south=full.south-(full.north-full.south)*pad;
  const north=full.north+(full.south===full.north?0.01:full.north-full.south)*pad;
  const w=Math.max(1,surface.clientWidth),h=Math.max(1,surface.clientHeight);
  // The fallback has no vector tiles or zoom control. It must still cluster
  // the actual geographic positions; 1500 overlapping 7px DOM buttons are not
  // a readable or keyboard-friendly substitute for a basemap.
  const project=([lon,lat])=>({
    x:w*(lon-west)/(east-west),
    y:h*(north-lat)/(north-south),
  });
  const markers=layoutMapMarkers(points,project,w,h,11,state.selected);
  surface.replaceChildren();
  const label=document.createElement('span');
  label.className='fallback-caption';
  label.textContent='PLAN SCHÉMATIQUE · MODE SANS TUILES';
  surface.append(label);
  const byId=new Map(points.map(p=>[p.id,p]));
  const frag=document.createDocumentFragment();
  for(const mark of markers){
    const clustered=mark.count>1;
    const station=clustered?null:byId.get(mark.ids[0]);
    const point=document.createElement('button');
    point.type='button';
    point.className='fallback-point '+mark.condition+(clustered?' cluster':'');
    point.style.left=(100*mark.x/w).toFixed(3)+'%';
    point.style.top=(100*mark.y/h).toFixed(3)+'%';
    point.title=clustered?`${mark.count} stations proches`:station?.name||'Station';
    point.setAttribute('aria-label',clustered
      ?`Explorer le regroupement de ${mark.count} stations proches`
      :`Inspecter ${station?.name||'la station'}`);
    if(clustered){
      point.textContent=String(mark.count);
      point.addEventListener('click',()=>{
        state.view='reseau';state.selected=null;state.clusterIds=mark.ids;
        history.replaceState(null,'','#reseau');
        updateNav();paintStats();renderInspector();resetInspectorScroll();
        $('inspector-content').querySelector('[data-dismiss-cluster]')?.focus({preventScroll:true});
      });
    }else{
      point.addEventListener('click',()=>selectStation(mark.ids[0]));
    }
    frag.append(point);
  }
  surface.append(frag);
  setViewportCount(points.length,markers,true);
}
function mapFallback() {
  if(state.mapFailed)return;
  state.mapFailed=true;
  try{state.map?.remove()}catch(_){/* safer than a blank map */}
  state.map=null;state.mapReady=false;state.markerPositions=[];
  fallbackMap(filtered());repaintMap();
}
function drawMapMarkers(){
  if(!state.map||!state.mapReady)return;
  try{
    const container=$('map'),w=container.clientWidth,h=container.clientHeight;
    if(w<=0||h<=0)return;
    if(!state.markerCanvas){
      const canvas=document.createElement('canvas');
      canvas.id='station-overlay';canvas.className='station-overlay';
      canvas.setAttribute('aria-hidden','true');container.parentElement.append(canvas);
      state.markerCanvas=canvas;
    }
    const canvas=state.markerCanvas;
    const pixelRatio=Math.min(window.devicePixelRatio||1,2);
    canvas.width=Math.round(w*pixelRatio);canvas.height=Math.round(h*pixelRatio);
    canvas.style.width=w+'px';canvas.style.height=h+'px';
    const ctx=canvas.getContext('2d');
    if(!ctx){mapFallback();return;}
    ctx.setTransform(pixelRatio,0,0,pixelRatio,0,0);
    ctx.clearRect(0,0,w,h);
    const stations=filtered();
    const markers=layoutMapMarkers(stations,pos=>state.map.project(pos),
      w,h,state.map.getZoom(),state.selected);
    state.markerPositions=markers;
    for(const p of markers){
      const clustered=p.count>1;
      const radius=p.selected?9:clustered?Math.min(17,8+Math.log2(p.count)*2):4.4;
      const color=COLORS[p.condition];
      ctx.beginPath();ctx.arc(p.x,p.y,radius,0,Math.PI*2);
      ctx.fillStyle=clustered?'#183a39':color;ctx.globalAlpha=.96;ctx.fill();
      ctx.lineWidth=p.selected?2.7:clustered?1.5:1.25;
      ctx.strokeStyle=p.selected?'#ffffff':clustered?'#a8edc7':'#031319';ctx.stroke();
      if(clustered){
        ctx.globalAlpha=1;ctx.fillStyle='#e9fff4';ctx.font='600 10px system-ui';
        ctx.textAlign='center';ctx.textBaseline='middle';
        ctx.fillText(String(p.count),p.x,p.y);
      }
    }
    ctx.globalAlpha=1;
    setViewportCount(stations.length,markers);
  }catch(error){
    console.warn('La superposition cartographique a échoué',error);
    mapFallback();
  }
}
function initMap() {
  const maplibre=window.maplibregl;
  if(!maplibre){mapFallback();return;}
  try{
    const map=new maplibre.Map({
      container:'map',style:'https://tiles.openfreemap.org/styles/dark',
      center:[2.348,48.856],zoom:11,attributionControl:false,pitchWithRotate:false,
      dragRotate:false,cooperativeGestures:false,
    });
    state.map=map;
    map.addControl(new maplibre.NavigationControl({showCompass:false}),'bottom-right');
    // Markers are drawn independently from MapLibre style sources and tiles.
    // A working basemap no longer hides stations when a style layer fails.
    map.on('load',()=>{
      if(state.mapFailed)return;
      state.mapReady=true;
      drawMapMarkers();
      repaintMap();
    });
    map.on('move',()=>{if(state.mapReady)drawMapMarkers()});
    map.on('resize',()=>{if(state.mapReady)drawMapMarkers()});
    map.on('click',evt=>{
      if(!state.mapReady)return;
      const p=pickMapMarker(state.markerPositions,evt.point.x,evt.point.y);
      if(!p)return;
      if(p.count>1){
        if(map.getZoom()>=16.4){
          state.view='reseau';state.selected=null;state.clusterIds=p.ids;
          state.query='';state.filter='all';state.sector='all';
          syncFilterButtons();
          history.replaceState(null,'','#reseau');
          updateNav();paintStats();renderInspector();repaintMap();
        } else {
          map.easeTo({center:[p.lon,p.lat],zoom:Math.min(17,map.getZoom()+2),duration:550});
        }
      }else if(p.ids[0])selectStation(p.ids[0]);
    });
    map.on('mousemove',evt=>{
      if(!state.mapReady)return;
      const p=pickMapMarker(state.markerPositions,evt.point.x,evt.point.y);
      map.getCanvas().style.cursor=p?'pointer':'grab';
    });
    map.on('error',event=>{
      if(!state.mapReady)console.warn('Style en cours de chargement',event.error?.message||'erreur tuiles');
    });
    window.addEventListener('resize',()=>{if(state.mapReady){map.resize();drawMapMarkers()}});
    setTimeout(()=>{if(!state.mapReady&&!state.mapFailed)mapFallback()},9000);
  }catch(error){console.warn('MapLibre indisponible',error);mapFallback();}
}
function focusStation(station) {
  if(state.mapReady&&state.map) state.map.flyTo({center:[station.lon,station.lat],zoom:Math.max(state.map.getZoom(),14),essential:true});
}
function selectStation(id) {
  const station=state.stations.find(s=>s.id===id);
  if(!station)return;
  state.selected=station.id;state.clusterIds=null;state.view='reseau';state.sector='all';
  // Preserve search/filter context when following a result into its detail.
  history.replaceState(null,'','#reseau');
  updateNav();paintStats();renderInspector();resetInspectorScroll();repaintMap();focusStation(station);
  // The clicked list row was replaced: move keyboard focus to the usable back control.
  $('inspector-content').querySelector('[data-back]')?.focus({preventScroll:true});
}
function updateNav() {
  for(const nav of document.querySelectorAll('.nav')){
    const active=nav.dataset.view===state.view;
    nav.classList.toggle('active',active);
    nav.setAttribute('aria-current',active?'page':'false');
    nav.setAttribute('aria-pressed',String(active));
  }
  const views={
    reseau:['01 / 04','Le pouls du réseau.','Explorez les stations Vélib’, leur disponibilité observée et les bornes libres.','Disponibilité par station'],
    territoires:['02 / 04','Comparer les secteurs.','Comparez les vélos disponibles dans quatre zones du réseau.','Répartition géographique'],
    fiabilite:['03 / 04','Des données à vérifier.','Repérez les stations dont les chiffres sont disponibles ou manquants.','Stations et qualité des mesures'],
    previsions:['04 / 04','Prévisions en préparation.','Les prévisions à 30 minutes seront affichées après vérification de leur fiabilité.','Prévisions / en attente'],
  };
  const [index,title,description,maptitle]=views[state.view];
  document.querySelector('.index').textContent=index;
  $('headline-title').innerHTML=html(title.slice(0,-1))+'<span class="period">.</span>';
  $('headline-description').textContent=description;
  $('map-title').textContent=maptitle;
  updateGuideContext();
  document.querySelector('.workspace').dataset.view=state.view;
  $('panel-state').textContent=state.view==='previsions'?'EN PRÉPARATION':state.view==='fiabilite'?'CONTRÔLE':state.view==='territoires'?'COMPARAISON':'EXPLORATION';
  $('timeline-heading').textContent=state.view==='fiabilite'?'Historique des vélos':
    state.view==='territoires'?'Historique des vélos':
    state.view==='previsions'?'Historique des vélos':'Historique des vélos';
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
    <div class="station-quality">
      <span class="station-kicker">QUALITÉ DE L’OBSERVATION ARCHIVÉE</span>
      <ul>${qualityReasons(station).map(reason=>`<li>${html(reason)}</li>`).join('')}</ul>
      ${station.lag_seconds!==null && station.lag_seconds!==undefined ? `<p>Retard du dernier signal : ${display(station.lag_seconds)} secondes</p>`:''}
    </div>
    <p class="detail-disclaimer" style="margin-top:18px;font-size:11px;color:var(--muted);line-height:1.6">Ces valeurs proviennent d’une capture archivée, et non d'une consultation en temps réel.</p>
  </div>`;
}
function stationRows(stations) {
  if(!stations.length)return '<div class="sidebar-placeholder">Aucune station ne correspond aux filtres.</div>';
  return stations.slice(0,250).map((s,i)=>`<button class="station-row ${s.id===state.selected?'selected':''}" type="button" data-station="${html(s.id)}" aria-label="Afficher la station ${html(s.name)}"><span class="row-count">${String(i+1).padStart(2,'0')}</span><span class="row-info"><span class="row-name">${html(s.name)}</span><span class="row-meta">#${html(s.code)} · ${html(s.sector)}</span></span><span class="row-value ${s.condition}">${s.bikes==null?'—':display(s.bikes)}<small>${s.condition==='unknown'?'': 'vélos'}</small></span></button>`).join('')+(stations.length>250?'<div class="sidebar-placeholder">Affichage limité à 250 lignes. Affinez la recherche pour trouver d’autres stations.</div>':'');
}
function renderInspector(){
  const box=$('inspector-content');
  if(state.view==='reseau' && state.clusterIds?.length){
    const stations=state.clusterIds.map(id=>state.stations.find(s=>s.id===id)).filter(Boolean);
    box.innerHTML=`<div class="cluster-picker">
      <button type="button" class="back-btn" data-dismiss-cluster>← TOUTES LES STATIONS</button>
      <span class="station-kicker">REPÈRE GÉOGRAPHIQUE / REGROUPEMENT</span>
      <h3>${display(stations.length)} stations à cet emplacement</h3>
      <p>Les stations restent géographiquement rapprochées. Choisis une station pour ouvrir sa fiche.</p>
    </div><div class="station-list">${stationRows(stations)}</div>`;
    box.querySelector('[data-dismiss-cluster]').onclick=()=>{state.clusterIds=null;renderInspector();resetInspectorScroll();repaintMap()};
    bindStationRows();return;
  }
  if(state.view==='reseau' && state.selected){
    const station=state.stations.find(s=>s.id===state.selected);
    if(station){
      box.innerHTML=renderStationDetail(station);
      box.querySelector('[data-back]').onclick=()=>{
        const previous=state.selected;
        state.selected=null;renderInspector();resetInspectorScroll();repaintMap();
        const row=[...document.querySelectorAll('[data-station]')].find(el=>el.dataset.station===previous);
        (row||$('station-search'))?.focus({preventScroll:true});
      };
      return;
    }
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
    box.querySelectorAll('[data-sector]').forEach(btn=>btn.onclick=()=>{state.sector=btn.dataset.sector;renderInspector();paintStats();repaintMap();
      const points=filtered();if(state.mapReady&&state.map&&points.length){
        const bb=bounds(points);state.map.fitBounds([[bb.west,bb.south],[bb.east,bb.north]],{padding:42,maxZoom:13,duration:450});
      }});return;
  }
  if(state.view==='fiabilite'){
    const m=state.dataset.metrics,q=state.dataset.quality_diagnostics;
    const unobserved=q?.not_observed,unusable=q?.observed_but_unusable;
    box.innerHTML=`<div class="side-section quality-audit">
      <span class="station-kicker">AUDIT / DERNIÈRE CAPTURE ARCHIVÉE</span>
      <h3>Pourquoi des observations sont rejetées.</h3>
      <p>Une station <strong>sans statut</strong> n’est pas une station sans vélo. Une station observée mais non exploitable reste exclue des sommes.</p>
      <div class="quality-overview">
        <div><strong>${unobserved==null?'—':display(unobserved)}</strong><span>stations sans observation</span></div>
        <div><strong>${unusable==null?'—':display(unusable)}</strong><span>observations reçues, non exploitables</span></div>
        <div><strong>${q?.observed_non_operational==null?'—':display(q.observed_non_operational)}</strong><span>stations au service interrompu (peut chevaucher d'autres motifs)</span></div>
      </div>
      <button class="quality-open-list" type="button" id="inspect-unqualified">Inspecter les ${display(state.stations.filter(s=>!s.usable).length)} stations non qualifiées ↗</button>
      <span class="station-kicker">SIGNALEMENTS DANS LA CAPTURE / ÉVÉNEMENTS</span>
      ${state.dataset.issues.length?state.dataset.issues.map(x=>`<div class="quality-row"><span>${html(issueLabel(x.code))}</span><strong>${display(x.count)}</strong></div>`).join(''):'<div class="quality-row"><span>Aucun signalement enregistré</span></div>'}
      <p>Un signalement ne correspond pas nécessairement à une station unique, plusieurs motifs peuvent se cumuler. Aucun comptage de trajets ni réparation de valeurs manquantes.</p>
    </div>`;
    $('inspect-unqualified').onclick=()=>{
      state.view='reseau';state.sector='all';state.selected=null;state.clusterIds=null;
      state.query='';state.filter='unknown';
      syncFilterButtons();
      history.replaceState(null,'','#reseau');
      updateNav();paintStats();renderInspector();resetInspectorScroll();repaintMap();
    };
    return;
  }
  if(state.view==='previsions'){
    const gate=p5Gate(state.dataset);
    const n=gate.available?gate.captures:null;
    const days=gate.available?gate.days:null;
    const coverage=gate.coverage;
    const progress=(value,target)=>value===null?'—':pct(Math.min(1,value/target));
    box.innerHTML=`<div class="side-section forecast-readiness">
      <span class="station-kicker">P5 / CONDITIONS D’ENTRAÎNEMENT</span>
      <span class="solid-tag">PRÉVISION NON DISPONIBLE</span>
      <h3>Des preuves avant le modèle.</h3>
      <p>Ce compteur lit les <strong>noms des archives GitHub sur 10 jours</strong>. Il ne garantit pas leurs sommes de contrôle, ni l’existence de paires valides à +30 minutes, ni la qualité prédictive.</p>
      <div class="p5-progress">
        <div class="p5-progress-row"><span>Captures recensées</span><strong>${n===null?'Indisponible':`${display(n)} / 900`}</strong><small>${progress(n,900)} du seuil de quantité</small><progress max="900" value="${n===null?0:Math.min(n,900)}"></progress></div>
        <div class="p5-progress-row"><span>Étendue historique</span><strong>${days===null?'Indisponible':`${days.toLocaleString('fr-FR',{maximumFractionDigits:2})} / 7 jours`}</strong><small>${progress(days,7)} du seuil calendaire</small><progress max="7" value="${days===null?0:Math.min(days,7)}"></progress></div>
        <div class="p5-progress-row"><span>Couverture indicative</span><strong>${coverage===null?'Non mesurable':`${pct(coverage)} / 40 %`}</strong><small>Calculée entre les premières et dernières archives recensées</small><progress max="0.4" value="${coverage===null?0:Math.min(coverage,0.4)}"></progress></div>
      </div>
      <div class="detail-meta"><span>Historique</span><strong>${!gate.available?'Indisponible':gate.eligible?'Seuils atteints, à vérifier':'Seuils non atteints'}</strong></div>
      <div class="detail-meta"><span>Paires futures +30 min</span><strong>Non vérifiées ici</strong></div>
      <div class="detail-meta"><span>Évaluation ML vs baseline</span><strong>Non validée</strong></div>
      <p class="readiness-note">${gate.checkedAt?'Inventaire vérifié le '+html(localTime(gate.checkedAt)):'Inventaire GitHub non joint à cet export. Lance une nouvelle exportation P6.'} · Aucune prévision ne sera affichée avant une validation P5 indépendante.</p>
    </div>`;
  }
}
function bindStationRows(){
  document.querySelectorAll('[data-station]').forEach(btn=>btn.onclick=()=>selectStation(btn.dataset.station));
}

function renderTimeline() {
  const history=state.dataset.history;
  $('timeline-count').textContent=display(history.length);
  const gaps=history.slice(1).map(x=>x.gap_minutes).filter(Number.isFinite);
  $('timeline-gap').textContent=gaps.length?`${Math.max(...gaps).toLocaleString('fr-FR',{maximumFractionDigits:1})} min`:'—';
  const target=$('timeline-plot');
  const assessment=assessHistory(history,state.dataset.metrics.stations);
  $('timeline-quality').textContent=assessment.unknownCount?'—':display(assessment.reducedCount);
  $('timeline-quality').title=assessment.unknownCount?'Couverture non mesurable pour certains points':
    `${assessment.reducedCount} relevés avec moins de 90 % de la meilleure couverture de la fenêtre`;
  const valid=assessment.points.filter(p=>Number.isFinite(p.bikes)&&p.bikes>=0&&Number.isFinite(Date.parse(p.at)));
  if(valid.length<2){
    target.innerHTML='<div class="timeline-empty">Historique insuffisant : moins de deux captures utilisables. Aucune tendance calculable.</div>';
    $('timeline-explain').textContent='Les valeurs manquantes ne sont jamais remplacées par zéro.';
    return;
  }
  // Avoid the misleading impression that historical totals plunge towards zero:
  // the axis is explicitly anchored at zero rather than at the sample minimum.
  const max=Math.max(...valid.map(p=>p.bikes)),ceiling=Math.max(1000,Math.ceil(max/2000)*2000);
  const first=Date.parse(valid[0].at),last=Date.parse(valid.at(-1).at),duration=Math.max(1,last-first);
  const W=680,H=94,left=43,right=12,top=10,bottom=65;
  const xy=p=>[left+(W-left-right)*(Date.parse(p.at)-first)/duration,
                bottom-(bottom-top)*p.bikes/ceiling];
  const lines=historySegments(assessment.points).map(segment=>{
    const pts=segment.filter(p=>Number.isFinite(p.bikes)&&p.bikes>=0);
    return pts.length<2?'':`<polyline points="${pts.map(p=>xy(p).map(n=>n.toFixed(2)).join(',')).join(' ')}" fill="none" stroke="#91d9b5" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linecap="round"/>`;
  }).join('');
  const dots=valid.map(p=>{
    const [x,y]=xy(p);
    const color=p.status==='reduced'?'#f5b17c':p.status==='unknown'?'#899fac':'#bce6cf';
    const cover=p.catalogRatio===null?'Couverture inconnue':`${display(p.usable)} / ${display(state.dataset.metrics.stations)} stations exploitables (${pct(p.catalogRatio)})`;
    const reason=p.status==='reduced'?' · couverture réduite, total non comparable':
      p.status==='unknown'?' · comparabilité inconnue':' · couverture comparable';
    return `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${p.status==='reduced'?3.8:2.6}" fill="${color}" stroke="#0a191c" stroke-width="1"><title>${html(localTime(p.at))} · ${display(p.bikes)} vélos comptabilisés · ${html(cover+reason)}</title></circle>`;
  }).join('');
  // Second reading on the same time axis: coverage of usable station observations.
  const coverageDots=valid.filter(p=>p.catalogRatio!==null).map(p=>{
    const x=xy(p)[0],y=77+7*(1-p.catalogRatio);
    const color=p.status==='reduced'?'#f5b17c':'#73a9c9';
    return `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="2" fill="${color}"><title>${html(localTime(p.at))} · ${display(p.usable)} stations exploitables sur ${display(state.dataset.metrics.stations)}</title></circle>`;
  }).join('');
  target.innerHTML=`<svg class="timeline-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Vélos observés sur une échelle démarrant à zéro. Orange : couverture réduite. Trait bleu inférieur : stations exploitables.">
    <line x1="${left}" x2="${W-right}" y1="${bottom}" y2="${bottom}" stroke="#4a6767"/>
    <line x1="${left}" x2="${W-right}" y1="${top}" y2="${top}" stroke="#355055" stroke-dasharray="2 6"/>
    <text x="${left-5}" y="${top+3}" font-size="9" text-anchor="end" fill="#b5ced0">${display(ceiling)}</text>
    <text x="${left-5}" y="${bottom+3}" font-size="9" text-anchor="end" fill="#b5ced0">0</text>
    ${lines}${dots}
    <line x1="${left}" x2="${W-right}" y1="80" y2="80" stroke="#264a5a"/>${coverageDots}
    <text x="${left}" y="${H-1}" font-size="8" fill="#9fbec1">${html(localTime(valid[0].at))}</text>
    <text x="${W-right}" y="${H-1}" font-size="8" text-anchor="end" fill="#9fbec1">${html(localTime(valid.at(-1).at))}</text>
  </svg>`;
  const gapCount=gaps.filter(x=>x>20).length,notes=[];
  if(assessment.reducedCount)notes.push(`${assessment.reducedCount} relevé(s) à couverture réduite (orange)`);
  if(gapCount)notes.push(`${gapCount} lacune(s) de plus de 20 min`);
  if(assessment.unknownCount)notes.push('couverture non mesurable pour certains relevés');
  $('timeline-explain').textContent=notes.length?notes.join(' · ')+'.':
    'Échelle à zéro · points réels · bande bleue : stations exploitables.';
}

function renderAll(){updateNav();syncFilterButtons();paintStats();renderInspector();renderTimeline();repaintMap();}
function activateView(view){
  if(!['reseau','territoires','fiabilite','previsions'].includes(view))return;
  if(state.view===view)return; // Reclicking the active tab preserves ongoing exploration.
  state.view=view;state.selected=null;state.clusterIds=null;state.sector='all';state.query='';state.filter='all';
  syncFilterButtons();
  updateNav();paintStats();renderInspector();resetInspectorScroll();renderTimeline();repaintMap();
  fitNetworkMap();
}
async function refresh(){
  const reload=$('reload'),retry=$('retry-data');
  reload.disabled=true;
  if(retry)retry.disabled=true;
  $('reload').setAttribute('aria-busy','true');
  try {
    // The exported file is intentionally archived and immutable until a fresh CI sync.
    const response=await fetch('./data/network.json',{cache:'no-store'});
    if(!response.ok)throw new Error(`Export P6 introuvable (HTTP ${response.status}).`);
    const dataset=validateDataset(await response.json());
    state.dataset=dataset;state.stations=sectors(dataset.stations);
    state.selected=null;state.clusterIds=null;
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
  }finally{
    reload.disabled=false;
    if(retry)retry.disabled=false;
    reload.removeAttribute('aria-busy');
  }
}
for(const btn of document.querySelectorAll('.nav'))btn.addEventListener('click',()=>{activateView(btn.dataset.view);history.replaceState(null,'','#'+btn.dataset.view)});
for(const btn of document.querySelectorAll('.filter-pill'))btn.addEventListener('click',()=>{
  state.filter=btn.dataset.filter;syncFilterButtons();
  state.selected=null;state.clusterIds=null;renderInspector();resetInspectorScroll();repaintMap();
});
$('open-guide').addEventListener('click',openGuide);
$('close-guide').addEventListener('click',closeGuide);
$('understand-dialog').querySelector('[data-guide-close="backdrop"]').addEventListener('click',closeGuide);
$('reload').addEventListener('click',refresh);
window.addEventListener('resize',()=>{
  if(state.mapFailed&&state.dataset)fallbackMap(filtered());
});
$('retry-data').addEventListener('click',refresh);
// Re-evaluate the displayed age; never fetch new Vélib data behind the user's back.
setInterval(updateFreshness,60_000);
const hash=location.hash.slice(1);if(['reseau','territoires','fiabilite','previsions'].includes(hash))state.view=hash;
refresh();
window.addEventListener('hashchange',()=>{
  const requested=location.hash.slice(1);
  if(['reseau','territoires','fiabilite','previsions'].includes(requested))activateView(requested);
});

$('map-reset').addEventListener('click',()=>{
  state.selected=null;state.clusterIds=null;
  if(state.mapReady&&state.map)fitNetworkMap();
  renderInspector();resetInspectorScroll();repaintMap();
});
document.addEventListener('keydown',event=>{
  if(!$('understand-dialog').hidden){trapGuideFocus(event);return;}
  if(event.key==='Escape' && (state.selected || state.clusterIds)){
    const previous=state.selected;
    state.selected=null;state.clusterIds=null;renderInspector();resetInspectorScroll();repaintMap();
    const row=[...document.querySelectorAll('[data-station]')].find(el=>el.dataset.station===previous);
    (row||$('station-search'))?.focus({preventScroll:true});
  }
});
