@echo off
setlocal EnableExtensions
title NeuroGenUI setup
cd /d "%~dp0"
echo.
echo  NeuroGenUI setup
echo  ================

rem ---- 1. Python 3.11 - 3.13 ------------------------------------------------
set "PY="
for %%V in (3.13 3.12 3.11) do call :try_py %%V
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo  [x] Python 3.11, 3.12 or 3.13 is required. Install it from https://www.python.org/downloads/ and run setup.bat again.
  goto :fail
)
echo  [ok] Using %PY%

rem ---- 2. Virtual environment + packages ------------------------------------
if not exist "backend\.venv\Scripts\python.exe" (
  echo  [..] Creating backend\.venv
  %PY% -m venv backend\.venv || goto :fail
)
set "VPY=backend\.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip >nul
echo  [..] Installing Python packages
"%VPY%" -m pip install -r backend\requirements.txt || goto :fail
echo  [..] Installing local OCR (optional, improves sketch text detection)
"%VPY%" -m pip install -r backend\requirements-ocr.txt >nul 2>&1
if errorlevel 1 (echo  [!] Local OCR could not be installed: sketches fall back to the vision model for text) else (echo  [ok] Local OCR installed)

rem ---- 3. Browser for validation (Edge preferred) ---------------------------
set "EDGE_A=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
set "EDGE_B=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
set "HAS_EDGE="
if exist "%EDGE_A%" set "HAS_EDGE=1"
if exist "%EDGE_B%" set "HAS_EDGE=1"
if defined HAS_EDGE (
  echo  [ok] Microsoft Edge found: validation will use it
) else (
  echo  [..] Edge not found: installing Playwright Chromium
  "%VPY%" -m playwright install chromium || goto :fail
)

rem ---- 4. Settings ----------------------------------------------------------
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo  [!] Created .env - put your OPENAI_API_KEY in it
)

rem ---- 5. Frontend (prebuilt dist is shipped) --------------------------------
if exist "frontend\dist\index.html" (
  echo  [ok] Frontend build present
) else (
  where node >nul 2>&1
  if errorlevel 1 (
    echo  [!] frontend\dist is missing and Node.js is not installed - the API still works at http://localhost:8200/docs
  ) else (
    echo  [..] Building the frontend
    pushd frontend
    call npm install
    call npm run build
    popd
  )
)

echo.
echo  Setup complete. Start NeuroGenUI with run.bat
echo.
pause
exit /b 0

:try_py
if defined PY exit /b 0
py -%1 -c "import sys" >nul 2>&1 && set "PY=py -%1"
exit /b 0

:fail
echo.
echo  Setup failed. See the messages above.
pause
exit /b 1
