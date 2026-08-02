# ============================================================
# DEPLOY TO RENDER - POCKET LAWYER v15.0
# ============================================================

echo "🚀 Deploying Pocket Lawyer v15.0 to Render..."

# Step 1: Push to GitHub
echo "📤 Pushing to GitHub..."
git add .
git commit -m "Deploy Pocket Lawyer v15.0"
git push -u origin main

echo ""
echo "✅ Code pushed to GitHub!"
echo ""
echo "📋 NEXT STEPS:"
echo "1. Go to https://dashboard.render.com"
echo "2. Click 'New +' → 'Web Service'"
echo "3. Connect to: ergrhnb/pocket-lawyer-v15"
echo "4. Select 'Python' as the runtime"
echo "5. Build Command: pip install -r requirements.txt"
echo "6. Start Command: uvicorn app:app --host 0.0.0.0 --port \$PORT"
echo "7. Add environment variables:"
echo "   - SECRET_KEY (generate one)"
echo "   - ENCRYPTION_KEY (generate one)"
echo "   - GROQ_API_KEY"
echo "   - SAMBANOVA_API_KEY"
echo "   - MISTRAL_API_KEY"
echo "   - OPENROUTER_API_KEY"
echo "   - TELEGRAM_BOT_TOKEN"
echo "8. Click 'Create Web Service'"
echo ""
echo "✅ Your app will be live at: https://pocket-lawyer-v15.onrender.com"
