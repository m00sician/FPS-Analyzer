@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title FPS Analyzer - Setup

echo.
echo  ============================================================
echo   FPS Analyzer - Setup
echo  ============================================================
echo   Installs everything into this folder (.venv). Nothing is
echo   changed system-wide, except Python and FFmpeg if they are
echo   missing - and you are asked before either is installed.
echo.

rem ------------------------------------------------------------------
rem  1. Python 3.10 or newer
rem ------------------------------------------------------------------
rem  The check RUNS Python instead of using "where": a fresh Windows
rem  ships a fake python.exe that only opens the Microsoft Store.
set "PYCHECK=import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)"
set "PY="

py -3 -c "%PYCHECK%" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto have_python

python -c "%PYCHECK%" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto have_python

echo [1/5] Python 3.10+ was not found.
where winget >nul 2>nul
if errorlevel 1 goto no_python_manual

choice /c YN /m "      Install Python 3.12 now via winget"
if errorlevel 2 goto no_python_manual

winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements

rem  PATH is not refreshed inside this window, so look in the usual places.
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
if not defined PY if exist "%ProgramFiles%\Python312\python.exe" set "PY="%ProgramFiles%\Python312\python.exe""
if defined PY goto have_python

echo.
echo  Python was installed, but this window cannot see it yet.
echo  Close this window and run install.bat again.
goto fail

:no_python_manual
echo.
echo  Please install Python 3.10 or newer from
echo      https://www.python.org/downloads/
echo  (tick "Add python.exe to PATH" in the installer),
echo  then run install.bat again.
goto fail

:have_python
echo [1/5] Python found:
%PY% --version

rem ------------------------------------------------------------------
rem  2. Virtual environment
rem ------------------------------------------------------------------
set "VPY=.venv\Scripts\python.exe"
if exist "%VPY%" goto have_venv
echo [2/5] Creating the virtual environment (.venv) ...
%PY% -m venv .venv
if errorlevel 1 goto venv_failed
if not exist "%VPY%" goto venv_failed
goto venv_done

:venv_failed
echo  Could not create the virtual environment.
goto fail

:have_venv
echo [2/5] Virtual environment already exists - reusing it.

:venv_done

rem ------------------------------------------------------------------
rem  3. Python packages
rem ------------------------------------------------------------------
echo [3/5] Installing the Python packages ...
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto pip_failed
goto pip_done

:pip_failed
echo.
echo  Installing the packages failed. Check your internet connection
echo  and run install.bat again.
goto fail

:pip_done

rem ------------------------------------------------------------------
rem  4. FFmpeg
rem ------------------------------------------------------------------
if exist "ffmpeg.exe" goto ffmpeg_local
where ffmpeg >nul 2>nul
if not errorlevel 1 goto ffmpeg_path

echo [4/5] FFmpeg was not found.
where winget >nul 2>nul
if errorlevel 1 goto ffmpeg_manual
choice /c YN /m "      Install FFmpeg now via winget"
if errorlevel 2 goto ffmpeg_manual
winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
echo       FFmpeg is on the PATH from the NEXT window you open.
goto ffmpeg_done

:ffmpeg_manual
echo       Download it from https://ffmpeg.org/download.html and put
echo       ffmpeg.exe into this folder, or add it to your PATH.
echo       The tool does not work without it.
goto ffmpeg_done

:ffmpeg_local
echo [4/5] FFmpeg found: ffmpeg.exe in this folder.
goto ffmpeg_done

:ffmpeg_path
echo [4/5] FFmpeg found on the PATH.

:ffmpeg_done

rem ------------------------------------------------------------------
rem  5. PyTorch (optional)
rem ------------------------------------------------------------------
echo.
echo [5/5] PyTorch is OPTIONAL. It is only used for CUDA detection and
echo       the GPU blender - analysis and NVENC encoding work without
echo       it. It is a download of about 2.5 GB and needs an NVIDIA GPU.
"%VPY%" -c "import torch" >nul 2>nul
if not errorlevel 1 goto torch_present
choice /c YN /d N /t 30 /m "      Install PyTorch with CUDA (default: No after 30s)"
if errorlevel 2 goto torch_done
"%VPY%" -m pip install torch --index-url https://download.pytorch.org/whl/cu126
if errorlevel 1 echo       PyTorch could not be installed - the tool runs without it.
goto torch_done

:torch_present
echo       Already installed.

:torch_done

rem ------------------------------------------------------------------
rem  Self-test
rem ------------------------------------------------------------------
echo.
echo  Checking the installation ...
"%VPY%" -c "import PyQt6.QtWidgets, cv2, numpy, PIL, psutil; print('  Packages OK - OpenCV', cv2.__version__, '/ NumPy', numpy.__version__)"
if errorlevel 1 goto selftest_failed

where nvidia-smi >nul 2>nul
if errorlevel 1 echo   Note: no NVIDIA driver found - encoding falls back to the CPU (libx264).

echo.
echo  ============================================================
echo   Done. Start the tool with start.bat
echo  ============================================================
echo.
pause
exit /b 0

:selftest_failed
echo.
echo  A package could not be imported - see the message above.

:fail
echo.
echo  Setup did NOT finish.
echo.
pause
exit /b 1
