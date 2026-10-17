# 真机端到端验收：构建 → 安装 → 选图 → 生成 → 拉回 → 结构校验 → WPS 打开
# 用法：pwsh -File 安卓版/tools/e2e_test.ps1
$ErrorActionPreference = "Continue"
$repo = if ($env:DAKA_REPO) { $env:DAKA_REPO } else { (Resolve-Path "$PSScriptRoot\..").Path }  # 仓库根（打卡工具）
$ws = Split-Path $repo -Parent                                                                  # 外层工作区（放验收截图）
$short = "C:\Users\l1644\Desktop\实用工具\工作\宣传委~1"
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
$apk = "$repo\安卓版\一键打卡_验证版.apk"
$out = "$ws\_验证\手机生成_第六周.docx"

function Shot($dest) {
  $p = New-Object System.Diagnostics.Process
  $p.StartInfo.FileName = $adb; $p.StartInfo.Arguments = "exec-out screencap -p"
  $p.StartInfo.RedirectStandardOutput = $true; $p.StartInfo.UseShellExecute = $false; $p.StartInfo.CreateNoWindow = $true
  [void]$p.Start(); $ms = New-Object System.IO.MemoryStream
  $p.StandardOutput.BaseStream.CopyTo($ms); $p.WaitForExit()
  [System.IO.File]::WriteAllBytes($dest, $ms.ToArray())
}

Write-Host "=== 1/6 构建 ===" -ForegroundColor Cyan
Set-Location "$ws\安卓版"
$env:JAVA_HOME = "D:\develop\jdk21"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:GRADLE_USER_HOME = "$ws\_gradle-home"
$env:ANDROID_USER_HOME = "$ws\_gradle-home\.android"
& .\gradlew.bat --offline --console=plain assembleDebug 2>&1 | Select-Object -Last 2 | Out-String
Copy-Item "app\build\outputs\apk\debug\app-debug.apk" $apk -Force

Write-Host "=== 2/6 安装 ===" -ForegroundColor Cyan
(& $adb install -r $apk 2>&1) | Select-Object -Last 1 | Out-String

Write-Host "=== 3/6 选图（长按第 2 格 + 点第 3 格）===" -ForegroundColor Cyan
(& $adb shell am force-stop com.yyyan44.daka 2>&1) | Out-Null
(& $adb shell am start -n com.yyyan44.daka/.MainActivity 2>&1) | Out-Null
Start-Sleep -Seconds 4
(& $adb shell input tap 540 666 2>&1) | Out-Null; Start-Sleep -Seconds 4
(& $adb shell input swipe 563 1028 563 1028 900 2>&1) | Out-Null; Start-Sleep -Seconds 2
(& $adb shell input tap 892 1028 2>&1) | Out-Null; Start-Sleep -Seconds 2
(& $adb shell input tap 847 153 2>&1) | Out-Null; Start-Sleep -Seconds 4

Write-Host "=== 4/6 生成 ===" -ForegroundColor Cyan
(& $adb shell input tap 540 2324 2>&1) | Out-Null
Start-Sleep -Seconds 20
Shot "$ws\_验证\手机_20_生成结果.png"

Write-Host "=== 5/6 拉回手机生成的文档 ===" -ForegroundColor Cyan
(& $adb shell ls -l "/sdcard/Download/一键打卡/" 2>&1) | Out-String
(& $adb pull "/sdcard/Download/一键打卡/XG1253第六周打卡.docx" "$short\_验证\手机生成_第六周.docx" 2>&1) | Select-Object -Last 1 | Out-String

Write-Host "=== 6/6 结构校验 + WPS 打开 ===" -ForegroundColor Cyan
$env:PYTHONIOENCODING = "utf-8"
& D:\anacoda\python.exe "$ws\安卓版\tools\check_docx.py" $out
