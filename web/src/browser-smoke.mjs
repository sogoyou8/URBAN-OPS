/** P6.6 browser smoke — synthetic fixture ONLY in local ephemeral HTTP server.
 * No live data, no remote map tiles, no screenshot published as a real observation.
 */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve, join, extname} from 'node:path';
import puppeteer from 'puppeteer-core';

const ROOT=resolve(import.meta.dirname, '..');
const at=new Date().toISOString();
const stations=[
 {id:'1',name:'Opéra – Test',code:'1001',lat:48.86,lon:2.32,capacity:15,usable:true,observed:true,condition:'available',bikes:5,docks:10,mechanical:3,electric:2,reported_at:at},
 {id:'2',name:'Bercy – Test',code:'1002',lat:48.85,lon:2.45,capacity:12,usable:true,observed:true,condition:'empty',bikes:0,docks:12,mechanical:0,electric:0,reported_at:at},
 {id:'3',name:'Belleville – Test',code:'1003',lat:48.92,lon:2.39,capacity:20,usable:false,observed:true,condition:'unknown',bikes:null,docks:null,mechanical:null,electric:null,reported_at:null},
 {id:'4',name:'Montparnasse – Test',code:'1004',lat:48.80,lon:2.18,capacity:19,usable:true,observed:true,condition:'available',bikes:11,docks:8,mechanical:6,electric:5,reported_at:at},
];
const fixture={
 schema_version:1,dataset_type:'archived_p3_observations',run_id:'TEST_BROWSERS_ONLY',
 captured_at:at,generated_at:at,source:'SYNTHETIC BROWSER FIXTURE NOT FOR PUBLICATION',
 stations,metrics:{stations:4,observed:4,usable:3,unusable:1,bikes:16,docks:30,empty:1,capture_count:2},
 issues:[{code:'stale_station_report',count:1}],
 history:[{at:'2026-10-20T01:00:00Z',bikes:15,usable:3,observed:4,gap_minutes:null,connected_to_previous:false},
          {at:'2026-10-20T01:05:00Z',bikes:4,usable:1,observed:4,gap_minutes:5,connected_to_previous:true},
          {at:'2026-10-20T01:10:00Z',bikes:16,usable:3,observed:4,gap_minutes:5,connected_to_previous:true},
          {at:'2026-10-20T01:15:00Z',bikes:17,usable:3,observed:4,gap_minutes:5,connected_to_previous:true}],
 forecast:{status:'unavailable',horizon_minutes:30},
 quality_diagnostics:{not_observed:0,observed_but_unusable:1,observed_non_operational:1,
   stations_with_multiple_issue_events:0},
 p5_readiness:{status:'insufficient_history',source:'GitHub Release asset names (not P3 revalidated content)',
    captures:27,span_days:0.65,coverage_estimate:0.2,checked_at_utc:at},

};

async function startServer(){
 let dataAvailable=true;
 const server=createServer(async (req,res)=>{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  if(pathname==='/data/network.json'){
   if(!dataAvailable){res.writeHead(503,{'Content-Type':'text/plain','Cache-Control':'no-store'});res.end('Dataset offline');return;}
   res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});
   res.end(JSON.stringify(fixture));return;
  }
  const safe=resolve(ROOT,'.'+(pathname==='/'?'/index.html':pathname));
  if(!safe.startsWith(ROOT+'/')){res.writeHead(403);res.end();return;}
  try{
   const content=await readFile(safe);
   const type={'.css':'text/css','.js':'application/javascript','.html':'text/html'}[extname(safe)]||'application/octet-stream';
   res.writeHead(200,{'Content-Type':type});res.end(content);
  }catch{res.writeHead(404);res.end();}
 });
 await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
 return {server,url:'http://127.0.0.1:'+server.address().port,setDatasetAvailable:v=>{dataAvailable=v;}};
}

const {server,url,setDatasetAvailable}=await startServer();
let browser;
try{
 browser=await puppeteer.launch({executablePath:process.env.P6_CHROME||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 const page=await browser.newPage();
 await page.setViewport({width:1440,height:900,deviceScaleFactor:1});
 await page.setRequestInterception(true);
 page.on('request',req=>req.url().startsWith(url)?req.continue():req.abort());
 await page.evaluateOnNewDocument(()=>{
  // Precisely model the MapLibre projection and DOM click semantics, but NEVER request tiles.
  class MockMap{
   constructor({container}){
    this.el=document.getElementById(container);this.events={};this.zoom=11;
    this.fitCalls=0;this.center=[2.348,48.856];window.__mockMap=this;
    this.el.addEventListener('click',event=>{
     const r=this.el.getBoundingClientRect();
     for(const fn of this.events.click||[])fn({point:{x:event.clientX-r.left,y:event.clientY-r.top}});
    });
    setTimeout(()=>{for(const fn of this.events.load||[])fn();},30);
   }
   on(name,fn){(this.events[name]??=[]).push(fn);}
   addControl(){}
   project([lon,lat]){const base={x:(lon-2)*700,y:(48.97-lat)*1500};
    if(this.zoom<14)return base;
    const scale=2**(this.zoom-13);
    return {x:350+(base.x-230)*scale,y:180+(base.y-170)*scale};
   }
   emitMove(){for(const fn of this.events.move||[])fn();}
   getZoom(){return this.zoom;}
   getCanvas(){return this.el;}
   flyTo(opts){this.zoom=opts.zoom;this.center=opts.center;this.emitMove();}
   easeTo(opts){this.zoom=opts.zoom;this.center=opts.center;this.emitMove();}
   fitBounds(bounds,opts){this.fitCalls++;this.zoom=Math.min(11,opts.maxZoom||11);this.center=[(bounds[0][0]+bounds[1][0])/2,(bounds[0][1]+bounds[1][1])/2];this.emitMove();}
   resize(){}
   remove(){}
  }
  window.maplibregl={Map:MockMap,NavigationControl:class{}};
 });
 await page.goto(url,{waitUntil:'load',timeout:20000});
 await page.waitForFunction(()=>document.querySelector('#station-overlay')?.width>0,{timeout:10000});
 await page.waitForFunction(()=>document.querySelector('#map-count')?.dataset.markers !== undefined,{timeout:10000});
 const initial=await page.evaluate(()=>{
  const map=document.getElementById('map'),canvas=document.getElementById('station-overlay');
  const ctx=canvas.getContext('2d');
  return {markers:document.getElementById('map-count').textContent,
          pixel:ctx.getImageData(224,165,1,1).data[3],
          pageHeight:document.documentElement.scrollHeight,viewport:window.innerHeight,
          mapWidth:map.getBoundingClientRect().width};
 });
 assert.match(initial.markers,/4 filtrées/);
 assert.equal(await page.$eval('#map-count',el=>el.dataset.filtered),'4');
 assert.equal(await page.$eval('#map-count',el=>el.dataset.visible),'4');
 assert.ok(initial.pixel>0,'Geographic marker MUST render even when style layers never load');
 assert.ok(initial.pageHeight<=initial.viewport+3,'Desktop page should not vertically scroll');
 assert.match(await page.$eval('.eyebrow',el=>el.textContent),/VÉLIB’ MÉTROPOLE/);
 assert.match(await page.$eval('#headline-description',el=>el.textContent),/stations Vélib’/);
 assert.match(await page.$eval('.scope-note',el=>el.textContent),/pas de temps réel/);
 assert.equal(await page.$eval('#timeline-heading',e=>e.textContent),'Historique des vélos');
 assert.match(await page.$eval('.timeline-meta',e=>e.textContent),/CAPTURES INCOMPLÈTES/);
 assert.match(await page.$eval('#timeline-explain',e=>e.textContent),/capture\(s\) incomplète\(s\)/);
 assert.doesNotMatch(await page.$eval('#timeline-explain',e=>e.textContent),/couverture réduite/i);
 assert.equal(await page.$eval('#timeline-quality',el=>el.textContent),'1',
   'One actual low-coverage observation must be visible as a warning');
 assert.equal(await page.$$eval('.timeline-svg polyline',els=>els.length),1,
   'Only the last two comparable captures may form a connected line');
 assert.match(await page.$eval('.timeline-svg',el=>el.getAttribute('aria-label')),/zéro/);
 await page.click('#open-guide');
 assert.equal(await page.$eval('#understand-dialog',el=>el.hidden),false);
 assert.equal(await page.$eval('#open-guide',el=>el.getAttribute('aria-expanded')),'true');
 assert.equal(await page.evaluate(()=>document.activeElement.id),'close-guide');
 assert.match(await page.$eval('#guide-context-text',el=>el.textContent),/station pour voir les vélos/);
 assert.match(await page.$eval('.guide-method',el=>el.textContent),/10 %/);
 await page.keyboard.press('Escape');
 assert.equal(await page.$eval('#understand-dialog',el=>el.hidden),true);
 assert.equal(await page.evaluate(()=>document.activeElement.id),'open-guide');

 // Zoomed viewport cannot continue to show the network total as if all were visible.
 await page.evaluate(()=>{window.__mockMap.zoom=16;window.__mockMap.emitMove()});
 const zoomed=await page.$eval('#map-count',e=>({total:+e.dataset.filtered,visible:+e.dataset.visible}));
 assert.equal(zoomed.total,4);
 assert.ok(zoomed.visible<zoomed.total,'Off-screen stations must not be counted as visible');
 await page.click('[data-view="territoires"]');
 assert.equal(await page.evaluate(()=>window.__mockMap.getZoom()),11);
 assert.equal(await page.$eval('#map-count',e=>e.dataset.visible),'4');
 assert.ok(await page.evaluate(()=>window.__mockMap.fitCalls>=1));
 // Clicking the active section must preserve exploratory zoom.
 await page.evaluate(()=>{window.__mockMap.zoom=15;window.__mockMap.emitMove()});
 await page.click('[data-view="territoires"]');
 assert.equal(await page.evaluate(()=>window.__mockMap.getZoom()),15);
 assert.match(await page.$eval('#headline-title',e=>e.textContent),/secteurs/i);
 await page.click('[data-sector="NE"]');
 assert.match(await page.$eval('#map-count',e=>e.textContent),/filtrées/);
 await page.click('[data-view="fiabilite"]');
 await page.click('#open-guide');
 assert.match(await page.$eval('#guide-context-title',el=>el.textContent),/Fiabilité/);
 await page.click('#close-guide');

 assert.equal(await page.evaluate(()=>window.__mockMap.getZoom()),11);
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/Signal station trop ancien/);
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/stations avec données inutilisables/);
 await page.click('#inspect-unqualified');
 assert.match(await page.$eval('#map-count',e=>e.textContent),/1 filtrées/);
 assert.match(await page.$eval('#station-list',e=>e.textContent),/Belleville/);
 await page.click('[data-station="3"]');
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/FIABILITÉ DES CHIFFRES/);
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/ne peuvent pas être utilisés/);
 await page.click('[data-back]');
 assert.match(await page.$eval('#station-list',e=>e.textContent),/Belleville/);
 await page.click('[data-view="fiabilite"]');
 await page.click('[data-view="previsions"]');
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/PRÉVISION NON DISPONIBLE/);
 // A new section always opens its inspector at the top (even from a scrolled one).
 await page.evaluate(()=>{document.querySelector('#inspector-content').scrollTop=180});
 await page.click('[data-view="reseau"]');
 assert.equal(await page.$eval('#inspector-content',e=>e.scrollTop),0);
 await page.click('[data-view="previsions"]');
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/27 \/ 900/);
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/À vérifier/);
 await page.click('[data-view="reseau"]');
 await page.click('[data-filter="empty"]');
 assert.equal(await page.$eval('[data-filter="empty"]',e=>e.getAttribute('aria-pressed')),'true');
 assert.match(await page.$eval('#map-count',e=>e.textContent),/1 filtrées/);
 await page.click('[data-filter="all"]');
 await page.type('#station-search','Bercy');
 assert.match(await page.$eval('#station-results',e=>e.textContent),/1 stations/);
 await page.click('[data-station="2"]');
 assert.ok(await page.$('#map-reset'));
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/Bercy – Test/);
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/0/);
 await page.click('[data-back]');
 assert.ok(await page.$('#station-search'));
 assert.equal(await page.$eval('#station-search',el=>el.value),'Bercy');
 const fitBeforeReset=await page.evaluate(()=>window.__mockMap.fitCalls);
 await page.click('#map-reset');
 assert.equal(await page.$eval('#station-search',el=>el.value),'Bercy');
 assert.ok(await page.evaluate(()=>window.__mockMap.fitCalls)>fitBeforeReset,
   'Map reset must fit the actual network, not hardcoded Paris');
 await page.click('[data-station="2"]');
 assert.equal(await page.evaluate(()=>document.activeElement?.hasAttribute('data-back')),true);
 await page.keyboard.press('Escape');
 assert.equal(await page.evaluate(()=>document.activeElement?.dataset.station),'2');
 assert.ok(await page.$('#station-search'));
 // Failure must offer a visible self-service recovery without fake data.
 setDatasetAvailable(false);
 await page.click('#reload');
 await page.waitForFunction(()=>!document.getElementById('error-state').hidden);
 assert.match(await page.$eval('#error-message',e=>e.textContent),/503/);
 assert.ok(await page.$('#retry-data'));
 setDatasetAvailable(true);
 await page.click('#retry-data');
 await page.waitForFunction(()=>document.getElementById('error-state').hidden);
 assert.equal(await page.$eval('#map-count',e=>e.dataset.filtered),'1',
   'Successful retry preserves the station search context');
 // Representative laptop and mobile breakpoints.
 await page.setViewport({width:1024,height:768,deviceScaleFactor:1});
 await page.evaluate(()=>window.dispatchEvent(new Event('resize')));
 await new Promise(done=>setTimeout(done,80));
 const laptop=await page.evaluate(()=>({h:document.documentElement.scrollHeight,v:innerHeight,w:document.documentElement.scrollWidth,vw:innerWidth}));
 assert.ok(laptop.h<=laptop.v+3,'Laptop cockpit must stay within viewport');
 assert.ok(laptop.w<=laptop.vw+3,'Laptop must not scroll horizontally');
 await page.setViewport({width:390,height:844,deviceScaleFactor:1});
 await new Promise(done=>setTimeout(done,80));
 const mobile=await page.evaluate(()=>{
   const rect=id=>document.querySelector(id).getBoundingClientRect();
   return {
    w:document.documentElement.scrollWidth,vw:innerWidth,
    navScrollable:document.querySelector('.topnav').scrollWidth >= document.querySelector('.topnav').clientWidth,
    headingBottom:rect('.map-header h2').bottom,
    countBottom:rect('#map-count').bottom,
    filterTop:rect('.map-control').top,
    kpiFootStyle:getComputedStyle(document.querySelector('.metric-foot')).whiteSpace
   };
 });
 assert.ok(mobile.w<=mobile.vw+3,'Mobile must not scroll horizontally');
 const timelineMobile=await page.evaluate(()=>{
   const plot=document.querySelector('.timeline-plot').getBoundingClientRect();
   const line=document.querySelector('.bottomline').getBoundingClientRect();
   const meta=document.querySelector('.timeline-meta').getBoundingClientRect();
   return {plotWidth:plot.width,containerWidth:line.width,plotBottom:plot.bottom,metaTop:meta.top};
 });
 assert.ok(timelineMobile.plotWidth/timelineMobile.containerWidth>0.94,
   'Mobile history chart must occupy the full available width');
 assert.ok(timelineMobile.metaTop>=timelineMobile.plotBottom,
   'History indicators must appear below the mobile graph');
 assert.ok(mobile.navScrollable,'All four views must remain reachable on mobile');
 assert.ok(mobile.headingBottom+6<=mobile.filterTop,'Map title must remain above filters on mobile');
 assert.ok(mobile.countBottom+6<=mobile.filterTop,'Map counters must remain above filters on mobile');
 assert.equal(mobile.kpiFootStyle,'normal','Mobile KPI descriptions must be readable, not ellipsized');
 await page.click('#open-guide');
 const dialog=await page.evaluate(()=>{
   const e=document.querySelector('.guide-panel').getBoundingClientRect();
   return {x:e.x,width:e.width,viewport:innerWidth};
 });
 assert.ok(dialog.x>=0&&dialog.x+dialog.width<=dialog.viewport+2,'Guide stays inside mobile viewport');
 await page.keyboard.press('Escape');

 await page.setViewport({width:320,height:700,deviceScaleFactor:1});
 await new Promise(done=>setTimeout(done,90));
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+3),
   'Small phone must not scroll sideways');
 // External map library unavailable: geographically accurate fallback buttons remain clickable.
 const fallbackPage=await browser.newPage();
 await fallbackPage.setViewport({width:1440,height:900});
 await fallbackPage.setRequestInterception(true);
 fallbackPage.on('request',req=>req.url().startsWith(url)?req.continue():req.abort());
 await fallbackPage.goto(url,{waitUntil:'load',timeout:20000});
 await fallbackPage.waitForFunction(()=>!document.querySelector('#map-fallback').hidden,{timeout:10000});
 assert.equal(await fallbackPage.$$eval('.fallback-point',els=>els.length),4);
 await fallbackPage.click('.fallback-point[aria-label="Inspecter Bercy – Test"]');
 assert.match(await fallbackPage.$eval('#inspector-content',e=>e.textContent),/Bercy – Test/);
 // Reproduce a dense network in the *synthetic* fallback-only fixture:
 // hundreds of DOM markers should reduce to accessible geographic groups.
 const dense=Array.from({length:140},(_,i)=>({
   ...stations[0],id:String(1000+i),code:String(5000+i),
   name:'Groupe dense '+i,lat:48.86+(i%11)*0.000015,
   lon:2.32+(i%13)*0.000015,
 }));
 fixture.stations.push(...dense);
 fixture.metrics.stations+=dense.length;
 fixture.metrics.observed+=dense.length;
 fixture.metrics.usable+=dense.length;
 fixture.metrics.bikes+=dense.length*5;
 fixture.metrics.docks+=dense.length*10;
 await fallbackPage.reload({waitUntil:'load'});
 await fallbackPage.waitForFunction(count=>
   !document.querySelector('#map-fallback').hidden &&
   Number(document.querySelector('#map-count')?.dataset.filtered)===count,
   {timeout:10000},fixture.stations.length);
 const fallbackCount=await fallbackPage.$$('.fallback-point');
 const fallbackDiagnostic=await fallbackPage.$eval('#map-count',e=>({filtered:e.dataset.filtered,markers:e.dataset.markers}));
 console.log('P6 fallback dense QA:',JSON.stringify({count:fallbackCount.length,fixtureStations:fixture.stations.length,stat:fallbackDiagnostic}));
 assert.ok(fallbackCount.length<fixture.stations.length/2,
   `Fallback should cluster dense stations: ${fallbackCount.length} markers for ${fixture.stations.length} stations`);
 assert.ok(await fallbackPage.$('.fallback-point.cluster'),'Fallback groups must be accessible');
 await fallbackPage.click('.fallback-point.cluster');
 assert.match(await fallbackPage.$eval('#inspector-content',e=>e.textContent),/stations à cet emplacement/);
 assert.ok(await fallbackPage.$('[data-dismiss-cluster]'));
 await fallbackPage.close();
 console.log('P6.6 BROWSER PASS: canvas marks, mono-screen, 4 tabs, sectors, quality, P5 gate, search, selection/back.');
}finally{
 if(browser)await browser.close();
 await new Promise(resolve=>server.close(resolve));
}
