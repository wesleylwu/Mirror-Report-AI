New-Item -ItemType File -Path "$PSScriptRoot\STOP" -Force | Out-Null
Write-Host "Stop signal sent. Current API call will end after the next chunk."
