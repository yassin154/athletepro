@echo off
echo ============================================
echo   AthléPro — Sync World Athletics
echo ============================================
echo.

cd /d "%~dp0"

echo [1/4] Test connexion World Athletics...
python sync_worldathletics.py --test
if %errorlevel% neq 0 (
    echo ERREUR lors du test - vérifiez votre connexion internet
    pause
    exit /b 1
)

echo.
echo [2/4] Synchronisation de tous les athlètes...
python sync_worldathletics.py

echo.
echo [3/4] Envoi sur GitHub...
git add resultats.json wa_ids.json wa_rankings.json
git diff --staged --quiet && (
    echo Aucun nouveau résultat a envoyer
) || (
    git commit -m "Sync WA %date:~6,4%-%date:~3,2%-%date:~0,2%"
    git push
    echo Résultats envoyés sur GitHub avec succès!
)

echo.
echo [4/4] Terminé!
pause
