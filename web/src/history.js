/** C2.5: Presentation only. Every value comes from the verified P3 export. */
import {assessHistory,historySegments,historyDetailScale,display,localTime} from './core.js';

const NS='http://www.w3.org/2000/svg';
let selectedAt=null;
let visible=[];
let xPositions=[];
let currentDataset=null;

function node(tag,cls,text){
  const element=document.createElement(tag);
  if(cls)element.className=cls;
  if(text!==undefined)element.textContent=text;
  return element;
}
function svgNode(parent,tag,attributes,text){
  const item=document.createElementNS(NS,tag);
  for(const [key,value] of Object.entries(attributes||{}))item.setAttribute(key,String(value));
  if(text!==undefined)item.textContent=String(text);
  parent.append(item);
  return item;
}
function localHour(at){
  return new Intl.DateTimeFormat('fr-FR',{hour:'2-digit',minute:'2-digit',timeZone:'Europe/Paris'}).format(new Date(at));
}
function inspect(index){
  if(!Number.isInteger(index)||index<0||index>=visible.length)return;
  const point=visible[index],catalog=currentDataset.metrics.stations;
  selectedAt=point.at;
  const unknown=point.status==='unknown',low=point.status==='reduced';
  const status=unknown?'Données insuffisantes':low?'Capture incomplète':'Mesure comparable';
  const info=document.getElementById('history-inspection');
  info.replaceChildren();
  info.append(node('span','history-inspection-title',localTime(point.at)));
  const bikes=node('strong','history-inspection-bikes',display(point.bikes)+' ');
  bikes.append(node('small',null,'vélos comptés'));
  info.append(bikes);
  info.append(node('span','history-inspection-count',
    Number.isInteger(point.usable)?display(point.usable)+' / '+display(catalog)+' stations mesurées'
      :'Nombre de stations inconnu'));
  info.append(node('span','history-inspection-status'+(low?' warn':''),status));
  document.querySelectorAll('.history-point').forEach(item=>{
    item.classList.toggle('selected',Number(item.dataset.historyIndex)===index);
  });
  const line=document.getElementById('history-crosshair');
  if(line){line.setAttribute('x1',xPositions[index]);line.setAttribute('x2',xPositions[index]);}
  const slider=document.getElementById('history-capture-slider');
  if(slider){
    slider.value=String(index);
    slider.setAttribute('aria-valuetext',localTime(point.at)+', '+display(point.bikes)+' vélos, '+
      (point.usable===null?'nombre de stations inconnu':display(point.usable)+' stations mesurées')+
      ', '+status);
  }
}
export function renderHistory(dataset){
  currentDataset=dataset;
  const history=dataset.history;
  const usableHistory=assessHistory(history,dataset.metrics.stations);
  const count=history.length;
  document.getElementById('timeline-count').textContent=display(count);
  const gaps=history.slice(1).map(p=>p.gap_minutes).filter(Number.isFinite);
  document.getElementById('timeline-gap').textContent=gaps.length?
    Math.max(...gaps).toLocaleString('fr-FR',{maximumFractionDigits:1})+' min':'—';
  document.getElementById('timeline-quality').textContent=
    usableHistory.unknownCount?'—':display(usableHistory.reducedCount);
  const incomplete=usableHistory.reducedCount;
  document.getElementById('timeline-explain').textContent=incomplete?
    display(incomplete)+' '+(incomplete===1?'capture incomplète':'captures incomplètes')+' (orange).':
    'Les points orange signalent des captures incomplètes.';
  visible=usableHistory.points.filter(p=>Number.isFinite(p.bikes)&&p.bikes>=0&&
    Number.isFinite(Date.parse(p.at)));
  const target=document.getElementById('timeline-plot');
  target.replaceChildren();
  if(visible.length<2){
    target.append(node('div','timeline-empty','Pas assez de captures pour afficher l’évolution.'));
    document.getElementById('history-inspection').textContent='Aucune capture à inspecter.';
    return;
  }
  const mainScale=historyDetailScale(visible);
  const catalog=dataset.metrics.stations,peak=Math.max(catalog,...visible.map(p=>p.usable||0),1);
  const stationMax=Math.ceil(peak/100)*100;
  const first=Date.parse(visible[0].at),last=Date.parse(visible.at(-1).at),span=Math.max(1,last-first);
  const width=Math.max(290,Math.round(target.clientWidth)-20);
  const left=50,right=width-13,yTop=28,yBottom=98,barTop=147,barBottom=184;
  const xOf=p=>left+(right-left)*(Date.parse(p.at)-first)/span;
  const yOf=p=>yBottom-(yBottom-yTop)*
    (Math.max(mainScale.min,Math.min(mainScale.max,p.bikes))-mainScale.min)/
    (mainScale.max-mainScale.min);
  const yStation=p=>barBottom-(barBottom-barTop)*p.usable/stationMax;
  xPositions=visible.map(p=>xOf(p).toFixed(2));
  const heading=node('div','history-plot-head');
  const period=new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'long',timeZone:'Europe/Paris'});
  const sameDay=period.format(new Date(first))===period.format(new Date(last));
  const dateLabel=sameDay?period.format(new Date(first))+' · '+localHour(visible[0].at)+' – '+localHour(visible.at(-1).at):
    localTime(visible[0].at)+' – '+localTime(visible.at(-1).at);
  heading.append(node('span','history-date-range','◷ '+dateLabel));
  const minutes=Math.round(span/60000);
  const duration=minutes>=60?Math.floor(minutes/60)+' h '+String(minutes%60).padStart(2,'0'):minutes+' min';
  const chip=node('span','history-window',duration);
  chip.title='Période réellement disponible dans cet export';
  heading.append(chip);
  target.append(heading);

  const svg=svgNode(target,'svg',{class:'timeline-svg',viewBox:'0 0 '+width+' 202',role:'img',
    'aria-label':'Vélos comptés, échelle détaillée de '+display(mainScale.min)+' à '+display(mainScale.max)+
    '. Les barres du bas affichent les stations mesurées sur une échelle de zéro à '+display(stationMax)+'.'});
  svgNode(svg,'text',{x:left,y:14,class:'history-chart-label'},'Vélos comptés');
  svgNode(svg,'text',{x:right,y:14,class:'history-axis','text-anchor':'end'},'Échelle détaillée');
  for(const value of [mainScale.max,(mainScale.max+mainScale.min)/2,mainScale.min]){
    const y=yBottom-(yBottom-yTop)*(value-mainScale.min)/(mainScale.max-mainScale.min);
    svgNode(svg,'line',{x1:left,x2:right,y1:y,y2:y,class:'history-grid'});
    svgNode(svg,'text',{x:left-7,y:y+3,class:'history-axis','text-anchor':'end'},display(Math.round(value)));
  }
  const steps=width<500?2:4;
  for(let i=0;i<=steps;i++){
    const x=left+(right-left)*i/steps;
    const stamp=first+(last-first)*i/steps;
    svgNode(svg,'line',{x1:x,x2:x,y1:yTop,y2:yBottom,class:'history-grid-vertical'});
    svgNode(svg,'text',{x,y:115,class:'history-time',
      'text-anchor':i===0?'start':i===steps?'end':'middle'},localHour(stamp));
  }
  for(const group of historySegments(usableHistory.points)){
    const pts=group.filter(p=>Number.isFinite(p.bikes)&&p.bikes>=0&&Number.isFinite(Date.parse(p.at)));
    if(pts.length<2)continue;
    svgNode(svg,'polyline',{class:'history-line',points:pts.map(p=>
      xOf(p).toFixed(2)+','+yOf(p).toFixed(2)).join(' ')});
  }
  const crosshair=svgNode(svg,'line',{id:'history-crosshair',class:'history-crosshair',
    x1:xPositions[0],x2:xPositions[0],y1:23,y2:barBottom,'pointer-events':'none'});
  const barWidth=Math.max(2.5,Math.min(11,(right-left)/visible.length*.65));
  visible.forEach((p,index)=>{
    const x=xOf(p),y=yOf(p),outside=p.bikes<mainScale.min||p.bikes>mainScale.max;
    const low=p.status==='reduced',unknown=p.status==='unknown';
    const color=low?'#f3ae80':unknown?'#93a0ad':'#a1ecc1';
    const group=svgNode(svg,'g',{'data-history-index':index,class:'history-point',role:'presentation'});
    svgNode(group,'circle',{cx:x,cy:y,r:low?4.5:3.7,fill:color,stroke:'#06151a',
      'stroke-width':1.5,class:'history-bike-dot'});
    svgNode(group,'circle',{cx:x,cy:y,r:10,fill:'transparent',class:'history-hit'});
    svgNode(group,'title',{},localTime(p.at)+', '+display(p.bikes)+' vélos comptés'+
      (outside?', hors échelle détaillée':''));
    if(outside){
      const towardLow=p.bikes<mainScale.min,atY=towardLow?yBottom-8:yTop+8;
      svgNode(group,'path',{d:'M '+(x-4)+' '+(atY-4)+' L '+x+' '+(atY+3)+
        ' L '+(x+4)+' '+(atY-4),fill:'none',stroke:'#f3ae80',
        'stroke-width':1.5,'pointer-events':'none'});
    }
  });
  svgNode(svg,'text',{x:left,y:135,class:'history-chart-label'},'Stations mesurées');
  svgNode(svg,'text',{x:left-7,y:barTop+4,class:'history-axis','text-anchor':'end'},display(stationMax));
  svgNode(svg,'text',{x:left-7,y:barBottom+3,class:'history-axis','text-anchor':'end'},'0');
  svgNode(svg,'line',{x1:left,x2:right,y1:barBottom,y2:barBottom,class:'history-grid'});
  visible.forEach((p,index)=>{
    if(!Number.isInteger(p.usable))return;
    const y=yStation(p),x=xOf(p);
    const bar=svgNode(svg,'rect',{x:x-barWidth/2,y,width:barWidth,
      height:Math.max(.5,barBottom-y),class:'history-station-bar history-point',
      fill:p.status==='reduced'?'#f3ae80':'#80b9e2','data-history-index':index});
    svgNode(bar,'title',{},localTime(p.at)+', '+display(p.usable)+' stations mesurées');
  });
  const foot=node('div','history-plot-foot');
  const legend=node('div','history-legend');
  legend.innerHTML='<span><i class="history-key bikes"></i> Vélos comptés</span>'+
    '<span><i class="history-key incomplete"></i> Capture incomplète</span>'+
    '<span><i class="history-key measured"></i> Stations mesurées</span>';
  foot.append(legend);
  const control=node('label','history-capture-control','Explorer ');
  const slider=node('input');
  slider.type='range';slider.id='history-capture-slider';
  slider.min='0';slider.max=String(visible.length-1);slider.step='1';
  slider.setAttribute('aria-label','Explorer les captures');
  slider.setAttribute('aria-describedby','history-inspection');
  control.append(slider);foot.append(control);target.append(foot);
  if(mainScale.offScaleCount)target.append(node('span','history-scale-note',
    display(mainScale.offScaleCount)+' capture(s) hors échelle : valeur exacte dans le détail.'));
  svg.addEventListener('click',event=>{
    const item=event.target.closest('[data-history-index]');
    if(item)inspect(Number(item.dataset.historyIndex));
  });
  slider.addEventListener('input',()=>inspect(Number(slider.value)));
  const index=selectedAt===null?visible.length-1:
    Math.max(0,visible.findIndex(p=>p.at===selectedAt));
  inspect(index);
}
