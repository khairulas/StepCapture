@echo off
REM Build a single-file Windows app: dist\StepCapture.exe
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt pyinstaller || goto :error
python -m PyInstaller --noconfirm --clean --noconsole --onefile --name StepCapture ^
  --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
  --collect-data docx run.py || goto :error
echo.
echo Done: %cd%\dist\StepCapture.exe
pause
exit /b 0
:error
echo.
echo Build failed. See the messages above.
pause
exit /b 1
