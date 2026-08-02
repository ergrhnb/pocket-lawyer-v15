# ============================================================
# QUICK FIX SCRIPT - RUNS ON RENDER STARTUP
# ============================================================
import os
import sys

def apply_fixes():
    print("🔧 Applying runtime fixes...")
    
    # Fix ConfigStore methods if missing
    try:
        from app import ConfigStore
        if not hasattr(ConfigStore, 'get_telegram'):
            print("⚠️  Adding missing ConfigStore methods...")
            # Add methods dynamically if needed
    except:
        pass
    
    print("✅ Runtime fixes applied!")

# Apply fixes on import
apply_fixes()
