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
--add-binary "dlls\api-ms-win-core-console-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-datetime-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-debug-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-errorhandling-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-file-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-file-l1-2-0.dll;." ^
--add-binary "dlls\api-ms-win-core-file-l2-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-handle-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-heap-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-interlocked-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-libraryloader-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-localization-l1-2-0.dll;." ^
--add-binary "dlls\api-ms-win-core-memory-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-namedpipe-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-path-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-processenvironment-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-processthreads-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-processthreads-l1-1-1.dll;." ^
--add-binary "dlls\api-ms-win-core-profile-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-rtlsupport-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-string-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-synch-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-synch-l1-2-0.dll;." ^
--add-binary "dlls\api-ms-win-core-sysinfo-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-timezone-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-core-util-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-conio-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-convert-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-environment-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-filesystem-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-heap-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-locale-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-math-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-multibyte-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-process-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-runtime-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-stdio-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-string-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-time-l1-1-0.dll;." ^
--add-binary "dlls\api-ms-win-crt-utility-l1-1-0.dll;." ^
--add-binary "dlls\ucrtbase.dll;." ^
--add-binary "dlls\MSVCP140.dll;." ^
--add-binary "dlls\MSVCP140_1.dll;." ^
--add-binary "dlls\MSVCP140_2.dll;." ^
--add-binary "dlls\VCRUNTIME140.dll;." ^
--add-data ".venv\Lib\site-packages\colorama;colorama" ^
--add-data ".venv\Lib\site-packages\requests;requests" ^
--add-data ".venv\Lib\site-packages\psutil;psutil" ^
--add-data ".venv\Lib\site-packages\tqdm;tqdm" ^
--add-data ".venv\Lib\site-packages\certifi;certifi" ^
main.py > build_log.txt 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: PyInstaller failed. Check build_log.txt for details.
) else (
    echo Build completed successfully. Check dist\main.exe.
)
pause