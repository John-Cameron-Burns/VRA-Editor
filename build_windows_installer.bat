@echo off
REM Builds the Windows installer completely from scratch: wipes any
REM existing venv/build state, reinstalls dependencies, rebuilds with
REM PyInstaller, then wraps it with Inno Setup.
REM
REM Produces: distributions\VRA_Editor_Setup_<version>.exe
REM
REM Requires Inno Setup 7 (ISCC.exe) -- see packaging\VRA_Editor.iss and
REM https://jrsoftware.org/isdl.php.
REM
REM If VRA Editor.exe is already running, PyInstaller's cleanup step will
REM fail with a "file in use" error -- close it first if that happens;
REM this script won't force-kill it for you (could discard unsaved edits
REM in an open record).

setlocal

cd /d "%~dp0"

echo === Cleaning previous build state ===
if exist ".venv" rmdir /s /q ".venv"
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo.
echo === Creating virtual environment ===
python -m venv .venv
if errorlevel 1 goto :error

echo.
echo === Installing dependencies ===
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo.
echo === Building with PyInstaller ===
".venv\Scripts\python.exe" -m PyInstaller packaging\VRA_Editor.spec --noconfirm
if errorlevel 1 goto :error

echo.
echo === Building installer with Inno Setup ===
set "ISCC=C:\Program Files\Inno Setup 7\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if not exist "%ISCC%" (
    for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do set "ISCC=%%I"
)
if not exist "%ISCC%" (
    echo.
    echo Inno Setup's ISCC.exe wasn't found in its usual install locations
    echo or on PATH. Install it from https://jrsoftware.org/isdl.php and
    echo re-run this script.
    exit /b 1
)

"%ISCC%" packaging\VRA_Editor.iss
if errorlevel 1 goto :error

echo.
echo === Done ===
echo Installer: distributions\
goto :eof

:error
echo.
echo *** Build FAILED -- see the error above. ***
exit /b 1
