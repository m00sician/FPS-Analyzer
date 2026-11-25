@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto venv
python fps_analyzer_main.py
goto done
:venv
".venv\Scripts\python.exe" fps_analyzer_main.py
:done
if errorlevel 1 pause
