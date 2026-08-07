$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath('Desktop')
$ExePath = "W:\OfflineSpeechTranslator_dev_v1.0\dist\LinguaFusion\LinguaFusion.exe"
$WorkDir = "W:\OfflineSpeechTranslator_dev_v1.0\dist\LinguaFusion"

# 1. Desktop Shortcut
$DesktopShortcutPath = "$DesktopPath\LinguaFusion.lnk"
$Shortcut = $WshShell.CreateShortcut($DesktopShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = $WorkDir
$Shortcut.IconLocation = "$ExePath,0"
$Shortcut.Description = "LinguaFusion Offline Speech & Translation Desktop App"
$Shortcut.Save()
Write-Host "Desktop shortcut created at: $DesktopShortcutPath"

# 2. Taskbar Quick Launch Shortcut
$TaskbarPath = "$env:APPDATA\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"
if (-not (Test-Path $TaskbarPath)) {
    New-Item -ItemType Directory -Path $TaskbarPath -Force | Out-Null
}
$TaskbarShortcutPath = "$TaskbarPath\LinguaFusion.lnk"
$TbShortcut = $WshShell.CreateShortcut($TaskbarShortcutPath)
$TbShortcut.TargetPath = $ExePath
$TbShortcut.WorkingDirectory = $WorkDir
$TbShortcut.IconLocation = "$ExePath,0"
$TbShortcut.Description = "LinguaFusion Offline Speech & Translation Desktop App"
$TbShortcut.Save()
Write-Host "Taskbar shortcut created at: $TaskbarShortcutPath"
