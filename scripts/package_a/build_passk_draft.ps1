param(
    [string]$RunId = "20260415T120000Z",
    [string]$RunRoot = "data/mcu-bench/runs",
    [string]$ValidatedDir = "data/validated",
    [string]$SynthesisDir = "data/synthesis"
)

$ErrorActionPreference = "Stop"

$runDir = Join-Path -Path $RunRoot -ChildPath $RunId
$topKPath = Join-Path -Path $runDir -ChildPath "topk_results.jsonl"

if (-not (Test-Path -Path $topKPath)) {
    throw "Missing top-k results file: $topKPath"
}

$rows = Get-Content -Path $topKPath |
    Where-Object { $_.Trim().Length -gt 0 } |
    ForEach-Object { $_ | ConvertFrom-Json }

$total = [int]$rows.Count
if ($total -eq 0) {
    throw "No records found in top-k results file: $topKPath"
}

$kValues = @(1, 3, 5)
$metrics = @()
$csvRows = @()

foreach ($k in $kValues) {
    $hits = 0

    foreach ($row in $rows) {
        $topPages = @($row.top_k | Select-Object -First $k | Select-Object -ExpandProperty page_id)
        if ($topPages -contains $row.expected_page_id) {
            $hits++
        }
    }

    $passRate = [Math]::Round(($hits / [double]$total), 4)

    $metrics += [PSCustomObject]@{
        metric = "PASS@$k"
        method = "retrieval_fixture_v1"
        pass_count = [int]$hits
        total = $total
        pass_rate = $passRate
        source = "retrieval_topk_proxy"
    }

    $csvRows += [PSCustomObject]@{
        metric_scope = "draft"
        method = "retrieval_fixture_v1"
        k = $k
        pass_count = [int]$hits
        total = $total
        pass_rate = $passRate
        data_mode = "retrieval_proxy_only"
    }
}

$validatedCount = if (Test-Path -Path $ValidatedDir) {
    (Get-ChildItem -Path $ValidatedDir -Recurse -File -Filter "*.json" -ErrorAction SilentlyContinue).Count
} else {
    0
}

$synthesisCount = if (Test-Path -Path $SynthesisDir) {
    (Get-ChildItem -Path $SynthesisDir -Recurse -File -Filter "*.json" -ErrorAction SilentlyContinue).Count
} else {
    0
}

$summary = [PSCustomObject]@{
    run_id = $RunId
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    sample_count = $total
    scoring_mode = if ($validatedCount -gt 0 -or $synthesisCount -gt 0) { "mixed" } else { "retrieval_proxy_only" }
    available_inputs = [PSCustomObject]@{
        validated_json_count = [int]$validatedCount
        synthesis_json_count = [int]$synthesisCount
    }
    metrics = $metrics
    notes = @(
        "Draft PASS@K uses expected page retrieval hit as proxy signal.",
        "Replace with validated/synthesis-derived PASS@K when Package B/C artifacts arrive."
    )
}

$jsonPath = Join-Path -Path $runDir -ChildPath "passk_summary_draft.json"
$csvPath = Join-Path -Path $runDir -ChildPath "passk_summary_draft.csv"
$notesPath = Join-Path -Path $runDir -ChildPath "scoring_notes.md"

$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $jsonPath -Encoding utf8
$csvRows | ConvertTo-Csv -NoTypeInformation | Set-Content -Path $csvPath -Encoding utf8

$notes = @(
    "# Scoring Notes (Draft)",
    "",
    "Run ID: $RunId",
    "",
    "Mode: retrieval_proxy_only (validated/synthesis artifacts not present)",
    "",
    "What is measured:",
    "- PASS@K proxy using whether expected benchmark page appears in retrieval top-K.",
    "",
    "What is not measured yet:",
    "- Address-level correctness of synthesized code against SVD.",
    "- CoVe-corrected extraction quality from Package B.",
    "",
    "Upgrade path when upstream artifacts arrive:",
    "1. Map each benchmark ID to validated JSON and synthesis outputs.",
    "2. Compute true PASS@K using generated addresses versus SVD ground truth.",
    "3. Keep this draft as historical baseline in paper appendix."
)

$notes | Set-Content -Path $notesPath -Encoding utf8

Write-Output "PASS@K draft JSON: $($jsonPath -replace '\\', '/')"
Write-Output "PASS@K draft CSV: $($csvPath -replace '\\', '/')"
Write-Output "Scoring notes: $($notesPath -replace '\\', '/')"
