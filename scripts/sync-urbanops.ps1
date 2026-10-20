#requires -Version 5.1
<#
.SYNOPSIS
  Synchronise un UNIQUE espace de travail Urban Ops depuis GitHub Actions.
.DESCRIPTION
  Git pull --ff-only, récupération du dernier PBIP réussi et installation dans
  le dépôt local, sans ZIP ni dossier V2/V3. Refuse par défaut tout écrasement
  de modifications locales non suivies dans le rapport Power BI.
  Fermer Power BI Desktop avant toute synchronisation.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\sync-urbanops.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\sync-urbanops.ps1 -BackupAndReplace
#>
[CmdletBinding()]
param(
    [string]$WorkspaceRoot = '',
    [string]$ArtifactZip = '',
    [switch]$SkipGitPull,
    [switch]$BackupAndReplace
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Sha256([string]$File) {
    return (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Path-In-Workspace([string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative -match '(^|/|\\)\.\.($|/|\\)') {
        throw "Chemin relatif dangereux : $Relative"
    }
    return Join-Path $root ($Relative.Replace('/',[IO.Path]::DirectorySeparatorChar))
}
function Copy-Into([string]$From, [string]$To) {
    $parent = Split-Path -Parent $To
    if (!(Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    Copy-Item -LiteralPath $From -Destination $To -Force
}

$root = if ($WorkspaceRoot) {
    (Resolve-Path -LiteralPath $WorkspaceRoot).Path
} else {
    (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
}
if (Get-Process -Name 'PBIDesktop' -ErrorAction SilentlyContinue) {
    throw 'Ferme Power BI Desktop et enregistre ton travail avant de synchroniser Urban Ops.'
}
if (!$SkipGitPull) {
    if (!(Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git absent. Installer Git for Windows.' }
    Push-Location $root
    try {
        $branch = (& git branch --show-current | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $branch -ne 'main') { throw 'Ouvre la branche main du dépôt UrbanOps avant la mise à jour.' }
        $dirty = @(& git status --porcelain --untracked-files=no)
        if ($LASTEXITCODE -ne 0 -or ($dirty | Where-Object { $_ })) {
            throw 'Des fichiers Git suivis sont modifiés. Sauvegarde/commit ces modifications avant git pull.'
        }
        & git pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) { throw 'git pull a échoué. Aucune mise à jour Power BI réalisée.' }
    } finally { Pop-Location }
}

$stateDir  = Join-Path $root '.urbanops-local'
$statePath = Join-Path $stateDir 'sync-state.json'
$previous = $null
$oldHashes = @{}
if (Test-Path -LiteralPath $statePath) {
    $previous = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($previous.schema -ne 1) { throw 'Format de cet etat local inconnu. Vérifie .urbanops-local/sync-state.json.' }
    foreach ($item in $previous.files.PSObject.Properties) { $oldHashes[$item.Name] = [string]$item.Value }
}

$runId = $null
$commitSha = $null
if ($ArtifactZip) {
    $artifact = (Resolve-Path -LiteralPath $ArtifactZip).Path
    $runId = 'offline-' + (Get-Sha256 $artifact).Substring(0,16)
} else {
    if (!(Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI absent. Installer GitHub CLI (gh), puis gh auth login.' }
    & gh auth status 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Connexion GitHub CLI manquante : exécute gh auth login.' }
    $runJson = & gh run list --repo sogoyou8/URBAN-OPS --workflow p4-analytics.yml --branch main --status success --limit 1 --json databaseId,headSha,createdAt
    if ($LASTEXITCODE -ne 0 -or !$runJson) { throw 'Impossible de trouver une exécution P4 réussie sur GitHub.' }
    $runs = @($runJson | ConvertFrom-Json)
    if ($runs.Count -ne 1 -or !$runs[0].databaseId) { throw 'Aucun artefact P4 utilisable trouvé.' }
    $runId = [string]$runs[0].databaseId
    $commitSha = [string]$runs[0].headSha
}
if ($previous -and ([string]$previous.runId -eq $runId)) {
    Write-Host "Rapport Power BI déjà synchronisé (run $runId). Aucun autre dossier créé."
    exit 0
}

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('urbanops-sync-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
try {
    $zip = $null
    if ($ArtifactZip) {
        $zip = $artifact
    } else {
        $download = Join-Path $temporary 'download'
        New-Item -ItemType Directory -Path $download -Force | Out-Null
        & gh run download $runId --repo sogoyou8/URBAN-OPS --name urban-ops-p4-real-4pages-PBIP --dir $download
        if ($LASTEXITCODE -ne 0) { throw "Téléchargement GitHub de l'artefact P4 (run $runId) échoué. Vérifie sa disponibilité (14 jours)." }
        $zips = @(Get-ChildItem -LiteralPath $download -Filter '*.zip' -File -Recurse)
        if ($zips.Count -ne 1) { throw "L'artefact GitHub doit contenir un ZIP PBIP ; trouvés : $($zips.Count)" }
        $zip = $zips[0].FullName
    }
    $unpacked = Join-Path $temporary 'unpacked'
    Expand-Archive -LiteralPath $zip -DestinationPath $unpacked -Force
    $pbipFiles = @(Get-ChildItem -LiteralPath $unpacked -Recurse -File -Filter 'UrbanOps.pbip')
    if ($pbipFiles.Count -ne 1) { throw "Structure PBIP invalide : $($pbipFiles.Count) fichier(s) UrbanOps.pbip." }
    $packageRoot = Split-Path -Parent $pbipFiles[0].FullName
    foreach ($required in @('UrbanOps.Report','UrbanOps.SemanticModel','data','data/manifest.json')) {
        if (!(Test-Path -LiteralPath (Join-Path $packageRoot $required))) { throw "Fichier/dossier manquant : $required" }
    }

    # Vérifie la provenance et les SHA-256 de TOUS les CSV exportés.
    $datasetManifest = Get-Content -LiteralPath (Join-Path $packageRoot 'data/manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([int]$datasetManifest.unique_collections -lt 1) { throw 'Aucune capture réelle dans le manifeste P4.' }
    $tableCount = 0
    foreach ($entry in $datasetManifest.tables.PSObject.Properties) {
        $csv = Join-Path $packageRoot ('data/' + $entry.Name + '.csv')
        if (!(Test-Path -LiteralPath $csv)) { throw "CSV absent : $($entry.Name)" }
        if ((Get-Sha256 $csv) -ne ([string]$entry.Value.sha256).ToLowerInvariant()) {
            throw "Empreinte SHA-256 invalide dans le rapport : $($entry.Name)"
        }
        $tableCount++
    }
    if ($tableCount -ne 9) { throw "9 tables analytiques attendues, $tableCount trouvées." }

    $newFiles = @{}
    $rootLen = $packageRoot.TrimEnd('\','/').Length
    foreach ($file in (Get-ChildItem -LiteralPath $packageRoot -Recurse -File -Force)) {
        $rel = $file.FullName.Substring($rootLen).TrimStart('\','/').Replace('\','/')
        $valid = $rel -in @('UrbanOps.pbip','BUILD_MANIFEST.json','COLLECTOR_COVERAGE.json','README_OUVERTURE.md') `
            -or $rel.StartsWith('UrbanOps.Report/') -or $rel.StartsWith('UrbanOps.SemanticModel/') `
            -or ($rel -match '^data/[^/]+\.csv$') -or $rel -eq 'data/manifest.json'
        if (!$valid) { throw "Fichier inattendu dans l'artefact P4 : $rel" }
        if ($newFiles.ContainsKey($rel)) { throw "Doublon dans l'artefact : $rel" }
        $newFiles[$rel] = $file.FullName
    }

    # Le paramètre est régénéré automatiquement à partir du dossier de travail FIXE.
    $exprKey = 'UrbanOps.SemanticModel/definition/expressions.tmdl'
    if (!$newFiles.ContainsKey($exprKey)) { throw 'Paramètre DataFolder absent du modèle.' }
    $exprText = [IO.File]::ReadAllText($newFiles[$exprKey])
    $pathValue = (Join-Path $root 'data').Replace('"','""')
    $pattern = '(?m)^expression DataFolder = "[^"]*"'
    if ([regex]::Matches($exprText,$pattern).Count -ne 1) { throw 'Expression DataFolder inattendue ; aucune modification effectuée.' }
    $exprText = [regex]::Replace($exprText,$pattern,[System.Text.RegularExpressions.MatchEvaluator]{ param($m) return 'expression DataFolder = "' + $pathValue + '"' })
    [IO.File]::WriteAllText($newFiles[$exprKey],$exprText,(New-Object System.Text.UTF8Encoding($false)))

    # Préservation par défaut : si Desktop a modifié, ajouté ou supprimé un élément, STOP.
    $collisions = New-Object 'System.Collections.Generic.List[string]'
    foreach ($rel in $oldHashes.Keys) {
        $dest = Path-In-Workspace $rel
        if (!(Test-Path -LiteralPath $dest -PathType Leaf) -or (Get-Sha256 $dest) -ne $oldHashes[$rel]) {
            $collisions.Add($rel)
        }
    }
    foreach ($rel in $newFiles.Keys) {
        $dest = Path-In-Workspace $rel
        if (!$oldHashes.ContainsKey($rel) -and (Test-Path -LiteralPath $dest)) { $collisions.Add($rel) }
    }
    foreach ($part in @('UrbanOps.Report','UrbanOps.SemanticModel')) {
        $dir = Join-Path $root $part
        if (Test-Path -LiteralPath $dir) {
            foreach ($item in (Get-ChildItem -LiteralPath $dir -Recurse -File -Force)) {
                $rel = $item.FullName.Substring($root.TrimEnd('\','/').Length).TrimStart('\','/').Replace('\','/')
                # Ignore only known Power BI workspace caches; do not discard real user modifications.
                if (!$oldHashes.ContainsKey($rel) -and !$newFiles.ContainsKey($rel) -and $rel -notmatch '/\.pbi/') {
                    $collisions.Add($rel)
                }
            }
        }
    }
    $conflicts = @($collisions | Select-Object -Unique)
    if ($conflicts.Count -gt 0 -and !$BackupAndReplace) {
        throw ("Modifications locales ou fichiers non gérés détectés (" + $conflicts.Count + ") : " +
            (($conflicts | Select-Object -First 5) -join ', ') +
            '. Rien n a été écrasé. Pour conserver une sauvegarde et remplacer volontairement : relancer avec -BackupAndReplace.')
    }
    if ($conflicts.Count -gt 0 -and $BackupAndReplace) {
        $backupStage = Join-Path $temporary 'previous-files'
        New-Item -ItemType Directory -Path $backupStage -Force | Out-Null
        $saved = @(@($oldHashes.Keys) + @($newFiles.Keys) + @($conflicts) | Select-Object -Unique)
        foreach ($rel in $saved) {
            $source = Path-In-Workspace $rel
            if (Test-Path -LiteralPath $source -PathType Leaf) {
                $backupTarget = Join-Path $backupStage ($rel.Replace('/',[IO.Path]::DirectorySeparatorChar))
                Copy-Into $source $backupTarget
            }
        }
        $backupFolder = Join-Path $stateDir 'backups'
        New-Item -ItemType Directory -Path $backupFolder -Force | Out-Null
        $backupZip = Join-Path $backupFolder ('UrbanOps-edits-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6) + '.zip')
        Compress-Archive -Path (Join-Path $backupStage '*') -DestinationPath $backupZip
        Write-Host "Modifications locales sauvegardées ici : $backupZip"
    }

    # Conserver les autres fichiers locaux data/ (bases SQLite, autres archives, etc.).
    foreach ($rel in $oldHashes.Keys) {
        if (!$newFiles.ContainsKey($rel)) {
            $dest = Path-In-Workspace $rel
            if (Test-Path -LiteralPath $dest -PathType Leaf) { Remove-Item -LiteralPath $dest -Force }
        }
    }
    $newHashes = [ordered]@{}
    foreach ($rel in ($newFiles.Keys | Sort-Object)) {
        $dest = Path-In-Workspace $rel
        Copy-Into $newFiles[$rel] $dest
        $newHashes[$rel] = Get-Sha256 $dest
    }
    New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    $newState = [ordered]@{schema=1;runId=$runId;headSha=$commitSha;capturedCount=[int]$datasetManifest.unique_collections;updatedUtc=[datetime]::UtcNow.ToString('o');files=$newHashes}
    $tempState = Join-Path $temporary 'state.json'
    [IO.File]::WriteAllText($tempState,($newState | ConvertTo-Json -Depth 10),[Text.Encoding]::UTF8)
    Copy-Item -LiteralPath $tempState -Destination $statePath -Force
    Write-Host "SUCCÈS : rapport synchronisé (run $runId ; $tableCount tables ; $($datasetManifest.unique_collections) capture(s))."
    Write-Host "Ouvre TOUJOURS : $(Join-Path $root 'UrbanOps.pbip')"
    if ([int]$datasetManifest.unique_collections -lt 2) { Write-Warning 'Une seule capture : les graphiques temporels ne peuvent pas démontrer de tendance.' }
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}