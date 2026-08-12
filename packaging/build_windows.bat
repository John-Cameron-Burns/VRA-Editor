@echo off
REM Full Windows packaging pipeline: venv/deps -> PyInstaller -> Inno Setup.
REM Run from anywhere -- this cd's to the repo root itself (this file's
REM own parent's parent), so double-clicking it in Explorer works the
REM same as running it from any shell.
REM
REM Produces:
REM   dist\VRA Editor\VRA Editor.exe        (portable app -- see VRA_Editor.spec)
REM   installer_output\VRA_Editor_Setup_<version>.exe   (installer -- see VRA_Editor.iss)
REM
REM If VRA Editor.exe is already running, the PyInstaller step will fail
REM with a PermissionError trying to clean out dist\VRA Editor -- this
REM script does not try to detect or close that for you, since force-
REM killing it could discard an open record's unsaved edits. Close it
REM yourself first if you hit that.

setlocal

cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :error
)

echo.
echo === Installing/updating dependencies ===
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
    echo or on PATH -- skipping the installer step. The portable app is
    echo still available in dist\VRA Editor\.
    goto :eof
)

"%ISCC%" packaging\VRA_Editor.iss
if errorlevel 1 goto :error

echo.
echo === Done ===
echo Portable app:  dist\VRA Editor\VRA Editor.exe
echo Installer:     installer_output\
goto :eof

:error
echo.
echo *** Build FAILED -- see the error above. ***
exit /b 1
