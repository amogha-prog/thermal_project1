# TIOS2 Clean Startup Script
# Run this script instead of starting services manually
# Usage: Right-click → "Run with PowerShell"

Write-Host "`n=== TIOS2 Startup ===" -ForegroundColor Cyan

# Kill any existing node/python processes
Write-Host "[1/4] Clearing old processes..." -ForegroundColor Yellow
Get-Process node, python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2

# Kill anything on used ports
$ports = @(4000, 9998, 9999, 14555, 14556, 14560)
foreach ($port in $ports) {
    netstat -ano | Select-String ":$port\s" | ForEach-Object {
        $parts = $_ -split '\s+'
        $procId = $parts[-1]
        if ($procId -match '^\d+$' -and [int]$procId -gt 0) {
            taskkill /F /PID $procId 2>$null | Out-Null
        }
    }
}
Write-Host "[1/4] Ports cleared." -ForegroundColor Green

# Start Node.js backend
Write-Host "[2/4] Starting Node.js backend (port 4000)..." -ForegroundColor Yellow
$backend = Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'd:\aeroluna thermal project\tios2\backend'; node src/server.js" -PassThru
Start-Sleep 3
Write-Host "[2/4] Backend started (PID $($backend.Id))" -ForegroundColor Green

# Start Frontend
Write-Host "[3/4] Starting Frontend (port 5173)..." -ForegroundColor Yellow
$frontend = Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'd:\aeroluna thermal project\tios2\frontend'; npm run dev" -PassThru
Start-Sleep 2
Write-Host "[3/4] Frontend started (PID $($frontend.Id))" -ForegroundColor Green

# Start Drone Bridge
Write-Host "[4/5] Starting MAVLink bridge (UDP:14555 -> 14556)..." -ForegroundColor Yellow
$bridge = Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'd:\aeroluna thermal project\tios2\backend'; python -u drone_bridge.py" -PassThru
Write-Host "[4/5] Bridge started (PID $($bridge.Id))" -ForegroundColor Green

# Start Analysis Pipeline
Write-Host "[5/5] Starting Hotspot Detection Pipeline..." -ForegroundColor Yellow
$pipeline = Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'd:\aeroluna thermal project\tios2\backend\python'; python -u main.py --simulation" -PassThru
Write-Host "[5/5] Pipeline started (PID $($pipeline.Id))" -ForegroundColor Green

Write-Host "`n=== All services started ===" -ForegroundColor Cyan
Write-Host "Dashboard: http://localhost:5173" -ForegroundColor White
Write-Host "Backend:   http://localhost:4000" -ForegroundColor White
Write-Host "`nH12 OpeniLink UDP output must be set to:" -ForegroundColor Yellow
Write-Host "  IP: 192.168.144.200  Port: 14555" -ForegroundColor White
Write-Host "`nPress any key to exit this window (services keep running)..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
