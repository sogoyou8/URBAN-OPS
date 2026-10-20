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
 history:[{at:'2026-10-20T01:00:00Z',bikes:15,gap_minutes:null,connected_to_previous:false},
          {at:'2026-10-20T01:05:00Z',bikes:16,gap_minutes:5,connected_to_previous:true}],
 forecast:{status:'unavailable',horizon_minutes:30},
};

async function startServer(){
 const server=createServer(async (req,res)=>{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  if(pathname==='/data/network.json'){
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
 return {server,url:'http://127.0.0.1:'+server.address().port};
}

const {server,url}=await startServer();
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
    this.el.addEventListener('click',event=>{
     const r=this.el.getBoundingClientRect();
     for(const fn of this.events.click||[])fn({point:{x:event.clientX-r.left,y:event.clientY-r.top}});
    });
    setTimeout(()=>{for(const fn of this.events.load||[])fn();},30);
   }
   on(name,fn){(this.events[name]??=[]).push(fn);}
   addControl(){}
   project([lon,lat]){return {x:(lon-2)*700,y:(48.97-lat)*1500};}
   getZoom(){return this.zoom;}
   getCanvas(){return this.el;}
   flyTo(opts){this.zoom=opts.zoom;this.center=opts.center;}
   easeTo(opts){this.zoom=opts.zoom;this.center=opts.center;}
   fitBounds(){}
   resize(){}
   remove(){}
  }
  window.maplibregl={Map:MockMap,NavigationControl:class{}};
 });
 await page.goto(url,{waitUntil:'load',timeout:20000});
 await page.waitForFunction(()=>document.querySelector('#station-overlay')?.width>0,{timeout:10000});
 await page.waitForFunction(()=>document.querySelector('#map-count')?.textContent.includes('REPÈRES'),{timeout:10000});
 const initial=await page.evaluate(()=>{
  const map=document.getElementById('map'),canvas=document.getElementById('station-overlay');
  const ctx=canvas.getContext('2d');
  return {markers:document.getElementById('map-count').textContent,
          pixel:ctx.getImageData(224,165,1,1).data[3],
          pageHeight:document.documentElement.scrollHeight,viewport:window.innerHeight,
          mapWidth:map.getBoundingClientRect().width};
 });
 assert.match(initial.markers,/4 STATIONS/);
 assert.ok(initial.pixel>0,'Geographic marker MUST render even when style layers never load');
 assert.ok(initial.pageHeight<=initial.viewport+3,'Desktop page should not vertically scroll');
 await page.click('[data-view="territoires"]');
 assert.match(await page.$eval('#headline-title',e=>e.textContent),/territoire/i);
 await page.click('[data-sector="NE"]');
 assert.match(await page.$eval('#map-count',e=>e.textContent),/STATIONS/);
 await page.click('[data-view="fiabilite"]');
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/Signal station trop ancien/);
 await page.click('[data-view="previsions"]');
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/PRÉVISION NON DISPONIBLE/);
 await page.click('[data-view="reseau"]');
 await page.click('[data-filter="empty"]');
 assert.match(await page.$eval('#map-count',e=>e.textContent),/1 STATIONS/);
 await page.click('[data-filter="all"]');
 await page.type('#station-search','Bercy');
 assert.match(await page.$eval('#station-results',e=>e.textContent),/1 stations/);
 await page.click('[data-station="2"]');
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/Bercy – Test/);
 assert.match(await page.$eval('#inspector-content',e=>e.textContent),/0/);
 await page.click('[data-back]');
 assert.ok(await page.$('#station-search'));
 // Representative laptop and mobile breakpoints.
 await page.setViewport({width:1024,height:768,deviceScaleFactor:1});
 await page.evaluate(()=>window.dispatchEvent(new Event('resize')));
 await new Promise(done=>setTimeout(done,80));
 const laptop=await page.evaluate(()=>({h:document.documentElement.scrollHeight,v:innerHeight,w:document.documentElement.scrollWidth,vw:innerWidth}));
 assert.ok(laptop.h<=laptop.v+3,'Laptop cockpit must stay within viewport');
 assert.ok(laptop.w<=laptop.vw+3,'Laptop must not scroll horizontally');
 await page.setViewport({width:390,height:844,deviceScaleFactor:1});
 await new Promise(done=>setTimeout(done,80));
 const mobile=await page.evaluate(()=>({w:document.documentElement.scrollWidth,vw:innerWidth}));
 assert.ok(mobile.w<=mobile.vw+3,'Mobile must not scroll horizontally');
 // External map library unavailable: geographically accurate fallback buttons remain clickable.
 const fallbackPage=await browser.newPage();
 await fallbackPage.setViewport({width:1440,height:900});
 await fallbackPage.setRequestInterception(true);
 fallbackPage.on('request',req=>req.url().startsWith(url)?req.continue():req.abort());
 await fallbackPage.goto(url,{waitUntil:'load',timeout:20000});
 await fallbackPage.waitForFunction(()=>!document.querySelector('#map-fallback').hidden,{timeout:10000});
 assert.equal(await fallbackPage.$eval('.fallback-point',els=>els.length),4);
 await fallbackPage.click('.fallback-point[aria-label="Inspecter Bercy – Test"]');
 assert.match(await fallbackPage.$eval('#inspector-content',e=>e.textContent),/Bercy – Test/);
 await fallbackPage.close();
 console.log('P6.6 BROWSER PASS: canvas marks, mono-screen, 4 tabs, sectors, quality, P5 gate, search, selection/back.');
}finally{
 if(browser)await browser.close();
 await new Promise(resolve=>server.close(resolve));
}
