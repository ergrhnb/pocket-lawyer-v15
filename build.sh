#!/bin/bash
# ============================================================
# POCKET LAWYER v15.0 - BUILD SCRIPT
# ============================================================

echo "🚀 Starting build..."

# Install Python dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -r requirements.txt

# Verify PyMuPDF is installed
echo "🔍 Verifying PyMuPDF installation..."
python -c "import fitz; print('✅ PyMuPDF version:', fitz.__doc__)"

echo "✅ Build completed successfully!"
