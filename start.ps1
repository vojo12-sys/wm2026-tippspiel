# WM 2026 Tippspiel - Hilfsbefehle
# Ausfuehren: .\start.ps1

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  WM 2026 Tippspiel - Schnellbefehle" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  [1] Server starten (Port 8080)" -ForegroundColor Green
Write-Host "  [2] Server beenden (alle Python-Prozesse)" -ForegroundColor Red
Write-Host "  [3] Demo-Daten simulieren (10 Spiele)" -ForegroundColor Yellow
Write-Host "  [4] Demo-Daten zuruecksetzen" -ForegroundColor Yellow
Write-Host "  [5] Aenderungen auf GitHub pushen" -ForegroundColor Magenta
Write-Host "  [q] Beenden" -ForegroundColor Gray
Write-Host ""

$choice = Read-Host "Auswahl"

switch ($choice) {
    "1" {
        $env:SPORTSDB_API_KEY="1"
        Write-Host "Server startet auf http://localhost:8080 ..." -ForegroundColor Green
        python -m uvicorn main:app --reload --port 8080
    }
    "2" {
        Write-Host "Beende alle Python-Prozesse..." -ForegroundColor Red
        taskkill /F /IM python.exe
    }
    "3" {
        Write-Host "Simuliere 10 Spiele..." -ForegroundColor Yellow
        python demo_data.py 10
    }
    "4" {
        Write-Host "Setze Demo-Daten zurueck..." -ForegroundColor Yellow
        python demo_data.py reset
    }
    "5" {
        $msg = Read-Host "Commit-Nachricht (Enter fuer Standard)"
        if ($msg -eq "") { $msg = "Update" }
        git add .
        git commit -m $msg
        git push
        Write-Host "Gepusht!" -ForegroundColor Green
    }
    "q" {
        Write-Host "Tschuess!" -ForegroundColor Gray
    }
    default {
        Write-Host "Unbekannte Auswahl." -ForegroundColor Red
    }
}
