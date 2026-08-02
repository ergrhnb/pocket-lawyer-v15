# ============================================================
# POCKET LAWYER v15.0 - MONITORING DASHBOARD
# ============================================================
Clear-Host
Write-Host "📊 Pocket Lawyer v15.0 - Monitoring Dashboard" -ForegroundColor Cyan
Write-Host ""

$appUrl = "https://pocket-lawyer-v15.onrender.com"

# Check health
Write-Host "🔍 Health Check:" -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "$appUrl/api/health" -TimeoutSec 10
    $status = $health.status
    $version = $health.version
    $pdfAvailable = $health.pdf_available
    $pdfReader = $health.pdf_reader
    
    if ($status -eq "healthy") {
        Write-Host "   ✅ Status: $status" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Status: $status" -ForegroundColor Yellow
    }
    Write-Host "   📌 Version: $version" -ForegroundColor Cyan
    Write-Host "   📄 PDF Generation: $(if($pdfAvailable){'✅'}else{'❌'})" -ForegroundColor Cyan
    Write-Host "   📑 PDF Reader: $(if($pdfReader){'✅'}else{'❌'})" -ForegroundColor Cyan
} catch {
    Write-Host "   ❌ Health check failed" -ForegroundColor Red
    Write-Host "   Error: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "⏱️  Uptime Check:" -ForegroundColor Yellow
$attempts = 3
$success = 0
for ($i = 1; $i -le $attempts; $i++) {
    try {
        $response = Invoke-WebRequest -Uri $appUrl -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            $success++
        }
    } catch {
        # Ignore
    }
    Start-Sleep -Seconds 1
}
Write-Host "   📊 Uptime: $($success/$attempts*100)% ($success/$attempts attempts)" -ForegroundColor Cyan

Write-Host ""
Write-Host "📋 Recent Logs:" -ForegroundColor Yellow
try {
    $logs = tail -n 10 logs/pocket_lawyer.log 2>$null
    if ($logs) {
        $logs | ForEach-Object {
            $line = $_
            if ($line -match "ERROR") {
                Write-Host "   ❌ $line" -ForegroundColor Red
            } elseif ($line -match "WARNING") {
                Write-Host "   ⚠️  $line" -ForegroundColor Yellow
            } elseif ($line -match "✅|SUCCESS") {
                Write-Host "   ✅ $line" -ForegroundColor Green
            } else {
                Write-Host "   ℹ️  $line" -ForegroundColor White
            }
        }
    } else {
        Write-Host "   No logs available" -ForegroundColor Gray
    }
} catch {
    Write-Host "   Could not read logs" -ForegroundColor Gray
}

Write-Host ""
Write-Host "📊 System Info:" -ForegroundColor Yellow
Write-Host "   🕐 Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "   💻 Host: $env:COMPUTERNAME" -ForegroundColor Cyan
Write-Host "   📁 Directory: $PWD" -ForegroundColor Cyan

Write-Host ""
Write-Host "🌐 Quick Access:" -ForegroundColor Green
Write-Host "   App: $appUrl" -ForegroundColor Cyan
Write-Host "   Health: $appUrl/api/health" -ForegroundColor Cyan
Write-Host ""
