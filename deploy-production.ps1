# ============================================================
# POCKET LAWYER v15.0 - PRODUCTION DEPLOYMENT SCRIPT
# ============================================================
Clear-Host
Write-Host "🚀 Pocket Lawyer v15.0 - Production Deployment" -ForegroundColor Cyan
Write-Host ""

# Check git status
Write-Host "📤 Checking git status..." -ForegroundColor Yellow
$gitStatus = git status --porcelain
if ($gitStatus) {
    Write-Host "⚠️  You have uncommitted changes:" -ForegroundColor Yellow
    git status
    $proceed = Read-Host "Continue with deployment? (y/n)"
    if ($proceed -ne 'y') { 
        Write-Host "❌ Deployment cancelled" -ForegroundColor Red
        exit
    }
}

# Pull latest changes
Write-Host "📥 Pulling latest changes..." -ForegroundColor Yellow
git pull origin main

# Run tests
Write-Host "🧪 Running tests..." -ForegroundColor Yellow
$testResult = pytest tests/ -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Tests failed. Fix issues before deploying." -ForegroundColor Red
    exit
}

# Push to GitHub
Write-Host "📤 Pushing to GitHub..." -ForegroundColor Yellow
git add .
git commit -m "Production deployment $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
git push origin main

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Git push failed!" -ForegroundColor Red
    exit
}

Write-Host "✅ Code pushed to GitHub!" -ForegroundColor Green
Write-Host ""

Write-Host "🚀 Triggering Render deployment..." -ForegroundColor Yellow
Write-Host ""
Write-Host "📋 MANUAL STEPS REQUIRED ON RENDER:" -ForegroundColor Cyan
Write-Host "1. Go to https://dashboard.render.com" -ForegroundColor White
Write-Host "2. Click on your service: pocket-lawyer-v15" -ForegroundColor White
Write-Host "3. Click 'Manual Deploy' → 'Deploy latest commit'" -ForegroundColor White
Write-Host "4. Wait for deployment to complete" -ForegroundColor White
Write-Host "5. Check logs for any errors" -ForegroundColor White
Write-Host ""

Write-Host "🔑 DEPLOYMENT CHECKLIST:" -ForegroundColor Yellow
Write-Host "   ✅ Code pushed to GitHub" -ForegroundColor White
Write-Host "   ✅ Tests passed" -ForegroundColor White
Write-Host "   ⏳ Waiting for Render deployment" -ForegroundColor White
Write-Host ""

Write-Host "🌐 After deployment, your app will be at:" -ForegroundColor Green
Write-Host "   https://pocket-lawyer-v15.onrender.com" -ForegroundColor Cyan
Write-Host ""

Read-Host "Press Enter to open Render Dashboard"
Start-Process "https://dashboard.render.com"
