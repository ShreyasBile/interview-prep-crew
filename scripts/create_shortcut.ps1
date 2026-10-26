# Put an "Interview Prep Crew" shortcut on the Desktop that starts the app (run.bat).
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")  # follows OneDrive Desktop redirection
$path = Join-Path $desktop "Interview Prep Crew.lnk"

$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
$shortcut.TargetPath = Join-Path $root "run.bat"
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = (Join-Path $root "static\app.ico") + ",0"
$shortcut.Description = "Start Interview Prep Crew"
$shortcut.Save()
Write-Host "Created $path"
