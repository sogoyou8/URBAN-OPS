"""Create a four-page editable PBIP/PBIR + TMDL Power BI project from P4 CSV.

This creates text-based Power BI project files, NOT a .pbix and not a verified
Power BI Desktop render. Import assets are real only when CSV are replayed from
verified P3 releases; synthetic fixtures are allowed only in automated tests.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path
from urban_ops.analytics import TABLES

SCHEMA='https://developer.microsoft.com/json-schemas/fabric/'
NAME='UrbanOps'
COL_TYPES={
    'station_id':'int64','capacity':'int64','year':'int64','month':'int64','day_of_week':'int64',
    'is_weekend':'int64','local_hour':'int64','utc_offset_minutes':'int64',
    'samples':'int64','usable_samples':'int64','invalid_samples':'int64','empty_samples':'int64','full_samples':'int64',
    'sum_bikes_available':'int64','sum_docks_available':'int64','sum_mechanical_available':'int64',
    'sum_ebikes_available':'int64','distinct_station_reports':'int64','observed_stations':'int64',
    'num_bikes_available':'int64','num_docks_available':'int64','mechanical_bikes':'int64','electric_bikes':'int64',
    'reported_lag_seconds':'int64','is_usable':'int64','is_installed':'int64','is_renting':'int64','is_returning':'int64',
    'station_information_count':'int64','station_status_count':'int64','inserted_status_count':'int64','issue_count':'int64',
    'gap_over_10_minutes':'int64','latitude':'double','longitude':'double',
    'avg_bikes_available':'double','avg_docks_available':'double','avg_mechanical_available':'double',
    'avg_ebikes_available':'double','avg_station_report_lag_seconds':'double','gap_minutes':'double',
    'local_date':'dateTime','first_seen_at':'dateTime','last_seen_at':'dateTime',
    'utc_hour_start':'dateTime','collected_at':'dateTime','feed_updated_at':'dateTime',
    'station_reported_at':'dateTime','started_at':'dateTime','finished_at':'dateTime',
    'captured_at':'dateTime','previous_captured_at':'dateTime'
}
M_TYPES={'int64':'Int64.Type','double':'type number','dateTime':'type datetimezone'}
MEASURES={
    'Observations':("SUM('fact_station_hourly'[samples])",'#,##0'),
    'Observations exploitables':("SUM('fact_station_hourly'[usable_samples])",'#,##0'),
    'Stations observees':("DISTINCTCOUNT('fact_station_hourly'[station_id])",'#,##0'),
    'Taux qualite':("DIVIDE([Observations exploitables],[Observations])",'0.0%'),
    'Part sans velo':("DIVIDE(SUM('fact_station_hourly'[empty_samples]),[Observations exploitables])",'0.0%'),
    'Part sans borne':("DIVIDE(SUM('fact_station_hourly'[full_samples]),[Observations exploitables])",'0.0%'),
    'Velos moyens':("DIVIDE(SUM('fact_station_hourly'[sum_bikes_available]),[Observations exploitables])",'#,##0.0'),
    'Bornes moyennes':("DIVIDE(SUM('fact_station_hourly'[sum_docks_available]),[Observations exploitables])",'#,##0.0'),
    'Anomalies':("COUNTROWS('fact_issues')",'#,##0'),
    'Collectes reussies':("CALCULATE(COUNTROWS('fact_runs'),'fact_runs'[status] = \"success\")",'#,##0'),
    'Collectes echouees':("CALCULATE(COUNTROWS('fact_runs'),'fact_runs'[status] = \"failed\")",'#,##0'),
    'Intervalles > 10 min':("SUM('fact_capture_intervals'[gap_over_10_minutes])",'#,##0'),
    'Derniere capture UTC':("MAX('fact_station_latest'[collected_at])",'yyyy-MM-dd HH:mm'),
    'Velos moyens reseau':("DIVIDE(SUM('fact_network_hourly'[sum_bikes_available]), SUM('fact_network_hourly'[usable_samples]))",'#,##0.0'),
    'Bornes moyennes reseau':("DIVIDE(SUM('fact_network_hourly'[sum_docks_available]), SUM('fact_network_hourly'[usable_samples]))",'#,##0.0'),
    'Observations reseau valides':("SUM('fact_network_hourly'[usable_samples])",'#,##0'),
    'Observations reseau invalides':("SUM('fact_network_hourly'[invalid_samples])",'#,##0'),
}

def key(s):return hashlib.sha1(s.encode()).hexdigest()[:20]
def write(path:Path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    if isinstance(value,(dict,list)):
        value=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    path.write_text(value,encoding='utf-8')

def quoted(name):return name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name) else "'"+name.replace("'","''")+"'"

def tmdl_table(table,columns):
    out=[f'table {table}']
    for col in columns:
        typ=COL_TYPES.get(col,'string')
        out += ['',f'\tcolumn {quoted(col)}',f'\t\tdataType: {typ}',f'\t\tsourceColumn: {col}', '\t\tsummarizeBy: none']
    trs=[f'{{"{c}", {('type date' if c=='local_date' else M_TYPES[COL_TYPES[c]])}}}' for c in columns if COL_TYPES.get(c) in M_TYPES]
    changes='{' + ', '.join(trs) + '}'
    # The user changes DataFolder once; no file paths hardcoded to our runner.
    source=f'''\tpartition {table} = m
\t\tmode: import
\t\tsource =
\t\t\tlet
\t\t\t\tSource = Csv.Document(File.Contents(DataFolder & "/{table}.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
\t\t\t\tPromoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
\t\t\t\tTyped = Table.TransformColumnTypes(Promoted, {changes}, "en-US")
\t\t\tin
\t\t\t\tTyped'''
    return '\n'.join(out+['',source,''])+'\n'

def field(table,col,measure=False):
    k='Measure' if measure else 'Column'
    return {k:{'Expression':{'SourceRef':{'Entity':table}},'Property':col}}
def proj(table,col,measure=False):
    return {'field':field(table,col,measure), 'queryRef':f'{table}.{col}','nativeQueryRef':col}
def visual(page,title,typ,roles,x,y,w,h):
    name=key(page+'-'+title)
    v={'$schema':SCHEMA+'item/report/definition/visualContainer/2.7.0/schema.json','name':name,
       'position':{'x':x,'y':y,'z':1,'width':w,'height':h,'tabOrder':1},
       'visual':{'visualType':typ,'query':{'queryState':{role:{'projections':[proj(*f) for f in fields]} for role,fields in roles.items()}},
                 'visualContainerObjects':{'title':[{'properties':{'show':{'expr':{'Literal':{'Value':'true'}}},
                  'text':{'expr':{'Literal':{'Value':"'"+title.replace("'","''")+"'"}}}}}]}}}
    return name,v

def build(csv_dir:Path,output:Path)->dict:
    if not (csv_dir/'manifest.json').is_file():raise FileNotFoundError(f'Missing P4 manifest in {csv_dir}')
    manifest=json.loads((csv_dir/'manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('has_usable_history') or manifest.get('unique_collections',0)<1:
        raise ValueError('PBIP requires at least one replayed capture; do not fabricate rows')
    for table in TABLES:
        item=manifest.get('tables',{}).get(table)
        if item is None:raise ValueError(f'{table} missing in manifest')
        content=(csv_dir/(table+'.csv')).read_bytes()
        if hashlib.sha256(content).hexdigest()!=item['sha256']:
            raise ValueError(f'SHA-256 mismatch: {table}')
        with (csv_dir/(table+'.csv')).open(encoding='utf-8-sig',newline='') as f:
            if next(csv.reader(f))!=TABLES[table]:raise ValueError(f'CSV schema mismatch: {table}')
    project=output/NAME
    model=project/(NAME+'.SemanticModel')
    report=project/(NAME+'.Report')
    data=project/'data'
    data.mkdir(parents=True,exist_ok=True)
    for t in TABLES:shutil.copy2(csv_dir/(t+'.csv'),data/(t+'.csv'))
    shutil.copy2(csv_dir/'manifest.json',data/'manifest.json')
    write(project/(NAME+'.pbip'),{'$schema':SCHEMA+'pbip/pbipProperties/1.0.0/schema.json','version':'1.0','artifacts':[{'report':{'path':NAME+'.Report'}}]})
    for kind,folder in [('SemanticModel',model),('Report',report)]:
        write(folder/'.platform',{'$schema':SCHEMA+'gitIntegration/platformProperties/2.0.0/schema.json',
            'metadata':{'type':kind,'displayName':'Urban Ops / Vélib Intelligence'},
            'config':{'version':'2.0','logicalId':str(uuid.uuid5(uuid.NAMESPACE_DNS,'urbanops-p4-'+kind))}})
    write(model/'definition.pbism',{'$schema':SCHEMA+'item/semanticModel/definitionProperties/1.0.0/schema.json','version':'4.0','settings':{}})
    root=model/'definition'
    write(root/'database.tmdl',f'database {uuid.uuid5(uuid.NAMESPACE_DNS,"urbanops-p4-database")}\n\tcompatibilityLevel: 1702\n\tcompatibilityMode: powerBI\n\tlanguage: 1036\n')
    write(root/'model.tmdl','model Model\n\tculture: fr-FR\n\tsourceQueryCulture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\n'+ '\n'.join('ref table '+t for t in [*TABLES,'_Measures'])+'\n')
    write(root/'expressions.tmdl', 'expression DataFolder = "C:\\UrbanOps\\data" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n')
    for t,cols in TABLES.items():write(root/'tables'/(t+'.tmdl'),tmdl_table(t,cols))
    # A separate, non-numeric measure table is not used in the fact relationships.
    ms=['table _Measures']
    for name,(dax,fmt) in MEASURES.items():ms.extend(['',f'\tmeasure {quoted(name)} = {dax}',f'\t\tformatString: {fmt}'])
    ms.extend(['','\tcolumn Dummy','\t\tdataType: int64','\t\tisHidden','\t\tsourceColumn: [Dummy]','','\tpartition _Measures = calculated','\t\tmode: import','\t\tsource = ROW("Dummy", BLANK())',''])
    write(root/'tables'/'_Measures.tmdl','\n'.join(ms))
    relationships=[('fact_station_hourly','station_id','dim_station','station_id'),('fact_station_daily','station_id','dim_station','station_id'),('fact_station_latest','station_id','dim_station','station_id'),('fact_issues','station_id','dim_station','station_id'),('fact_station_hourly','local_date','dim_date','local_date'),('fact_station_daily','local_date','dim_date','local_date'),('fact_issues','run_id','fact_runs','run_id')]
    write(root/'relationships.tmdl','\n\n'.join(f'relationship rel_{i:02d}\n\tfromColumn: {a}.{b}\n\ttoColumn: {c}.{d}' for i,(a,b,c,d) in enumerate(relationships,1))+'\n')
    write(report/'definition.pbir',{'$schema':SCHEMA+'item/report/definitionProperties/2.0.0/schema.json','version':'4.0','datasetReference':{'byPath':{'path':'../'+NAME+'.SemanticModel'}}})
    defs=report/'definition'
    write(defs/'version.json',{'$schema':SCHEMA+'item/report/definition/versionMetadata/1.0.0/schema.json','version':'2.0.0'})
    # Registered custom theme is generated by us; no borrowed Microsoft base theme.
    custom_theme=Path(__file__).resolve().parents[1]/'powerbi'/'urbanops_theme.json'
    if not custom_theme.is_file():raise FileNotFoundError(f'Urban Ops theme is missing: {custom_theme}')
    (report/'StaticResources'/'RegisteredResources').mkdir(parents=True,exist_ok=True)
    shutil.copy2(custom_theme,report/'StaticResources'/'RegisteredResources'/'UrbanOpsTheme.json')
    write(defs/'report.json',{
        '$schema':SCHEMA+'item/report/definition/report/3.2.0/schema.json',
        'themeCollection':{'customTheme':{'name':'UrbanOpsTheme.json','type':'RegisteredResources',
            'reportVersionAtImport':{'visual':'2.7.0','report':'3.2.0','page':'2.1.0'}}},
        'resourcePackages':[{'name':'RegisteredResources','type':'RegisteredResources','items':[
            {'name':'UrbanOpsTheme.json','path':'UrbanOpsTheme.json','type':'CustomTheme'}]}],
        'settings':{'useStylableVisualContainerHeader':True}
    })
    M=lambda n:('_Measures',n,True)
    C=lambda t,n:(t,n,False)
    pages=[
      ('01 · Réseau',[
        ('Stations observées','cardVisual',{'Data':[M('Stations observees')]},35,105,270,132),
        ('Observations exploitables','cardVisual',{'Data':[M('Observations exploitables')]},323,105,270,132),
        ('Part sans vélo','cardVisual',{'Data':[M('Part sans velo')]},611,105,270,132),
        ('Dernière capture UTC','cardVisual',{'Data':[M('Derniere capture UTC')]},899,105,340,132),
        ('Disponibilité horaire','lineChart',{'Category':[C('fact_network_hourly','utc_hour_start')],'Y':[M('Velos moyens reseau'),M('Bornes moyennes reseau')]},35,260,760,380),
        ('Qualité par heure','columnChart',{'Category':[C('fact_network_hourly','utc_hour_start')],'Y':[M('Observations reseau valides'),M('Observations reseau invalides')]},818,260,421,380),
      ]),
      ('02 · Territoires',[
        ('Stations référencées','cardVisual',{'Data':[M('Stations observees')]},35,105,270,132),
        ('Vélos moyens par observation','cardVisual',{'Data':[M('Velos moyens')]},323,105,305,132),
        ('Bornes libres moyennes','cardVisual',{'Data':[M('Bornes moyennes')]},646,105,305,132),
        ('Implantation des stations (coordonnées)','scatterChart',{'Category':[C('dim_station','station_code')],'X':[C('dim_station','longitude')],'Y':[C('dim_station','latitude')]},35,260,705,380),
        ('Référentiel géographique','tableEx',{'Values':[C('dim_station','station_name'),C('dim_station','station_code'),C('dim_station','capacity'),C('dim_station','latitude'),C('dim_station','longitude')]},764,260,475,380),
      ]),
      ('03 · Stations',[
        ('Sélectionner une station','slicer',{'Values':[C('dim_station','station_name')]},35,110,365,135),
        ('Vélos disponibles moyens','cardVisual',{'Data':[M('Velos moyens')]},422,110,280,135),
        ('Observations exploitables','cardVisual',{'Data':[M('Observations exploitables')]},723,110,280,135),
        ('Evolution des vélos et bornes par heure','lineChart',{'Category':[C('fact_station_hourly','utc_hour_start')],'Y':[M('Velos moyens'),M('Bornes moyennes')]},35,267,770,375),
        ('Observations par jour local','tableEx',{'Values':[C('fact_station_daily','local_date'),C('fact_station_daily','samples'),C('fact_station_daily','usable_samples'),C('fact_station_daily','empty_samples'),C('fact_station_daily','full_samples')]},828,267,411,375),
      ]),
      ('04 · Fiabilité',[
        ('Captures réussies','cardVisual',{'Data':[M('Collectes reussies')]},35,105,270,132),
        ('Captures échouées','cardVisual',{'Data':[M('Collectes echouees')]},323,105,270,132),
        ('Anomalies tracées','cardVisual',{'Data':[M('Anomalies')]},611,105,270,132),
        ('Intervalles > 10 min','cardVisual',{'Data':[M('Intervalles > 10 min')]},899,105,340,132),
        ('Catégories d anomalies','barChart',{'Category':[C('fact_issues','issue_code')],'Y':[M('Anomalies')]},35,265,520,370),
        ('Intervalles entre collectes','lineChart',{'Category':[C('fact_capture_intervals','captured_at')],'Y':[C('fact_capture_intervals','gap_minutes')]},580,265,659,370),
      ])
    ]
    # Avoid showing a phantom observed trend when there is only one capture. No fabricated rows.
    ids=[];total=0
    for title,items in pages:
        pid=key(title);ids.append(pid)
        page=defs/'pages'/pid
        write(page/'page.json',{'$schema':SCHEMA+'item/report/definition/page/2.1.0/schema.json',
            'name':pid,'displayName':title,'displayOption':'FitToPage','height':720,'width':1280})
        for label,typ,roles,x,y,w,h in items:
            vid,body=visual(pid,label,typ,roles,x,y,w,h)
            write(page/'visuals'/vid/'visual.json',body)
            total+=1
    write(defs/'pages'/'pages.json',{'$schema':SCHEMA+'item/report/definition/pagesMetadata/1.1.0/schema.json',
        'pageOrder':ids,'activePageName':ids[0]})
    readme=f'''# Urban Ops — Power BI PBIP (prévisualisation technique)

- 4 pages préassemblées, {total} visuels natifs, 9 tables CSV et {len(MEASURES)} mesures DAX.
- Couverture réelle dans cet export : **{manifest['unique_collections']} captures**, {manifest['unique_stations_observed']} stations, de {manifest['from_utc']} à {manifest['through_utc']}.
- Sources CSV et métadonnées: `data/*.csv`, `data/manifest.json` ; vérifier provenance et SHA-256 avant diffusion.
- **Non vérifié dans Power BI Desktop Windows** : la compatibilité réelle du PBIP, les détails visuels et les autorisations de chargement doivent être testés dans Desktop.
- Les rapports ne prétendent pas avoir un historique plus long ou une disponibilité temporelle mesurée.

## Ouverture dans Power BI Desktop
1. Extraire tout le dossier UrbanOps sur le PC (par exemple C:\\UrbanOps).
2. Ouvrir `UrbanOps.pbip` depuis Power BI Desktop récent (format PBIR).
3. Dans les paramètres Power Query, modifier **DataFolder** vers le chemin absolu du dossier `UrbanOps\\data` extrait (sans guillemets supplémentaires), puis Actualiser.
4. Contrôler les 4 pages, les types, les relations et les mesures, corriger l'affichage si le Desktop demande une migration du thème ou du format PBIR.
5. Enregistrer sous `.pbip` puis, si nécessaire, publier/exporter un `.pbix` depuis Desktop. Aucun .pbix binaire n'est fourni ici.

## Limites
Les agrégats sont calculés sur les **captures observées**, pas sur la durée réelle d'un service, ni sur les trajets. La première capture ne permet aucun diagnostic de tendances. Le graphique de latitude/longitude utilise un nuage de points (pas une carte SIG).
'''
    write(project/'README_OUVERTURE.md',readme)
    result={'pages':len(pages),'visuals':total,'tables':len(TABLES),'measures':len(MEASURES),'captures':manifest['unique_collections'],'project':str(project)}
    write(project/'BUILD_MANIFEST.json',result)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--csv-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.csv_dir,a.output),ensure_ascii=False))
if __name__=='__main__':main()