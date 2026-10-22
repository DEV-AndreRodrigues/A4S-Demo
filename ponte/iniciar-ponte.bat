@echo off
REM Windows: dê dois cliques para iniciar a ponte.
cd /d "%~dp0"
if not exist ponte.config.json (
  echo Falta o arquivo ponte.config.json nesta pasta. Peca ao time de Produto.
  pause
  exit /b 1
)
where py >nul 2>nul && (py -3 ponte_smart_safety.py) || (python ponte_smart_safety.py)
pause
