# ============================================================
# FIX TELEGRAM CONFIGURATION
# ============================================================
Clear-Host
Write-Host "🔧 Fixing Telegram configuration..." -ForegroundColor Cyan

# Option 1: Disable Telegram in Render
Write-Host ""
Write-Host "📋 OPTION 1: Disable Telegram in Render Dashboard" -ForegroundColor Yellow
Write-Host "   1. Go to https://dashboard.render.com" -ForegroundColor White
Write-Host "   2. Click on your service: pocket-lawyer-v15" -ForegroundColor White
Write-Host "   3. Go to 'Environment' tab" -ForegroundColor White
Write-Host "   4. Find TELEGRAM_ENABLED and set to: false" -ForegroundColor White
Write-Host "   5. Click 'Save Changes'" -ForegroundColor White
Write-Host "   6. Click 'Manual Deploy' → 'Deploy latest commit'" -ForegroundColor White
Write-Host ""

Write-Host "📋 OPTION 2: Get a Valid Telegram Bot Token" -ForegroundColor Yellow
Write-Host "   1. Open Telegram" -ForegroundColor White
Write-Host "   2. Search for @BotFather" -ForegroundColor White
Write-Host "   3. Send: /newbot" -ForegroundColor White
Write-Host "   4. Choose a name and username for your bot" -ForegroundColor White
Write-Host "   5. Copy the token (format: 1234567890:ABCdefGHIJklmNOPQRSTUVWXYZ)" -ForegroundColor White
Write-Host "   6. Update TELEGRAM_BOT_TOKEN in Render environment variables" -ForegroundColor White
Write-Host "   7. Set TELEGRAM_ENABLED to: true" -ForegroundColor White
Write-Host ""

Write-Host "📋 OPTION 3: Test Your Telegram Token" -ForegroundColor Yellow
Write-Host "   Run this command to test your token:" -ForegroundColor White
Write-Host "   curl https://api.telegram.org/botYOUR_TOKEN/getMe" -ForegroundColor Cyan
Write-Host ""

Read-Host "Press Enter to open Render Dashboard"
Start-Process "https://dashboard.render.com"
