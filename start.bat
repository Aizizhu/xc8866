@echo off
REM 设置代理（可根据需要修改或注释）
set http_proxy=http://127.0.0.1:7890
set https_proxy=http://127.0.0.1:7890
set no_proxy=localhost,127.0.0.1,::1

chcp 65001 >nul
cd /d %~dp0

REM 输入起始页链接和爬取总页数
set /p start_url=请输入起始页链接（如 https://xc8866.com/topics/tag/193?page=1）:
set /p total_pages=请输入总共爬取页数（数字）:
set /p threads=请输入线程数（默认6，回车则6）:

if "%threads%"=="" (
    set threads=6
)

REM 激活虚拟环境
call venv\Scripts\activate

REM 启动爬虫程序
python main.py --start-url %start_url% --total-pages %total_pages% --threads %threads%

pause
