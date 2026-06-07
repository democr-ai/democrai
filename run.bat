@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PYTHON_CMD="

call :find_python

if not defined PYTHON_CMD (
    call :install_python
    call :find_python
)

if defined PYTHON_CMD (
    call %PYTHON_CMD% "%SCRIPT_DIR%run.py" %*
    exit /b %errorlevel%
)

echo Python 3.12+ not found. 1>&2
exit /b 1

:find_python
py -3.12 -c "import sys" >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3.12"
    exit /b 0
)
python -c "import sys; raise SystemExit(sys.version_info < (3, 12))" >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=python"
    exit /b 0
)
exit /b 1

:install_python
echo Python 3.12+ not found. Trying to install Python 3.12...
where winget >nul 2>nul
if not %errorlevel%==0 (
    echo winget is required to install Python automatically on Windows. 1>&2
    exit /b 1
)
winget install --id Python.Python.3.12 -e --source winget
exit /b %errorlevel%
