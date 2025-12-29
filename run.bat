@echo off
setlocal

:: Define paths
set VENV_DIR=.venv
set PYTHON_EXE=%VENV_DIR%\Scripts\python.exe

:: Check if venv exists
if not exist "%PYTHON_EXE%" (
    echo Virtual environment not found. Setting up...
    
    :: Create venv
    echo Creating .venv...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo Failed to create virtual environment. Please install Python.
        pause
        exit /b 1
    )
    
    :: Install requirements
    if exist "requirements.txt" (
        echo Installing requirements...
        "%PYTHON_EXE%" -m pip install -r requirements.txt
        if errorlevel 1 (
            echo Failed to install requirements.
            pause
            exit /b 1
        )
    ) else (
        echo Warning: requirements.txt not found. Skipping installation.
    )
    
    echo Setup complete.
) else (
    echo Virtual environment found using %PYTHON_EXE%
)

:: Run the application
echo Starting Simple Manga Reader...
"%PYTHON_EXE%" main.py

if errorlevel 1 (
    echo Application exited with error.
    pause
)

endlocal
