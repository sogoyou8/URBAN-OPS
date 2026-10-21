/** P6.9 real archive package QA, served under a GitHub Pages-style subdirectory.
 * Chromium has no direct Internet access and DOES NOT deploy anything.
 */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {resolve, extname, relative, sep, join} from 'node:path';
import puppeteer from 'puppeteer-core';

const root=resolve(process.argv[2]||'dist/p6-public');
const prefix='/URBAN-OPS/';
const server=createServer(async(req,res)=>{
  const request=new URL(req.url,'http://127.0.0.1');
  if(!request.pathname.startsWith(prefix)){res.writeHead(404).end();return;}
  const sub=decodeURIComponent(request.pathname.slice(prefix.length))||'index.html';
  const path=resolve(root,sub);
  if(!(path===root || path.startsWith(root+sep))){res.writeHead(403).end();return;}
  try{
    const b=await readFile(path);
    const type={'.js':'application/javascript','.css':'text/css','.html':'text/html','.json':'application/json'}[extname(path)]||'application/octet-stream';
    res.writeHead(200,{'Content-Type':type,'Cache-Control':'no-store'}).end(b);
  }catch{res.writeHead(404).end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const base=`http://127.0.0.1:${server.address().port}${prefix}`;
let browser;
try{
  browser=await puppeteer.launch({headless:true,executablePath:process.env.P6_CHROME||'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle']});
  const page=await browser.newPage();
  await page.setViewport({width:1440,height:900,deviceScaleFactor:1});
  const errors=[], blocked=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.setRequestInterception(true);
  page.on('request',req=>{
    const u=req.url();
    if(u.startsWith(base))return req.continue();
    if(u.startsWith('https://tiles.openfreemap.org/styles/dark')){
      return req.respond({status:200,contentType:'application/json',body:JSON.stringify({version:8,name:'Offline QA background',sources:{},layers:[]})});
    }
    blocked.push(u);return req.abort('blockedbyclient');
  });
  await page.goto(base,{waitUntil:'domcontentloaded',timeout:20000});
  await page.waitForFunction(()=>document.querySelector('#map-count')?.dataset.filtered,
    {timeout:20000});
  const initial=await page.evaluate(()=>{
    const d=document.querySelector('#map-count');
    return {filtered:+d.dataset.filtered,visible:+d.dataset.visible,markers:+d.dataset.markers,
      scrollHeight:document.documentElement.scrollHeight,height:innerHeight,
      scrollWidth:document.documentElement.scrollWidth,width:innerWidth,
      scriptVendor:performance.getEntriesByType('resource').some(r=>r.name.includes('/vendor/maplibre-gl.js'))};
  });
  assert.ok(initial.filtered>1000,'Must load the actual replay-verified Vélib public data');
  assert.ok(initial.scriptVendor,'Page must load self-hosted MapLibre');
  assert.ok(initial.scrollHeight<=initial.height+3,'Desktop must remain screen-height');
  assert.ok(initial.scrollWidth<=initial.width+3,'Desktop must not scroll sideways');
  assert.ok(initial.visible<=initial.filtered && initial.markers<=initial.visible,'Viewport labels must be coherent');
  const auditDir=resolve('data/p6-c1c2-qa');
  await mkdir(auditDir,{recursive:true});
  assert.equal(await page.$eval('#history-size-toggle',e=>e.getAttribute('aria-pressed')),'false');
  const compact=await page.evaluate(()=>({
    map:document.querySelector('.operational').clientHeight,
    history:document.querySelector('#history-section').clientHeight
  }));
  await page.screenshot({path:join(auditDir,'desktop-real-1440x900.png'),fullPage:true});
  await page.click('#history-size-toggle');
  await page.waitForFunction(()=>document.querySelector('#history-section').classList.contains('history-expanded'));
  await new Promise(r=>setTimeout(r,60));
  const expanded=await page.evaluate(()=>({
    map:document.querySelector('.operational').clientHeight,
    history:document.querySelector('#history-section').clientHeight,
    scroll:document.documentElement.scrollHeight
  }));
  assert.ok(expanded.history>compact.history+25,'Expanded history must get more space');
  assert.ok(expanded.map<compact.map-25,'Map-first compact layout needs more map space');
  assert.ok(expanded.scroll<=900+3,'Expanding history must not add global desktop scroll');
  await page.screenshot({path:join(auditDir,'history-expanded-real-1440x900.png'),fullPage:true});
  await page.click('#history-size-toggle');
  await page.waitForFunction(()=>document.querySelector('#history-section').classList.contains('history-compact'));
  assert.match(await page.$eval('.eyebrow',e=>e.textContent),/VÉLIB’ MÉTROPOLE/);
  assert.match(await page.$eval('#headline-description',e=>e.textContent),/stations Vélib’/);
  assert.match(await page.$eval('.scope-note',e=>e.textContent),/pas de temps réel/);
  assert.equal(await page.$eval('#timeline-heading',e=>e.textContent),'Historique des vélos');
  assert.match(await page.$eval('.timeline-meta',e=>e.textContent),/CAPTURES INCOMPLÈTES/);
  assert.match(await page.$eval('.guide-method',e=>e.textContent),/points sont orange/i);
  assert.doesNotMatch(await page.$eval('#timeline-explain',e=>e.textContent),/couverture réduite/i);
  assert.ok(await page.$('.timeline-svg'),'Real verified history should be graphed');
  assert.ok((await page.$$('.history-station-bar')).length>=2,
    'Real archive includes actual usable-station bars');
  assert.ok((await page.$$('.history-bike-dot')).length>=2,
    'Real archive includes actual bike observations');
  assert.match(await page.$eval('.history-date-range',e=>e.textContent),/octobre|septembre|novembre|décembre|janvier|février|mars|avril|mai|juin|juillet|août/i);
  assert.match(await page.$eval('#history-inspection',e=>e.textContent),/vélos comptés/);
  await page.$eval('#history-capture-slider',e=>{e.value='0';e.dispatchEvent(new Event('input',{bubbles:true}));});
  assert.equal(await page.$eval('#history-capture-slider',e=>e.value),'0');
  assert.match(await page.$eval('#history-inspection',e=>e.textContent),/stations mesurées/);
  // Return to the latest real observation before taking the desktop evidence.
  await page.$eval('#history-capture-slider',e=>{e.value=e.max;e.dispatchEvent(new Event('input',{bubbles:true}));});
  assert.match(await page.$eval('.timeline-svg',e=>e.getAttribute('aria-label')),/échelle détaillée/i);
  assert.match(await page.$eval('.timeline-svg',e=>e.getAttribute('aria-label')),/zéro/i);
  await page.click('#open-guide');
  assert.equal(await page.$eval('#understand-dialog',e=>e.hidden),false);
  assert.match(await page.$eval('.guide-method',e=>e.textContent),/10 %/);
  await page.screenshot({path:join(auditDir,'guide-real-1440x900.png'),fullPage:true});
  await page.keyboard.press('Escape');
  assert.equal(await page.$eval('#understand-dialog',e=>e.hidden),true);

  // Exercise data-backed station inspection without assuming a station condition.
  const firstStation=await page.$('[data-station]');
  assert.ok(firstStation,'Real verified dataset should expose station rows');
  await firstStation.click();
  assert.ok(await page.$('[data-back]'),'Station inspector should offer a back control');
  assert.equal(await page.evaluate(()=>document.activeElement?.hasAttribute('data-back')),true,
    'Keyboard focus follows station inspection');
  await page.click('[data-back]');
  assert.ok(await page.$('#station-search'),'Back returns to search');
  await page.click('[data-view="fiabilite"]');
  assert.match(await page.$eval('#headline-title',e=>e.textContent),/donnée/i);
  await page.click('[data-view="previsions"]');
  assert.match(await page.$eval('#inspector-content',e=>e.textContent),/PRÉVISION NON DISPONIBLE/);
  await page.click('[data-view="reseau"]');
  await page.setViewport({width:390,height:844,deviceScaleFactor:1});
  await new Promise(r=>setTimeout(r,200));
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+3), 'Mobile must not scroll horizontally');
  await page.screenshot({path:join(auditDir,'mobile-real-390x844.png'),fullPage:true});
  assert.deepEqual(errors,[],'No browser page exceptions');
  assert.ok(!blocked.some(u=>u.includes('cdn.jsdelivr.net/npm/maplibre-gl')),'No external JS CDN at runtime');
  console.log(JSON.stringify({status:'PASS',loaded_real_stations:initial.filtered,vendor_loaded:true,network_requests_blocked:blocked.length,offline_basemap_smoke:true}));
}finally{
  if(browser)await browser.close();
  await new Promise(r=>server.close(r));
}