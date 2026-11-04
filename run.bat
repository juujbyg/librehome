@echo off
rem Launch LibreHome on Windows. Needs only Python 3.10+ (python.org or the Microsoft Store).
cd /d "%~dp0"
set PYTHONPATH=src
where py >nul 2>nul && (py -3 -m librehome serve %* & goto :eof)
python -m librehome serve %*
