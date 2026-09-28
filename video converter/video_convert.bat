@echo off
where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw "%~dp0video_convert.py"
) else (
    python "%~dp0video_convert.py"
)
