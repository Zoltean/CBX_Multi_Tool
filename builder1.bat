@echo off
echo Starting build process for CBX_Multi_Tool...

:: Переключаемся на диск E:
E:
if %ERRORLEVEL% neq 0 (
    echo Error: Unable to switch to E: drive.
    pause
    exit /b %ERRORLEVEL%
)

:: Переходим в папку проекта
cd \Soft\CBX_Multi_Tool
if %ERRORLEVEL% neq 0 (
    echo Error: Directory E:\Soft\CBX_Multi_Tool not found.
    pause
    exit /b %ERRORLEVEL%
)

:: Активируем виртуальное окружение
call .venv\Scripts\activate
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to activate virtual environment.
    pause
    exit /b %ERRORLEVEL%
)

:: Запускаем PyInstaller
echo Running PyInstaller...
pyinstaller --onefile --icon=0.ico --noupx ^
--add-binary "dlls\api-ms-win-core-path-l1-1-0.dll;." ^
main.py > build_log.txt 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: PyInstaller failed. Check build_log.txt for details.
) else (
    echo Build completed successfully. Check dist\main.exe.
)
pause