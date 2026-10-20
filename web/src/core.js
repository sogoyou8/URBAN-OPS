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