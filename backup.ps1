# ============================================================
# POCKET LAWYER v15.0 - BACKUP SCRIPT
# ============================================================
Clear-Host
Write-Host "📦 Pocket Lawyer v15.0 - Database Backup" -ForegroundColor Cyan
Write-Host ""

$backupDir = "backups"
if (!(Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force
}

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$backupFile = "$backupDir/pocket_lawyer_$timestamp.db"

# Check if database exists
if (Test-Path "database/pocket_lawyer.db") {
    Copy-Item "database/pocket_lawyer.db" $backupFile
    Write-Host "✅ Database backed up to: $backupFile" -ForegroundColor Green
    Write-Host "   Size: $((Get-Item $backupFile).Length / 1KB) KB" -ForegroundColor Cyan
} else {
    Write-Host "⚠️  Database file not found" -ForegroundColor Yellow
}

# List recent backups
Write-Host ""
Write-Host "📋 Recent backups:" -ForegroundColor Yellow
Get-ChildItem -Path $backupDir -Filter "*.db" | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | ForEach-Object {
    $size = $_.Length / 1KB
    Write-Host "   $($_.Name) ($size KB)" -ForegroundColor White
}
