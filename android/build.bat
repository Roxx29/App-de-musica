@echo off
rem Genera el .apk de BrilloMusical para Android.
rem Requisitos: Android Studio instalado (trae el SDK y Java). Ejecuta este archivo con doble clic.
cd /d "%~dp0"
if "%JAVA_HOME%"=="" if exist "%ProgramFiles%\Android\Android Studio\jbr" set "JAVA_HOME=%ProgramFiles%\Android\Android Studio\jbr"
if not exist local.properties if exist "%LOCALAPPDATA%\Android\Sdk" (
  echo sdk.dir=%LOCALAPPDATA:\=\\%\\Android\\Sdk> local.properties
)
call gradlew.bat assembleDebug
if errorlevel 1 ( echo. & echo Error en el build. & pause & exit /b 1 )
echo.
echo Listo: app\build\outputs\apk\debug\app-debug.apk
echo Copialo al telefono e instalalo (permite "origenes desconocidos").
pause
