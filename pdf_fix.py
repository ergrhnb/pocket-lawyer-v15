# Add this at the top of app.py after the imports
# This will make PyMuPDF optional

try:
    import fitz
    PDF_READER_AVAILABLE = True
except ImportError:
    PDF_READER_AVAILABLE = False
    fitz = None
    print("⚠️  PyMuPDF not available - PDF analysis disabled")

# Then in your code, check PDF_READER_AVAILABLE before using fitz
