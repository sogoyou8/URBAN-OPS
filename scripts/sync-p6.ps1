#requires -Version 5.1
<# Synchronise l'instantané P6 réel dans le dossier UNIQUE UrbanOps.
   Nécessite `gh auth login`, Git et le workflow P6 réussi sur main.
   Ne modifie pas les rapports Power BI ni le code source. #>
[CmdletBinding()]
param([switch]$ReplaceLocalData)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dest = Join-Path $root 'web/data/network.json'
$stateDir = Join-Path $root '.urbanops-local/p6'
$stateFile = Join-Path $stateDir 'last-sha256.txt'
if (!(Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI absent. Installer gh puis effectuer gh auth login.' }
& gh auth status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Connecte GitHub CLI avec gh auth login.' }
$runJson = & gh run list -R sogoyou8/URBAN-OPS -w p6-cockpit.yml -b main -s success -L 1 --json databaseId
if ($LASTEXITCODE -ne 0 -or !$runJson) { throw 'Aucun workflow P6 réussi.' }
$run = @($runJson | ConvertFrom-Json)[0]
if (!$run.databaseId) { throw 'Aucun run P6 avec export réel.' }
if ((Test-Path -LiteralPath $dest) -and (Test-Path -LiteralPath $stateFile) -and !$ReplaceLocalData) {
  $known = (Get-Content -LiteralPath $stateFile -Raw).Trim()
  $current = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($current -ne $known) { throw 'network.json a été modifié localement : arrêt sans écrasement. Sauvegarde/compare le fichier ou relance avec -ReplaceLocalData.' }
}
if ((Test-Path -LiteralPath $dest) -and !(Test-Path -LiteralPath $stateFile) -and !$ReplaceLocalData) {
  throw 'Fichier P6 local sans état de synchronisation : arrêt pour préserver le contenu. Pour adopter les données GitHub, relancer avec -ReplaceLocalData.'
}
$temp = Join-Path ([IO.Path]::GetTempPath()) ('urbanops-p6-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -Force | Out-Null
try {
  & gh run download $run.databaseId -R sogoyou8/URBAN-OPS -n urban-ops-p6-real-data -D $temp
  if ($LASTEXITCODE -ne 0) { throw 'Le dernier run P6 réussi ne contient pas d’artifact de données réel (expiration 7 jours ?).' }
  $sources = @(Get-ChildItem -Path $temp -Filter 'network.json' -File -Recurse)
  if ($sources.Count -ne 1) { throw 'L’artifact P6 doit contenir un seul fichier network.json.' }
  $file = $sources[0].FullName
  $d = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($d.schema_version -ne 1 -or $d.dataset_type -ne 'archived_p3_observations' -or
      $d.metrics.stations -lt 1 -or !$d.captured_at -or $d.forecast.status -ne 'unavailable') {
    throw 'Fichier P6 réel invalide : refus de remplacer le tableau de bord.'
  }
  if (Test-Path -LiteralPath $dest) {
    $newSha = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    $oldSha = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($oldSha -eq $newSha) { Write-Host 'Urban Ops P6 : données déjà synchronisées.'; exit 0 }
    if ($ReplaceLocalData) {
      New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
      $backup = Join-Path $stateDir ('network-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
      Copy-Item -LiteralPath $dest -Destination $backup -Force
      Write-Host "Sauvegarde des précédentes données : $backup"
    }
  }
  New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
  Copy-Item -LiteralPath $file -Destination $dest -Force
  New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
  (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant() | Set-Content -LiteralPath $stateFile -Encoding Ascii
  Write-Host "P6 synchronisé : $($d.metrics.stations) stations, $($d.metrics.capture_count) archives, capture UTC $($d.captured_at)."
  Write-Host "Lance python -m http.server 5173 --directory web puis ouvre http://localhost:5173"
} finally {
  Remove-Item -LiteralPath $temp -Force -Recurse -ErrorAction SilentlyContinue
}