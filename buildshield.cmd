@echo off
rem BuildShield launcher for Windows (CMD / PowerShell).
rem Usage: buildshield start | stop | restart | status | monitor | doctor ...

setlocal
set "PYTHON="

where py >nul 2>nul
if not errorlevel 1 set "PYTHON=py -3"

if not defined PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON=python"
)

if not defined PYTHON (
    echo BuildShield launcher needs Python 3, but it was not found on PATH.
    echo Install it from https://www.python.org/downloads/ and try again.
    exit /b 1
)

%PYTHON% "%~dp0tools\buildshield_launcher.py" %*
exit /b %ERRORLEVEL%
