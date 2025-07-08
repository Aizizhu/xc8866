@echo off
set no_proxy=localhost,127.0.0.1,::1
call .\venv\Scripts\activate
start "" /B python app.py
timeout /t 3 /nobreak > nul
start "" http://127.0.0.1:5000/
pause
