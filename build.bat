@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title WireNote build

echo.
echo  ==============================
echo    WireNote - build + installer
echo  ==============================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python was not found on PATH. Install Python 3.10+ and try again.
    goto :fail
)

echo [1/4] Installing build requirements...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

echo.
echo [2/4] Generating icons...
python wirenote.py --make-icon assets
if errorlevel 1 goto :fail

echo.
echo [3/4] Building WireNote.exe (one-folder build so right-click launches are instant)...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
python -m PyInstaller --noconfirm --clean --windowed --onedir ^
    --name WireNote ^
    --icon assets\icon.ico ^
    --add-data "assets;assets" ^
    wirenote.py
if errorlevel 1 goto :fail

echo.
echo [4/4] Building installer...
call :findiscc
if not defined ISCC (
    echo     Inno Setup not found - installing it with winget...
    winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
    call :findiscc
)
if not defined ISCC (
    echo [X] Could not find ISCC.exe. Install Inno Setup 6 from https://jrsoftware.org/isdl.php and re-run.
    goto :fail
)
"%ISCC%" /Q installer.iss
if errorlevel 1 goto :fail

echo.
echo  Done!
echo    Portable app : dist\WireNote\WireNote.exe
for %%F in (installer\WireNote-Setup-*.exe) do echo    Installer    : %%F
echo.
pause
exit /b 0

:findiscc
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
exit /b 0

:fail
echo.
echo  Build failed - see the messages above.
pause
exit /b 1
