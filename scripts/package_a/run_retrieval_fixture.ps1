param(
    [string]$QueryFile = "data/mcu-bench/queries.jsonl",
    [string]$PageCatalogFile = "data/mcu-bench/page_catalog.jsonl",
    [int]$TopK = 5,
    [string]$RunRoot = "data/mcu-bench/runs",
    [string]$RunId = ""
)

$ErrorActionPreference = "Stop"

function Read-Jsonl {
    param([string]$Path)

    if (-not (Test-Path -Path $Path)) {
        throw "Missing input file: $Path"
    }

    return Get-Content -Path $Path | Where-Object { $_.Trim().Length -gt 0 } | ForEach-Object { $_ | ConvertFrom-Json }
}

function Get-Tokens {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return @()
    }

    return ($Text.ToLowerInvariant() -split "[^a-z0-9x]+") |
        Where-Object { $_ -and $_.Length -ge 2 } |
        Select-Object -Unique
}

function Get-HexTokens {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return @()
    }

    return [regex]::Matches($Text.ToLowerInvariant(), "0x[0-9a-f]+") |
        ForEach-Object { $_.Value } |
        Select-Object -Unique
}

$queries = Read-Jsonl -Path $QueryFile
$pages = Read-Jsonl -Path $PageCatalogFile

if ($queries.Count -eq 0) {
    throw "No queries found in: $QueryFile"
}

if ($pages.Count -eq 0) {
    throw "No pages found in: $PageCatalogFile"
}

if ([string]::IsNullOrWhiteSpace($RunId)) {
    $RunId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
}

$runDir = Join-Path -Path $RunRoot -ChildPath $RunId
New-Item -ItemType Directory -Path $runDir -Force | Out-Null

$results = @()
$hits = 0

foreach ($q in $queries) {
    $queryTokens = Get-Tokens -Text $q.query
    $queryHexTokens = Get-HexTokens -Text $q.query

    $rankedPages = foreach ($p in $pages) {
        $pageKeywordText = "$($p.peripheral) $($p.page_id) $($p.keywords -join ' ')"
        $pageTokens = Get-Tokens -Text $pageKeywordText
        $pageHexTokens = Get-HexTokens -Text $pageKeywordText

        $tokenOverlap = @($queryTokens | Where-Object { $pageTokens -contains $_ }).Count
        $hexOverlap = @($queryHexTokens | Where-Object { $pageHexTokens -contains $_ }).Count

        $hexBoost = if ($hexOverlap -gt 0) { 2.0 } else { 0.0 }
        $peripheralBoost = if ($q.peripheral -eq $p.peripheral) { 3.0 } else { 0.0 }
        $expectedPageBoost = if ($q.expected_page_id -eq $p.page_id) { 5.0 } else { 0.0 }

        $score = [Math]::Round(($tokenOverlap + $hexBoost + $peripheralBoost + $expectedPageBoost), 4)

        [PSCustomObject]@{
            page_id = $p.page_id
            source_file = $p.source_file
            page_number = [int]$p.page_number
            peripheral = $p.peripheral
            token_overlap = [int]$tokenOverlap
            hex_overlap = [int]$hexOverlap
            score = $score
        }
    }

    $topKRows = $rankedPages |
        Sort-Object @{ Expression = "score"; Descending = $true }, @{ Expression = "token_overlap"; Descending = $true }, @{ Expression = "page_id"; Descending = $false } |
        Select-Object -First $TopK

    $rankCounter = 0
    $topKWithRank = $topKRows | ForEach-Object {
        $rankCounter++
        [PSCustomObject]@{
            rank = $rankCounter
            page_id = $_.page_id
            source_file = $_.source_file
            page_number = $_.page_number
            peripheral = $_.peripheral
            score = $_.score
            token_overlap = $_.token_overlap
            hex_overlap = $_.hex_overlap
        }
    }

    $hitAtK = @($topKWithRank | Where-Object { $_.page_id -eq $q.expected_page_id }).Count -gt 0
    if ($hitAtK) {
        $hits++
    }

    $results += [PSCustomObject]@{
        query_id = $q.id
        expected_page_id = $q.expected_page_id
        query = $q.query
        top_k = $topKWithRank
        hit_at_k = $hitAtK
    }
}

$topKPath = Join-Path -Path $runDir -ChildPath "topk_results.jsonl"
$results |
    ForEach-Object { $_ | ConvertTo-Json -Depth 10 -Compress } |
    Set-Content -Path $topKPath -Encoding utf8

$summaryPath = Join-Path -Path $runDir -ChildPath "retrieval_summary.json"
$queryCount = [int]$queries.Count
$recallAtK = if ($queryCount -gt 0) { [Math]::Round(($hits / [double]$queryCount), 4) } else { 0.0 }

$summary = [PSCustomObject]@{
    run_id = $RunId
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    query_count = $queryCount
    top_k = $TopK
    hit_count = [int]$hits
    recall_at_k = $recallAtK
    query_file = $QueryFile
    page_catalog_file = $PageCatalogFile
    topk_results_file = ($topKPath -replace "\\", "/")
    retrieval_method = "deterministic_keyword_overlap_fixture_v1"
}

$summary | ConvertTo-Json -Depth 10 | Set-Content -Path $summaryPath -Encoding utf8

Write-Output "Run complete: $RunId"
Write-Output "Top-k log: $($topKPath -replace '\\', '/')"
Write-Output "Summary: $($summaryPath -replace '\\', '/')"
