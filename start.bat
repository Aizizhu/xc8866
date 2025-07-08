@echo off
set http_proxy=http://127.0.0.1:7890
set https_proxy=http://127.0.0.1:7890
set no_proxy=localhost,127.0.0.1,::1

chcp 65001 >nul
cd /d %~dp0

set /p start_url=请输入起始页链接（如 https://xc8866.com/forum-23-1.htm?tagids=151_0_0_0）:
set /p total_pages=请输入总共爬取页数（数字）:

call venv\Scripts\activate

python main.py --start-url %start_url% --total-pages %total_pages%

pause
