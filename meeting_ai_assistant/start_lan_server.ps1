$python = "C:\Users\HITORI\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$port = 8042

Write-Host "Starting Meeting Copilot on LAN..."
Write-Host "Open this app from Android with your computer LAN IP, for example: http://192.168.x.x:$port/"

& $python -m uvicorn app.main:app --host 0.0.0.0 --port $port
