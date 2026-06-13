# WM 2026 Tippspiel - Hilfsbefehle
# Ausfuehren: .\start.ps1

function Show-Menu {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  WM 2026 Tippspiel - Schnellbefehle" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  --- Server ---" -ForegroundColor DarkGray
    Write-Host "  [1] Server starten (Port 8080)" -ForegroundColor Green
    Write-Host "  [2] Server beenden (alle Python-Prozesse)" -ForegroundColor Red
    Write-Host "  [3] Browser oeffnen (http://localhost:8080)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  --- Python ---" -ForegroundColor DarkGray
    Write-Host "  [4] Python-Version anzeigen" -ForegroundColor White
    Write-Host "  [5] Installierte Pakete anzeigen (pip list)" -ForegroundColor White
    Write-Host "  [6] Abhaengigkeiten installieren (requirements.txt)" -ForegroundColor White
    Write-Host ""
    Write-Host "  --- Daten ---" -ForegroundColor DarkGray
    Write-Host "  [7] Demo-Daten simulieren (10 Spiele)" -ForegroundColor Yellow
    Write-Host "  [8] Demo-Daten zuruecksetzen" -ForegroundColor Yellow
    Write-Host "  [9] Spielplan importieren (import_schedule.py)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  --- Backup ---" -ForegroundColor DarkGray
    Write-Host " [12] Produktions-Backup erstellen (CSV)" -ForegroundColor Green
    Write-Host ""
    Write-Host "  --- Git ---" -ForegroundColor DarkGray
    Write-Host " [10] Git-Status anzeigen" -ForegroundColor Magenta
    Write-Host " [11] Aenderungen auf GitHub pushen" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "  [q] Beenden" -ForegroundColor Gray
    Write-Host ""
}

do {
    Show-Menu
    $choice = Read-Host "Auswahl"

    switch ($choice) {
        "1" {
            $env:SPORTSDB_API_KEY="1"
            Write-Host "Server startet auf http://localhost:8080 ..." -ForegroundColor Green
            python -m uvicorn main:app --reload --port 8080
        }
        "2" {
            Write-Host "Beende alle Python-Prozesse..." -ForegroundColor Red
            taskkill /F /IM python.exe 2>$null
            Write-Host "Erledigt." -ForegroundColor Green
        }
        "3" {
            Write-Host "Oeffne Browser..." -ForegroundColor Cyan
            Start-Process "http://localhost:8080"
        }
        "4" {
            Write-Host ""
            python --version
            Write-Host ""
        }
        "5" {
            Write-Host ""
            pip list
            Write-Host ""
        }
        "6" {
            Write-Host "Installiere Abhaengigkeiten..." -ForegroundColor White
            pip install -r requirements.txt
        }
        "7" {
            Write-Host "Simuliere 10 Spiele..." -ForegroundColor Yellow
            python demo_data.py 10
        }
        "8" {
            Write-Host "Setze Demo-Daten zurueck..." -ForegroundColor Yellow
            python demo_data.py reset
        }
        "9" {
            Write-Host "Importiere Spielplan..." -ForegroundColor Yellow
            python import_schedule.py
            Write-Host "Erledigt." -ForegroundColor Green
        }
        "10" {
            Write-Host ""
            git status
            Write-Host ""
        }
        "11" {
            $msg = Read-Host "Commit-Nachricht (Enter fuer Standard)"
            if ($msg -eq "") { $msg = "Update" }
            git add .
            git commit -m $msg
            git push
            Write-Host "Gepusht!" -ForegroundColor Green
        }
        "12" {
            $envFile = ".env"
            $dbUrl = ""

            # URL aus .env lesen falls vorhanden
            if (Test-Path $envFile) {
                $line = Get-Content $envFile | Where-Object { $_ -match "^DATABASE_URL=" }
                if ($line) {
                    $dbUrl = $line -replace "^DATABASE_URL=", ""
                }
            }

            # Falls nicht gefunden: abfragen und speichern
            if ($dbUrl -eq "") {
                Write-Host "Keine DATABASE_URL in .env gefunden." -ForegroundColor Yellow
                $dbUrl = Read-Host "Render PostgreSQL URL eingeben"
                if ($dbUrl -ne "") {
                    Add-Content -Path $envFile -Value "DATABASE_URL=$dbUrl" -Encoding utf8
                    Write-Host "URL in .env gespeichert." -ForegroundColor Green
                }
            }

            if ($dbUrl -ne "") {
                Write-Host "Erstelle Backup..." -ForegroundColor Green
                .venv/Scripts/python.exe backup_data.py $dbUrl
            } else {
                Write-Host "Abgebrochen - keine URL angegeben." -ForegroundColor Red
            }
        }
        "q" {
            Write-Host "Tschuess!" -ForegroundColor Gray
        }
        default {
            Write-Host "Unbekannte Auswahl." -ForegroundColor Red
        }
    }

    if ($choice -ne "q" -and $choice -ne "1") {
        Write-Host ""
        Read-Host "Enter druecken um fortzufahren"
    }

} while ($choice -ne "q")
