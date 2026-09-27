@echo off
setlocal
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean YGT.spec
if errorlevel 1 exit /b 1
echo Build complete: dist\YGT\YGT.exe
echo Distribute the entire dist\YGT folder.
