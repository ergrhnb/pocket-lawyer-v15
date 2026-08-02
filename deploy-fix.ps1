# ============================================================
# RENDER DEPLOYMENT FIX - POCKET LAWYER v15.0
# ============================================================

Write-Host "🚀 Fixing deployment for Render..." -ForegroundColor Cyan

# Step 1: Update requirements
Write-Host "📦 Updating requirements..." -ForegroundColor Yellow
@"
fastapi==0.104.1
uvicorn[standard]==0.24.0
httpx==0.25.2
reportlab==4.0.9
pymupdf==1.23.26
python-multipart==0.0.6
pydantic==2.5.0
python-dotenv==1.0.0
sqlalchemy==2.0.23
passlib==1.7.4
bcrypt==4.1.2
python-jose[cryptography]==3.3.0
PyJWT==2.8.0
cryptography==41.0.7
stripe==7.0.0
websockets==12.0
analytics-python==2.4.0
prometheus-client==0.19.0
itsdangerous==2.1.2
email-validator==2.1.0
"@ | Out-File -FilePath "requirements.txt" -Encoding utf8

# Step 2: Push to GitHub
Write-Host "📤 Pushing to GitHub..." -ForegroundColor Yellow
git add .
git commit -m "Fix: PyMuPDF build issues - use pre-built wheel"
git push -u origin main

Write-Host ""
Write-Host "✅ FIX PUSHED TO GITHUB!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 RENDER DEPLOYMENT INSTRUCTIONS:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Go to Render Dashboard" -ForegroundColor White
Write-Host "2. Click on your service" -ForegroundColor White
Write-Host "3. Go to 'Settings' → 'Build & Deploy'" -ForegroundColor White
Write-Host "4. Change Build Command to:" -ForegroundColor Yellow
Write-Host "   pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt" -ForegroundColor Cyan
Write-Host ""
Write-Host "5. Add this environment variable:" -ForegroundColor Yellow
Write-Host "   SETUPTOOLS_USE_DISTUTILS = stdlib" -ForegroundColor Cyan
Write-Host ""
Write-Host "6. Click 'Save Changes'" -ForegroundColor White
Write-Host "7. Click 'Manual Deploy' → 'Deploy latest commit'" -ForegroundColor White
Write-Host ""
Write-Host "✅ The build should now succeed!" -ForegroundColor Green
