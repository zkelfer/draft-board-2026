@echo off
setlocal
REM ============================================================
REM  Draft Board 2026 - draft-day launcher
REM    run-draft.bat            start helper (manager "zach") + open board
REM    run-draft.bat reset      strip cached picks first, then start fresh
REM    run-draft.bat <name>     use a different Yahoo manager name
REM  Uses "py"/"python" (never "python3" - on Windows that's a Store stub).
REM ============================================================
cd /d "%~dp0"
set "ME=zach"
set "DO_RESET="
if /i "%~1"=="reset" (set "DO_RESET=1") else (if not "%~1"=="" set "ME=%~1")

REM find a working Python (py launcher first - immune to the Store stub)
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo Python not found - run setup.bat first.
  pause
  exit /b 1
)

if not exist "data_private" mkdir "data_private"

if defined DO_RESET (
  echo Stripping cached picks...
  %PY% pipeline\reset_cache.py
  echo.
)

REM if the helper is already up, don't start a second one (single instance!)
netstat -an | findstr ":8737 " | findstr /i LISTENING >nul 2>&1
if not errorlevel 1 (
  echo Helper already running on port 8737 - not starting another.
) else (
  echo Starting draft sync helper for manager "%ME%"...
  if defined DO_RESET (
    start "Draft Sync - room feed" cmd /k %PY% pipeline\toast_sync.py --me "%ME%" --reset
  ) else (
    start "Draft Sync - room feed" cmd /k %PY% pipeline\toast_sync.py --me "%ME%"
  )
  timeout /t 3 /nobreak >nul
)

echo Opening the board at http://127.0.0.1:8737/
start "" http://127.0.0.1:8737/
echo.
echo Leave the helper window open during the draft.
echo On the board: leave "League name" BLANK, set League -^> Teams and Pick,
echo and make sure the Sync button is ON (it stays off after "Clear this draft").
endlocal
