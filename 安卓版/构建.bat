@echo off
rem 一键构建 APK：产物在 app\build\outputs\apk\debug\，同时复制一份到本文件夹
rem 依赖缓存在 ..\..\_构建缓存（没有的话会退回 %USERPROFILE%\.gradle，那就需要联网下载依赖）
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
set "ROOT=%HERE%.."
set "JAVA_HOME=D:\develop\jdk21"
set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
set "ANDROID_SDK_ROOT=%ANDROID_HOME%"

rem 依次找 Gradle 缓存：工程内 → 上级 → 工作区的 _构建缓存 → 系统默认
set "OFFLINE=--offline"
set "GRADLE_USER_HOME=%ROOT%\_gradle-home"
if not exist "%GRADLE_USER_HOME%" set "GRADLE_USER_HOME=%ROOT%\..\_gradle-home"
if not exist "%GRADLE_USER_HOME%" set "GRADLE_USER_HOME=%ROOT%\..\..\_构建缓存"
if not exist "%GRADLE_USER_HOME%" (
  set "GRADLE_USER_HOME=%USERPROFILE%\.gradle"
  set "OFFLINE="
)
set "ANDROID_USER_HOME=%GRADLE_USER_HOME%\.android"

pushd "%HERE%"
call gradlew.bat %OFFLINE% --console=plain %* assembleDebug
set "CODE=%ERRORLEVEL%"
popd

if "%CODE%"=="0" (
  copy /y "%HERE%app\build\outputs\apk\debug\app-debug.apk" "%HERE%一键打卡_最新.apk" >nul
  echo.
  echo   [OK] 已生成: 安卓版\一键打卡_最新.apk
  echo   （想让手机用，把这个文件复制到 ..\..\安卓版\ 里，或直接发到手机安装）
) else (
  echo.
  echo   [失败] 退出码 %CODE%
)
pause
endlocal
