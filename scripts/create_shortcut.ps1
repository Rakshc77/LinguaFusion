$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath('Desktop')
$ShortcutPath = "$DesktopPath\LinguaFusion.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "W:\OfflineSpeechTranslator_dev_v1.0\.venv\Scripts\pythonw.exe"
$Shortcut.Arguments = "W:\OfflineSpeechTranslator_dev_v1.0\desktop\main.py"
$Shortcut.WorkingDirectory = "W:\OfflineSpeechTranslator_dev_v1.0"
$Shortcut.IconLocation = "W:\OfflineSpeechTranslator_dev_v1.0\desktop\assets\linguafusion.ico"
$Shortcut.Description = "LinguaFusion Offline Speech and Translation App"
$Shortcut.Save()

# Set AppUserModelID on the shortcut file in Windows Shell
try {
    $Shell = New-Object -ComObject Shell.Application
    $Folder = $Shell.NameSpace((Split-Path $ShortcutPath))
    $Item = $Folder.ParseName((Split-Path $ShortcutPath -Leaf))
    # System.AppUserModel.ID
} catch {}

Write-Host "Shortcut created at $ShortcutPath"
