/** P6 pure selectors — no generated statistics, only dataset transformations. */
export const STATUS = Object.freeze({available:'Disponible', empty:'Sans vélo', unknown:'Non qualifiée'});

export function validateDataset(raw) {
  if (!raw || raw.schema_version !== 1 || raw.dataset_type !== 'archived_p3_observations' ||
      !raw.run_id || !Number.isFinite(Date.parse(raw.captured_at)) ||
      !Array.isArray(raw.stations) || !Array.isArray(raw.history) || !Array.isArray(raw.issues) ||
      !raw.metrics || raw.stations.length !== raw.metrics.stations) {
    throw new Error('Le fichier de données P6 est absent, incomplet ou incompatible.');
  }
  if (raw.stations.some(s=> !Number.isFinite(s.lat) || !Number.isFinite(s.lon) ||
      s.lat < -90 || s.lat > 90 || s.lon < -180 || s.lon > 180 ||
      !['available','empty','unknown'].includes(s.condition) ||
      (s.condition === 'unknown' && s.bikes !== null))) {
    throw new Error('Le fichier contient des coordonnées ou valeurs de stations invalides.');
  }
  if (raw.forecast?.status !== 'unavailable') {
    throw new Error('Les prévisions ne sont pas validées pour affichage dans ce cockpit.');
  }
  return raw;
}

export function selectStations(stations, { query='', filter='all', sector='all' }={}) {
  const q=query.trim().toLocaleLowerCase('fr-FR');
  return stations.filter(station=> {
    if (filter !== 'all' && station.condition !== filter) return false;
    if (sector !== 'all' && station.sector !== sector) return false;
    if (q && !`${station.name} ${station.code} ${station.id}`.toLocaleLowerCase('fr-FR').includes(q)) return false;
    return true;
  });
}
export function bounds(stations) {
  const good=stations.filter(s=>Number.isFinite(s.lat)&&Number.isFinite(s.lon));
  if (!good.length) return {west:2.1,east:2.55,south:48.72,north:48.97};
  let west=Infinity,east=-Infinity,south=Infinity,north=-Infinity;
  for (const s of good) {west=Math.min(west,s.lon);east=Math.max(east,s.lon);south=Math.min(south,s.lat);north=Math.max(north,s.lat);}
  return {west,east,south,north};
}
export function sectors(stations) {
  const sortedLat=stations.map(s=>s.lat).filter(Number.isFinite).sort((a,b)=>a-b);
  const sortedLon=stations.map(s=>s.lon).filter(Number.isFinite).sort((a,b)=>a-b);
  const mid=a=>a.length?a[Math.floor(a.length/2)]:0;
  const lat=mid(sortedLat),lon=mid(sortedLon);
  return stations.map(s=>({ ...s,sector:(s.lat>=lat?'N':'S')+(s.lon>=lon?'E':'O') }));
}
export function sectorSummaries(stations) {
  const names={NO:'Nord-Ouest',NE:'Nord-Est',SO:'Sud-Ouest',SE:'Sud-Est'};
  return Object.entries(names).map(([id,name])=> {
    const items=stations.filter(s=>s.sector===id);
    const qualified=items.filter(s=>s.usable);
    return {id,name,stations:items.length,qualified:qualified.length,
      bikes:qualified.reduce((n,s)=>n+s.bikes,0),
      empty:qualified.filter(s=>s.bikes===0).length,
      emptyRate:qualified.length?qualified.filter(s=>s.bikes===0).length/qualified.length:null};
  });
}
export function summary(stations) {
  const eligible=stations.filter(s=>s.usable);
  return {stations:stations.length,usable:eligible.length,empty:eligible.filter(s=>s.bikes===0).length,
    bikes:eligible.reduce((n,s)=>n+s.bikes,0),docks:eligible.reduce((n,s)=>n+s.docks,0),
    emptyRate:eligible.length?eligible.filter(s=>s.bikes===0).length/eligible.length:null};
}
export function historySegments(history, key='bikes') {
  const segments=[];let run=[];
  for(const item of history){
    if(!Number.isFinite(item[key])) continue;
    if(run.length && !item.connected_to_previous){segments.push(run);run=[];}
    run.push(item);
  }
  if(run.length)segments.push(run);
  return segments;
}
export function relativeAge(at,now=Date.now()) {
  const age=Math.max(0,Math.floor((now-Date.parse(at))/60000));
  if(!Number.isFinite(age))return 'heure indisponible';
  if(age<1)return 'moins d’une minute';
  if(age<60)return `${age} min`;
  if(age<1440)return `${Math.floor(age/60)} h ${age%60} min`;
  return `${Math.floor(age/1440)} j ${Math.floor((age%1440)/60)} h`;
}
export function captureFreshness(at,now=Date.now()){
  const age=(now-Date.parse(at))/60000;
  return Number.isFinite(age)&&age<=20?'recent':age<=90?'aging':'stale';
}
export function html(text){return String(text??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
export function display(n){return Number(n??0).toLocaleString('fr-FR');}
export function pct(n){return n==null?'—':`${(100*n).toLocaleString('fr-FR',{maximumFractionDigits:1})} %`;}
export function localTime(at){return new Intl.DateTimeFormat('fr-FR',{dateStyle:'short',timeStyle:'short',timeZone:'Europe/Paris'}).format(new Date(at));}
/** Screen-space geographic points. No dependency on vector-tile style loading.
 * Cluster at low zoom to preserve clickability and performance. */
export function layoutMapMarkers(stations, project, width, height, zoom=11, selectedId=null) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width<=0 || height<=0) return [];
  // Overview clustering scales with the actual viewport. On a phone, the
  // network has fewer screen pixels; keep markers legible instead of drawing
  // hundreds of overlapping dots. At street zoom, retain fine picking.
  const cell=zoom < 13.2 ? (width<=540 ? 46 : width<=860 ? 34 : 25)
                           : zoom < 16 ? 11 : 8;
  const cells=new Map();
  for (const station of stations) {
    if (!Number.isFinite(station.lon)||!Number.isFinite(station.lat)) continue;
    const p=project([station.lon,station.lat]);
    if (!p || !Number.isFinite(p.x) || !Number.isFinite(p.y) ||
        p.x < 0 || p.y < 0 || p.x > width || p.y > height) continue;
    // Always give the selected station its own dot.
    const chosen=station.id===selectedId;
    const key=chosen ? 'selected-'+station.id : Math.floor(p.x/cell)+':'+Math.floor(p.y/cell);
    let group=cells.get(key);
    if(!group){
      group={x:0,y:0,lon:0,lat:0,count:0,ids:[],available:0,empty:0,unknown:0,selected:chosen};
      cells.set(key,group);
    }
    group.x+=p.x;group.y+=p.y;group.lon+=station.lon;group.lat+=station.lat;
    group.count++;group.ids.push(station.id);group[station.condition]++;
  }
  return [...cells.values()].map(g=>{
    const n=g.count;
    return {x:g.x/n,y:g.y/n,lon:g.lon/n,lat:g.lat/n,count:n,ids:g.ids,
      condition:g.unknown===n?'unknown':g.available>0?'available':'empty',selected:g.selected};
  });
}

export function pickMapMarker(points,x,y,radius=14) {
  let best=null,dist=radius*radius;
  for(const point of points){
    const gap=(point.x-x)**2+(point.y-y)**2;
    if(gap<dist){dist=gap;best=point;}
  }
  return best;
}

export const ISSUE_LABELS = Object.freeze({
  stale_station_report:'Signal station trop ancien',
  over_declared_capacity:'Total vélos + bornes supérieur à la capacité',
  invalid_station_metadata:'Informations de station invalides',
  missing_station_information:'Station absente du référentiel',
  missing_station_status:'Statut de station absent',
  invalid_counts:'Nombres de vélos ou bornes invalides',
  invalid_station_timestamp:'Horodatage station invalide',
  invalid_operational_flag:'État de service invalide',
  bike_types_disagree:'Types de vélos incohérents',
  station_code_mismatch:'Identifiants de station incohérents',
  invalid_or_duplicate_information_id:'Identifiant de station absent ou dupliqué',
  invalid_or_duplicate_status_id:'Identifiant de statut absent ou dupliqué',
  alias_bikes_mismatch:'Nombre de vélos incohérent entre les deux champs source',
  alias_docks_mismatch:'Nombre de bornes incohérent entre les deux champs source',
  station_report_future_of_feed:'Signal station daté après le flux source',
});
export function issueLabel(code){return ISSUE_LABELS[code] ?? String(code).replaceAll('_',' ');}

/** No ML readiness is deduced from a short P6 replay. All thresholds come from
 * P5's ten-day GitHub Release filename inventory and remain unverified labels. */
export function p5Gate(data){
  const evidence=data?.p5_readiness;
  if(!evidence || evidence.status==='unavailable' || evidence.source!=='GitHub Release asset names (not P3 revalidated content)')
    return {available:false,captures:null,days:null,coverage:null,eligible:false,checkedAt:null};
  const valid=Number.isInteger(evidence.captures)&&evidence.captures>=0 &&
    Number.isFinite(evidence.span_days)&&evidence.span_days>=0 &&
    (evidence.coverage_estimate===null || (Number.isFinite(evidence.coverage_estimate)&&evidence.coverage_estimate>=0&&evidence.coverage_estimate<=1));
  if(!valid)return {available:false,captures:null,days:null,coverage:null,eligible:false,checkedAt:null};
  return {available:true,captures:evidence.captures,days:evidence.span_days,
    coverage:evidence.coverage_estimate,eligible:evidence.status==='eligible_to_attempt_training',
    checkedAt:evidence.checked_at_utc,reason:evidence.reason};
}

/** Observed invalid/unknown is distinct from missing. No issue type alone proves
 * a station's availability; flags and per-station events come from the same run. */
export function qualityReasons(station){
  const reasons=[];
  if(!station.observed)return ['Aucun statut enregistré pour cette station dans la capture.'];
  if(station.is_operational===false)reasons.push('Service interrompu : la station ne permet pas les opérations normales.');
  for(const issue of station.issues||[]){
    const label=issueLabel(issue.code);
    if(!reasons.includes(label)) reasons.push(label);
  }
  if(!station.usable && reasons.length===0)reasons.push('Observation rejetée par les règles de qualité P3 ; motif non disponible.');
  if(station.usable && reasons.length===0)reasons.push('Observation qualifiée, sans anomalie attachée.');
  return reasons;
}

/** Counts exactly what is projected inside the current map viewport.
 * A clustered marker can represent many visible stations. Outside stations
 * are filtered in layoutMapMarkers; never confuse this with the global total.
 */
export function viewportCounts(filteredCount, visibleMarkers){
  return {filtered:filteredCount,visible:visibleMarkers.reduce((sum,p)=>sum+p.count,0),
    markers:visibleMarkers.length,clusters:visibleMarkers.filter(p=>p.count>1).length};
}
