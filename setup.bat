@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM  Draft Board 2026 - one-time machine setup
REM  Verifies/install Python, creates data_private\, checks the
REM  clone, and prints the remaining browser-only steps.
REM  Safe to re-run any time.
REM ============================================================
cd /d "%~dp0"
echo.
echo === Draft Board 2026 setup ===
echo.

REM --- 1) find a working Python (the "python3" alias is often a
REM        Microsoft Store stub that just opens the Store - never use it)
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo Python not found - installing via winget...
  winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
  py -3 --version >nul 2>&1
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  echo.
  echo   Could not find or install Python automatically.
  echo   Install it from https://www.python.org/downloads/ ^(check "Add to PATH"^),
  echo   then run this script again.
  goto :done
)
for /f "tokens=*" %%v in ('%PY% --version') do echo Python OK: %%v  ^(command: %PY%^)

REM --- 2) data_private\ is gitignored, so a fresh clone lacks it;
REM        the helper caches picks there
if not exist "data_private" (
  mkdir "data_private"
  echo Created data_private\
) else (
  echo data_private\ present
)

REM --- 3) sanity-check the clone
if exist "dist\index.html" (echo Board build present: dist\index.html) else (echo WARNING: dist\index.html missing - re-clone or run: cd pipeline ^&^& %PY% build.py)
if exist "pipeline\toast_sync.py" (echo Draft-day helper present: pipeline\toast_sync.py) else (echo WARNING: pipeline\toast_sync.py missing - bad clone?)

REM --- 4) stdlib smoke test for the helper
%PY% -c "import sqlite3, json, threading; from http.server import ThreadingHTTPServer" >nul 2>&1
if errorlevel 1 (echo WARNING: Python stdlib check failed) else (echo Helper dependency check OK ^(stdlib only^))

echo.
echo === Remaining steps (browser, once) ===
echo  1. Chrome -^> chrome://extensions -^> Developer mode -^> Load unpacked -^> pick this repo's extension\ folder
echo  2. Move your prep: old machine board -^> League -^> Copy state; here -^> Paste state
echo.
echo === Draft day ===
echo  Double-click run-draft.bat  (starts the pick-sync helper and opens the board)
echo  Before a real draft: run a Yahoo mock and confirm the status line shows "room:" / "helper:" picks.
echo.

:done
REM pause only when double-clicked (not when run from a terminal)
echo %cmdcmdline% | find /i "%~f0" >nul && pause
endlocal
