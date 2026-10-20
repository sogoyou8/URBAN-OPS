import test from 'node:test';
import assert from 'node:assert/strict';
import {validateDataset,selectStations,sectors,sectorSummaries,summary,historySegments,html,captureFreshness,relativeAge,bounds,layoutMapMarkers,pickMapMarker,issueLabel} from './core.js';
const stations=[
 {id:'1',name:'A & <B>',code:'001',lat:48.8,lon:2.2,usable:true,condition:'available',bikes:5,docks:5},
 {id:'2',name:'Deux',code:'002',lat:48.9,lon:2.4,usable:true,condition:'empty',bikes:0,docks:10},
 {id:'3',name:'Inconnue',code:'003',lat:48.92,lon:2.42,usable:false,condition:'unknown',bikes:null,docks:null},
];
const payload={schema_version:1,dataset_type:'archived_p3_observations',run_id:'test',captured_at:'2026-10-20T11:00:00Z',stations,history:[],issues:[],metrics:{stations:3},forecast:{status:'unavailable'}};
test('data contract and forecast fail closed',()=>{
 assert.equal(validateDataset(payload),payload);
 assert.throws(()=>validateDataset({...payload,forecast:{status:'available'}}),/prévisions/);
 assert.throws(()=>validateDataset({...payload,stations:[{...stations[0],lat:123},stations[1],stations[2]]}),/coordonnées/);
});
test('filters do not turn unknown data into zero',()=>{
 assert.deepEqual(selectStations(stations,{filter:'empty'}).map(x=>x.id),['2']);
 assert.deepEqual(selectStations(stations,{filter:'unknown'}).map(x=>x.id),['3']);
 assert.deepEqual(selectStations(stations,{query:'<B>'}).map(x=>x.id),['1']);
 assert.equal(summary(stations).bikes,5);
 assert.equal(summary(stations).usable,2);
 assert.equal(summary(stations).emptyRate,.5);
});
test('geographic partitions are empirical, not arrondissements',()=>{
 const withSectors=sectors(stations);
 const sums=sectorSummaries(withSectors);
 assert.equal(sums.reduce((s,x)=>s+x.stations,0),3);
 assert.equal(sums.reduce((s,x)=>s+x.qualified,0),2);
 assert.equal(bounds(stations).north,48.92);
});
test('historical plots break on real gaps and never fill missing timestamps',()=>{
 const points=[{at:'a',bikes:4,connected_to_previous:false},{at:'b',bikes:7,connected_to_previous:true},{at:'c',bikes:8,connected_to_previous:false},{at:'d',bikes:1,connected_to_previous:true}];
 assert.deepEqual(historySegments(points).map(x=>x.length),[2,2]);
});
test('public station labels must be escaped and age labeled',()=>{
 assert.equal(html('<img src=x onerror="x">'), '&lt;img src=x onerror=&quot;x&quot;&gt;');
 assert.equal(captureFreshness('2026-10-20T10:58:00Z',Date.parse('2026-10-20T11:00:00Z')),'recent');
 assert.equal(relativeAge('2026-10-20T10:00:00Z',Date.parse('2026-10-20T11:00:00Z')),'1 h 0 min');
});
test('map overlay projects real coordinates independently from style layers',()=>{
 const pts=layoutMapMarkers(stations, ([lon,lat])=>({x:lon*100,y:lat*10}),600,600,15,'1');
 assert.equal(pts.length,3);
 assert.equal(pts.find(p=>p.ids.includes('1')).selected,true);
 assert.equal(pickMapMarker(pts,220,488).ids[0],'1');
 assert.equal(layoutMapMarkers(stations,()=>({x:Infinity,y:0}),600,600).length,0);
});
test('clusters at overview zoom and zooming retains real station ids',()=>{
 const dense=[
   {...stations[0],id:'a',lon:2.301,lat:48.85},
   {...stations[0],id:'b',lon:2.302,lat:48.85},
   {...stations[0],id:'c',lon:2.303,lat:48.85},
 ];
 const projected=layoutMapMarkers(dense, ([lon,lat])=>({x:lon*100,y:lat*10}),600,600,11);
 assert.equal(projected.length,1);
 assert.equal(projected[0].count,3);
 assert.deepEqual(projected[0].ids,['a','b','c']);
 assert.equal(issueLabel('stale_station_report'),'Signal station trop ancien');
});
