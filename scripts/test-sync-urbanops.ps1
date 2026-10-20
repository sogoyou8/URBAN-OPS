#requires -Version 5.1
# Contract tests for the offline part of the one-folder sync. No GitHub token or real HTTP.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$script=Join-Path $PSScriptRoot 'sync-urbanops.ps1'
$temp=Join-Path ([IO.Path]::GetTempPath()) ('urbanops-sync-test-'+[guid]::NewGuid().ToString('N'))
$workspace=Join-Path $temp 'UrbanOps'
New-Item -ItemType Directory -Path $workspace -Force | Out-Null
function Assert([bool]$Condition, [string]$Message) { if (!$Condition) { throw "ASSERTION: $Message" } }
function Package([string]$Suffix) {
    $source=Join-Path $temp "source-$Suffix"
    $root=Join-Path $source 'UrbanOps'
    New-Item -ItemType Directory -Path (Join-Path $root 'data') -Force | Out-Null
    $reportDir=Join-Path $root 'UrbanOps.Report/definition'
    $semanticDir=Join-Path $root 'UrbanOps.SemanticModel/definition'
    New-Item -ItemType Directory -Path $reportDir,$semanticDir -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $root 'UrbanOps.pbip') -Value '{"version":"1.0"}' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $reportDir 'report.json') -Value "report-$Suffix" -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $semanticDir 'expressions.tmdl') -Value 'expression DataFolder = "C:\UrbanOps\data" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]' -Encoding UTF8
    $tables=[ordered]@{}
    foreach ($name in @('dim_station','dim_date','fact_station_hourly','fact_station_daily','fact_network_hourly','fact_station_latest','fact_issues','fact_runs','fact_capture_intervals')) {
        $file=Join-Path $root "data/$name.csv"
        [IO.File]::WriteAllText($file,"station_id,observations`n1,5`n",[Text.Encoding]::UTF8)
        $tables[$name]=[ordered]@{sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    [IO.File]::WriteAllText((Join-Path $root 'data/manifest.json'),(@{unique_collections=1;tables=$tables}|ConvertTo-Json -Depth 10),[Text.Encoding]::UTF8)
    $zip=Join-Path $temp "fake-$Suffix.zip"
    Compress-Archive -LiteralPath $root -DestinationPath $zip
    return $zip
}
try {
    $zip1=Package 'one'
    & $script -WorkspaceRoot $workspace -ArtifactZip $zip1 -SkipGitPull
    Assert (Test-Path (Join-Path $workspace 'UrbanOps.pbip')) 'PBIP absent au chemin permanent'
    Assert (Test-Path (Join-Path $workspace '.urbanops-local/sync-state.json')) 'Etat de synchronisation absent'
    $expr=Get-Content -LiteralPath (Join-Path $workspace 'UrbanOps.SemanticModel/definition/expressions.tmdl') -Raw
    Assert ($expr.Contains((Join-Path $workspace 'data'))) 'DataFolder incorrect'
    $bronze=Join-Path $workspace 'data/bronze/keep.json'
    New-Item -ItemType Directory -Force -Path (Split-Path $bronze) | Out-Null
    Set-Content -LiteralPath $bronze -Value 'preserved' -Encoding UTF8
    $localReport=Join-Path $workspace 'UrbanOps.Report/definition/report.json'
    Set-Content -LiteralPath $localReport -Value 'my-powerbi-edits' -Encoding UTF8
    $zip2=Package 'two'
    $failed=$false
    try { & $script -WorkspaceRoot $workspace -ArtifactZip $zip2 -SkipGitPull } catch { $failed=$true }
    Assert $failed 'Un rapport édité a été écrasé sans confirmation'
    Assert ((Get-Content -LiteralPath $localReport -Raw) -match 'my-powerbi-edits') 'Une modification locale a été perdue'
    & $script -WorkspaceRoot $workspace -ArtifactZip $zip2 -SkipGitPull -BackupAndReplace
    Assert ((Get-Content -LiteralPath $localReport -Raw) -match 'report-two') 'Remplacement explicitement demandé non effectué'
    $backups=@(Get-ChildItem (Join-Path $workspace '.urbanops-local/backups') -Filter '*.zip')
    Assert ($backups.Count -eq 1) 'Il faut un unique backup lors du conflit seulement'
    Assert (Test-Path -LiteralPath $bronze) 'Données Bronze locales effacées'
    $state=Get-Content -LiteralPath (Join-Path $workspace '.urbanops-local/sync-state.json') -Raw | ConvertFrom-Json
    Assert ($state.capturedCount -eq 1) 'Etat des données inattendu'
    & $script -WorkspaceRoot $workspace -ArtifactZip $zip2 -SkipGitPull
    Assert (@(Get-ChildItem (Join-Path $workspace '.urbanops-local/backups') -Filter '*.zip').Count -eq 1) 'Synchronisation identique a créé un autre backup'
    Write-Host 'PASS: installation, chemin permanent, refus d écrasement, backup explicite, données conservées, idempotence.'
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}