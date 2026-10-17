@echo off
rem 一键离线构建（不联网）：把 debug APK 打到 app\build\outputs\apk\debug\
rem 依赖都在工作区的 _gradle-home 里，AGP 8.11.1 + Gradle 8.13
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
set "ROOT=%HERE%.."
set "JAVA_HOME=D:\develop\jdk21"
set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
set "ANDROID_SDK_ROOT=%ANDROID_HOME%"
set "GRADLE_USER_HOME=%ROOT%\_gradle-home"
if not exist "%GRADLE_USER_HOME%" set "GRADLE_USER_HOME=%ROOT%\..\_gradle-home"
if not exist "%GRADLE_USER_HOME%" set "GRADLE_USER_HOME=%USERPROFILE%\.gradle"
set "ANDROID_USER_HOME=%GRADLE_USER_HOME%\.android"

pushd "%HERE%"
call gradlew.bat --offline --console=plain %* assembleDebug
set "CODE=%ERRORLEVEL%"
popd

if "%CODE%"=="0" (
  copy /y "%HERE%app\build\outputs\apk\debug\app-debug.apk" "%HERE%一键打卡_验证版.apk" >nul
  echo.
  echo   [OK] 已生成: 安卓版\一键打卡_验证版.apk
) else (
  echo.
  echo   [失败] 退出码 %CODE%
)
pause
endlocal
