@echo off
setlocal

REM Optional proxy settings (edit or comment out if not needed)
set http_proxy=http://127.0.0.1:7890
set https_proxy=http://127.0.0.1:7890
set no_proxy=localhost,127.0.0.1,::1

chcp 65001 >nul
cd /d "%~dp0"

REM Input start URL and crawl options
set /p start_url=Enter start URL (example: https://xc8866.com/topics/tag/193?page=1): 
set /p total_pages=Enter total pages to crawl (number): 
set /p threads=Enter thread count (default 6): 

if "%threads%"=="" set threads=6

if "%start_url%"=="" (
    echo [ERROR] start_url is empty.
    goto :end
)

if "%total_pages%"=="" (
    echo [ERROR] total_pages is empty.
    goto :end
)

REM Activate venv when available, otherwise use system python
if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) else (
    echo [WARN] venv\Scripts\activate.bat not found, using system python.
)

python main.py --start-url "%start_url%" --total-pages "%total_pages%" --threads "%threads%"

:end
pause
endlocal
