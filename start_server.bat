@echo off
echo ============================================
echo  Restaurant Menu App - Backend Setup Script
echo ============================================
echo.

echo [1/4] Starting XAMPP MySQL...
"C:\xampp\mysql\bin\mysqld.exe" --standalone
timeout /t 3 >nul

echo [2/4] Creating database...
"C:\xampp\mysql\bin\mysql.exe" -u root -e "CREATE DATABASE IF NOT EXISTS menuapp_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
echo    Database ready.

echo [3/4] Running Django migrations...
python manage.py makemigrations
python manage.py migrate

echo [4/4] Starting Django server...
echo    Server will start on http://0.0.0.0:8000
echo    Access on LOCAL: http://localhost:8000
echo.
python manage.py runserver 0.0.0.0:8000
