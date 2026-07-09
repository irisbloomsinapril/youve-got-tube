@echo off
REM ============================================
REM  YGT (You've Got Tube) - Windows build script
REM  Run this once on the machine that builds the exe (April's PC).
REM  Python is only needed for building - not needed by people who
REM  receive the finished YGT.exe.
REM
REM  How to use:
REM   1) Put app.py, requirements.txt, and ffmpeg.exe in this folder
REM      (get ffmpeg.exe from https://www.gyan.dev/ffmpeg/builds/
REM       "release essentials" build, copy bin\ffmpeg.exe here)
REM   2) (optional) put ygt.ico in this folder to use it as the exe icon
REM   3) Double-click build.bat
REM   4) dist\YGT.exe will be created - share only that file
REM ============================================

setlocal

echo [1/4] Installing required packages...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo [ERROR] pip upgrade failed. Is Python installed and on PATH?
    echo Try running "python --version" in this window to check.
    echo.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install requirements.txt packages.
    echo.
    pause
    exit /b 1
)

python -m pip install pyinstaller
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install pyinstaller.
    echo.
    pause
    exit /b 1
)

if not exist ffmpeg.exe (
    echo.
    echo [WARNING] ffmpeg.exe was not found in this folder.
    echo mp4 merging / subtitles / mp3 conversion will not work without it.
    echo Get it from https://www.gyan.dev/ffmpeg/builds/ ("release essentials"),
    echo copy bin\ffmpeg.exe into this folder, then run this script again.
    echo.
    pause
)

if not exist ygt.ico (
    echo [INFO] ygt.ico not found - building with the default icon.
    echo To use your logo as the exe icon, convert ygt_logo.png to ygt.ico
    echo and place it in this folder, then run this script again.
)

echo [2/4] Cleaning previous build...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q YGT.spec 2>nul

echo [3/4] Building exe... (this can take a few minutes)
set ICON_OPT=
if exist ygt.ico set ICON_OPT=--icon "ygt.ico"

set DATA_OPT=
if exist ygt_logo.png set DATA_OPT=--add-data "ygt_logo.png;."

REM Use "python -m PyInstaller" instead of the bare "pyinstaller" command.
REM The pyinstaller.exe launcher script can end up in a Scripts folder that
REM is not on PATH, which makes the bare command fail silently. Calling it
REM as a module through python always works regardless of PATH.
if exist ffmpeg.exe (
    python -m PyInstaller --noconfirm --onefile --windowed --name "YGT" %ICON_OPT% %DATA_OPT% --add-binary "ffmpeg.exe;." app.py
) else (
    python -m PyInstaller --noconfirm --onefile --windowed --name "YGT" %ICON_OPT% %DATA_OPT% app.py
)

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed. See the messages above for details.
    echo.
    pause
    exit /b 1
)

if not exist "dist\YGT.exe" (
    echo.
    echo [ERROR] Build finished but dist\YGT.exe was not created. Something went wrong above.
    echo.
    pause
    exit /b 1
)

echo [4/4] Done!
echo.
echo dist\YGT.exe has been created.
echo Share only that one file - people who receive it do not need Python installed.
echo.
pause
