cd "$PSScriptRoot"
$env:ANTHROPIC_API_KEY = (Get-Content .env.local | Select-String "ANTHROPIC_API_KEY" | ForEach-Object { $_ -replace ".*=", "" }).Trim()
cd pipeline

$images = @("IMG_9688", "IMG_9689", "IMG_9691", "IMG_9692", "IMG_9697")

foreach ($img in $images) {
    Write-Host "=== Processing $img ===" -ForegroundColor Cyan
    python JSONgen.py --sonnet "..\input\$img.JPG" "..\output\$img.json"
}

Write-Host "Done." -ForegroundColor Green
