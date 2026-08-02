# ============================================================
# POCKET LAWYER v15.0 - CLEAN PRODUCTION VERSION
# ============================================================
import os
import json
import logging
import asyncio
import threading
import time
import re
import io
import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Depends, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
import httpx
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext
from cryptography.fernet import Fernet

# ============================================================
# LOGGING
# ============================================================
os.makedirs('logs', exist_ok=True)
os.makedirs('database', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/pocket_lawyer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("pocket_lawyer")

VERSION = "15.0.6"
APP_NAME = "Pocket Lawyer"

# ============================================================
# SECURITY
# ============================================================
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(64))
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# ============================================================
# DATABASE
# ============================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database/pocket_lawyer.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============================================================
# MODELS
# ============================================================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(200))
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    subscription_tier = Column(String(50), default="free")

class LegalCase(Base):
    __tablename__ = "legal_cases"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255))
    icon = Column(String(50))
    category = Column(String(100))
    slug = Column(String(100))
    is_active = Column(Boolean, default=True)
    order = Column(Integer, default=0)

Base.metadata.create_all(bind=engine)

# ============================================================
# PYDANTIC MODELS
# ============================================================
class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: str
    is_active: bool
    is_superuser: bool
    subscription_tier: str
    created_at: datetime
    
    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
    
    model_config = {"from_attributes": True}

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)

# ============================================================
# CONFIG
# ============================================================
class ConfigStore:
    _config = {
        "brand_name": "Pocket Lawyer",
        "ai_providers": [
            {"name": "Groq", "enabled": True,
             "api_key": os.getenv("GROQ_API_KEY", ""),
             "model": "llama-3.3-70b-versatile",
             "base_url": "https://api.groq.com/openai/v1"},
            {"name": "SambaNova", "enabled": True,
             "api_key": os.getenv("SAMBANOVA_API_KEY", ""),
             "model": "Meta-Llama-3.3-70B-Instruct",
             "base_url": "https://api.sambanova.ai/v1"},
            {"name": "Mistral", "enabled": True,
             "api_key": os.getenv("MISTRAL_API_KEY", ""),
             "model": "mistral-large-latest",
             "base_url": "https://api.mistral.ai/v1"},
            {"name": "OpenRouter", "enabled": True,
             "api_key": os.getenv("OPENROUTER_API_KEY", ""),
             "model": "mistralai/mistral-large",
             "base_url": "https://openrouter.ai/api/v1"}
        ],
        "telegram": {"enabled": True, "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""), "bot_username": "Mypocket_lawyerbot"},
        "legal_cases": [
            {"title": "Tenancy & Landlord", "icon": "🏠", "category": "Property"},
            {"title": "Employment Law", "icon": "💼", "category": "Employment"},
            {"title": "Contracts", "icon": "📝", "category": "Business"},
            {"title": "Family Law", "icon": "👨‍👩‍👧‍👦", "category": "Family"},
            {"title": "Debt Recovery", "icon": "💰", "category": "Finance"},
            {"title": "Criminal Law", "icon": "⚖️", "category": "Criminal"},
            {"title": "Corporate Law", "icon": "🏢", "category": "Business"},
            {"title": "Property Law", "icon": "🏡", "category": "Property"}
        ]
    }

    @classmethod
    def get(cls, key, default=None):
        return cls._config.get(key, default)

    @classmethod
    def get_ai_providers(cls):
        return cls._config.get("ai_providers", [])

    @classmethod
    def get_legal_cases(cls):
        return cls._config.get("legal_cases", [])

# ============================================================
# APP
# ============================================================
app = FastAPI(title=APP_NAME, version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================================
# AUTH FUNCTIONS
# ============================================================
def verify_password(plain_password, hashed_password):
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except:
        return False

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(days=7)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

def verify_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except:
        return None

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: SessionLocal = Depends(get_db)):
    if not credentials:
        return None
    payload = verify_token(credentials.credentials)
    if not payload:
        return None
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    return user if user and user.is_active else None

async def get_current_user_required(credentials: HTTPAuthorizationCredentials = Depends(security), db: SessionLocal = Depends(get_db)):
    user = await get_current_user(credentials, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    return user

# ============================================================
# PDF FUNCTIONS
# ============================================================
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    PDF_AVAILABLE = True
except:
    PDF_AVAILABLE = False

documents = {}

# ============================================================
# AI FUNCTIONS
# ============================================================
async def call_provider(base_url, api_key, model, messages):
    try:
        if not base_url or not api_key or not model:
            return None
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 2000}
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content")
            return None
    except:
        return None

async def get_ai_response(messages):
    for provider in ConfigStore.get_ai_providers():
        if not provider.get("enabled"):
            continue
        reply = await call_provider(
            provider.get("base_url"),
            provider.get("api_key"),
            provider.get("model"),
            messages
        )
        if reply:
            return {"reply": reply, "provider": provider.get("name")}
        await asyncio.sleep(0.05)
    return {"reply": "I'm having trouble connecting. Please try again later.", "provider": "offline"}

# ============================================================
# AUTH ENDPOINTS
# ============================================================
@app.post("/api/auth/register")
async def register(user_data: UserCreate, db: SessionLocal = Depends(get_db)):
    try:
        existing = db.query(User).filter(
            (User.email == user_data.email) | (User.username == user_data.username)
        ).first()
        if existing:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Email or username already registered"})

        user = User(
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            hashed_password=get_password_hash(user_data.password)
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_access_token({"user_id": user.id, "username": user.username})
        return {"access_token": token, "token_type": "bearer", "user": UserResponse.model_validate(user)}
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/auth/login")
async def login(login_data: UserLogin, db: SessionLocal = Depends(get_db)):
    try:
        user = db.query(User).filter(User.username == login_data.username).first()
        if not user:
            user = db.query(User).filter(User.email == login_data.username).first()

        if not user or not verify_password(login_data.password, user.hashed_password):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid credentials"})

        user.last_login = datetime.utcnow()
        db.commit()

        token = create_access_token({"user_id": user.id, "username": user.username})
        return {"access_token": token, "token_type": "bearer", "user": UserResponse.model_validate(user)}
    except Exception as e:
        logger.error(f"Login error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Login failed"})

@app.get("/api/auth/me")
async def get_current_user_info(current_user: User = Depends(get_current_user_required)):
    return UserResponse.model_validate(current_user)

# ============================================================
# LEGAL CASES
# ============================================================
@app.get("/api/legal-cases")
async def get_legal_cases():
    return {"status": "success", "cases": ConfigStore.get_legal_cases()}

# ============================================================
# CHAT
# ============================================================
@app.post("/api/chat")
async def chat(chat_req: ChatRequest):
    try:
        message = chat_req.message
        if not message:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Message required"})

        # Check for PDF generation
        pdf_keywords = ["generate pdf", "create pdf", "make pdf", "tenancy agreement", "nda"]
        if any(word in message.lower() for word in pdf_keywords) and PDF_AVAILABLE:
            title = "Legal Document"
            if "tenancy" in message.lower() or "rent" in message.lower():
                title = "Tenancy Agreement"
            
            doc_id = f"doc_{int(time.time())}"
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = [Paragraph(title, styles['Heading1']), Spacer(1, 0.2 * inch)]
            story.append(Paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}", styles['Normal']))
            doc.build(story)
            buffer.seek(0)
            
            documents[doc_id] = {"title": title, "pdf": buffer}
            return {
                "reply": f"Document generated: {title}",
                "pdf_url": f"/api/documents/{doc_id}/download",
                "document_id": doc_id,
                "is_pdf": True
            }

        result = await get_ai_response([{"role": "user", "content": message}])
        return {"reply": result["reply"], "provider": result.get("provider", "AI")}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/documents/{doc_id}/download")
async def download_document(doc_id: str):
    doc = documents.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    pdf_buffer = doc.get("pdf")
    if not pdf_buffer:
        raise HTTPException(status_code=404, detail="PDF not found")
    pdf_buffer.seek(0)
    return StreamingResponse(pdf_buffer, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={doc['title']}.pdf"})

# ============================================================
# HEALTH
# ============================================================
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": VERSION, "pdf_available": PDF_AVAILABLE}

# ============================================================
# FRONTEND PAGES
# ============================================================
@app.get("/")
async def home():
    brand = ConfigStore.get("brand_name", "Pocket Lawyer")
    cases_html = ""
    for case in ConfigStore.get_legal_cases():
        cases_html += f'<div class="case-card" onclick="window.location.href=\'/chat?q={case["title"]}\'"><span class="case-icon">{case["icon"]}</span><span class="case-title">{case["title"]}</span></div>'
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>{brand}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
        .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
        .header h1 {{ color: #60a5fa; }}
        .header h1 span {{ color: #f59e0b; }}
        .btn {{ padding: 10px 24px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }}
        .btn-primary {{ background: #3b82f6; color: white; }}
        .btn-primary:hover {{ background: #2563eb; }}
        .btn-outline {{ background: transparent; color: #94a3b8; border: 1px solid #334155; }}
        .btn-outline:hover {{ background: #1e293b; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
        .hero {{ text-align: center; padding: 60px 20px; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 16px; border: 1px solid #334155; margin-bottom: 32px; }}
        .hero h1 {{ font-size: 3rem; color: #60a5fa; }}
        .hero h1 .highlight {{ color: #f59e0b; }}
        .hero p {{ font-size: 1.2rem; color: #94a3b8; margin: 16px 0; }}
        .btn-group {{ display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 24px; }}
        .cases-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }}
        .case-card {{ background: #1e293b; padding: 16px 20px; border-radius: 10px; border: 1px solid #334155; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: all 0.3s; }}
        .case-card:hover {{ border-color: #60a5fa; transform: translateX(4px); background: #253450; }}
        .case-icon {{ font-size: 1.5rem; }}
        .case-title {{ color: #e2e8f0; font-size: 0.9rem; }}
        .footer {{ text-align: center; color: #64748b; font-size: 0.8rem; padding: 24px; border-top: 1px solid #1e293b; margin-top: 40px; }}
        @media (max-width: 768px) {{ .header {{ flex-direction: column; text-align: center; }} .hero h1 {{ font-size: 2rem; }} }}
    </style>
    </head>
    <body>
        <div class="header"><div><h1>⚖️ <span>Pocket</span> Lawyer</h1></div><div><a href="/auth/login" class="btn btn-outline">Login</a><a href="/auth/register" class="btn btn-primary">Get Started</a></div></div>
        <div class="container">
            <div class="hero"><h1>Your <span class="highlight">Trusted</span> Legal AI Assistant</h1><p>🇳🇬 Nigerian Law, Powered by Advanced AI</p><div class="btn-group"><a href="/auth/register" class="btn btn-primary">🚀 Start Now</a><a href="/chat" class="btn btn-primary">💬 Try AI Chat</a></div></div>
            <div style="padding:40px 20px;max-width:1200px;margin:0 auto;"><h2 style="text-align:center;margin-bottom:24px;color:#f59e0b;">📌 Choose Your Legal Matter</h2><div class="cases-grid">{cases_html}</div></div>
        </div>
        <div class="footer"><p>⚖️ {brand} v{VERSION} • General guidance only</p></div>
    </body>
    </html>
    """)

@app.get("/auth/login")
async def login_page():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Login</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; display: flex; justify-content: center; align-items: center; }
        .login-container { background: #1e293b; padding: 40px; border-radius: 16px; border: 1px solid #334155; width: 100%; max-width: 400px; }
        .login-container h2 { color: #60a5fa; text-align: center; }
        .login-container .subtitle { color: #94a3b8; text-align: center; margin-bottom: 24px; }
        .form-group { margin-bottom: 16px; }
        .form-group label { color: #94a3b8; display: block; margin-bottom: 4px; }
        .form-group input { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; }
        .form-group input:focus { border-color: #3b82f6; outline: none; }
        .btn { width: 100%; padding: 12px; border: none; border-radius: 8px; background: #3b82f6; color: white; font-weight: 600; cursor: pointer; }
        .btn:hover { background: #2563eb; }
        .links { text-align: center; margin-top: 16px; color: #94a3b8; }
        .links a { color: #60a5fa; text-decoration: none; }
        .error { background: #ef444420; color: #ef4444; padding: 12px; border-radius: 8px; margin-bottom: 16px; display: none; border: 1px solid #ef444440; }
    </style>
    </head>
    <body>
    <div class="login-container">
        <h2>⚖️ Welcome Back</h2>
        <p class="subtitle">Login to your Pocket Lawyer account</p>
        <div class="error" id="errorMsg"></div>
        <form id="loginForm">
            <div class="form-group"><label>Username</label><input type="text" id="username" required placeholder="Enter your username"></div>
            <div class="form-group"><label>Password</label><input type="password" id="password" required placeholder="Enter your password"></div>
            <button type="submit" class="btn" id="loginBtn">Sign In</button>
        </form>
        <div class="links"><p>Don't have an account? <a href="/auth/register">Register</a></p><p style="margin-top:8px;font-size:0.8rem;color:#64748b;">Demo: admin / admin123</p></div>
    </div>
    <script>
    document.getElementById('loginForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn = document.getElementById('loginBtn');
        const errorMsg = document.getElementById('errorMsg');
        btn.disabled = true;
        btn.textContent = 'Logging in...';
        errorMsg.style.display = 'none';
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    username: document.getElementById('username').value.trim(),
                    password: document.getElementById('password').value
                })
            });
            const data = await response.json();
            if (response.ok) {
                localStorage.setItem('token', data.access_token);
                localStorage.setItem('user', JSON.stringify(data.user));
                window.location.href = '/chat';
            } else {
                errorMsg.textContent = '❌ ' + (data.message || 'Invalid credentials');
                errorMsg.style.display = 'block';
            }
        } catch(e) {
            errorMsg.textContent = '❌ Connection error. Please try again.';
            errorMsg.style.display = 'block';
        }
        btn.disabled = false;
        btn.textContent = 'Sign In';
    });
    </script>
    </body>
    </html>
    """)

@app.get("/auth/register")
async def register_page():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Register</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; display: flex; justify-content: center; align-items: center; }
        .register-container { background: #1e293b; padding: 40px; border-radius: 16px; border: 1px solid #334155; width: 100%; max-width: 400px; }
        .register-container h2 { color: #60a5fa; text-align: center; }
        .register-container .subtitle { color: #94a3b8; text-align: center; margin-bottom: 24px; }
        .form-group { margin-bottom: 16px; }
        .form-group label { color: #94a3b8; display: block; margin-bottom: 4px; }
        .form-group input { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; }
        .form-group input:focus { border-color: #3b82f6; outline: none; }
        .btn { width: 100%; padding: 12px; border: none; border-radius: 8px; background: #10b981; color: white; font-weight: 600; cursor: pointer; }
        .btn:hover { background: #059669; }
        .links { text-align: center; margin-top: 16px; color: #94a3b8; }
        .links a { color: #60a5fa; text-decoration: none; }
        .error { background: #ef444420; color: #ef4444; padding: 12px; border-radius: 8px; margin-bottom: 16px; display: none; border: 1px solid #ef444440; }
    </style>
    </head>
    <body>
    <div class="register-container">
        <h2>🚀 Create Account</h2>
        <p class="subtitle">Start using Pocket Lawyer today</p>
        <div class="error" id="errorMsg"></div>
        <form id="registerForm">
            <div class="form-group"><label>Full Name</label><input type="text" id="full_name" required placeholder="Enter your full name"></div>
            <div class="form-group"><label>Username</label><input type="text" id="username" required placeholder="Choose a username" minlength="3"></div>
            <div class="form-group"><label>Email</label><input type="email" id="email" required placeholder="Enter your email"></div>
            <div class="form-group"><label>Password</label><input type="password" id="password" required placeholder="Min 6 characters" minlength="6"></div>
            <button type="submit" class="btn" id="registerBtn">Create Account</button>
        </form>
        <div class="links"><p>Already have an account? <a href="/auth/login">Login</a></p></div>
    </div>
    <script>
    document.getElementById('registerForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn = document.getElementById('registerBtn');
        const errorMsg = document.getElementById('errorMsg');
        btn.disabled = true;
        btn.textContent = 'Creating account...';
        errorMsg.style.display = 'none';
        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    full_name: document.getElementById('full_name').value.trim(),
                    username: document.getElementById('username').value.trim(),
                    email: document.getElementById('email').value.trim(),
                    password: document.getElementById('password').value
                })
            });
            const data = await response.json();
            if (response.ok) {
                localStorage.setItem('token', data.access_token);
                localStorage.setItem('user', JSON.stringify(data.user));
                window.location.href = '/chat';
            } else {
                errorMsg.textContent = '❌ ' + (data.message || 'Registration failed');
                errorMsg.style.display = 'block';
            }
        } catch(e) {
            errorMsg.textContent = '❌ Connection error. Please try again.';
            errorMsg.style.display = 'block';
        }
        btn.disabled = false;
        btn.textContent = 'Create Account';
    });
    </script>
    </body>
    </html>
    """)

@app.get("/chat")
async def chat_ui():
    brand = ConfigStore.get("brand_name", "Pocket Lawyer")
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>{brand} - Chat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; overflow: hidden; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 24px; background: #1e293b; border-bottom: 1px solid #334155; }}
        .header h2 {{ color: #60a5fa; }}
        .btn {{ background: #1e293b; color: #e2e8f0; padding: 6px 16px; border-radius: 8px; text-decoration: none; border: 1px solid #334155; cursor: pointer; }}
        .chat-container {{ max-width: 900px; margin: 0 auto; padding: 20px; height: calc(100vh - 80px); display: flex; flex-direction: column; }}
        .chat-box {{ flex:1; overflow-y:auto; padding:20px; background:#0f172a; border:1px solid #1e293b; border-radius:12px; margin-bottom:16px; }}
        .message {{ padding: 12px 18px; margin: 8px 0; border-radius: 12px; max-width: 85%; word-wrap: break-word; line-height: 1.6; }}
        .user {{ background: #3b82f6; margin-left: auto; }}
        .ai {{ background: #1e293b; border: 1px solid #334155; }}
        .input-area {{ display: flex; gap: 12px; padding: 16px 0; }}
        .input-area input {{ flex:1; padding:12px 18px; border-radius:12px; border:1px solid #334155; background:#1e293b; color:#e2e8f0; font-size:1rem; outline:none; }}
        .input-area input:focus {{ border-color:#3b82f6; }}
        .input-area button {{ padding:12px 28px; border-radius:12px; border:none; background:#3b82f6; color:white; font-weight:600; cursor:pointer; }}
        .input-area button:hover {{ background:#2563eb; }}
        .disclaimer {{ font-size:0.7rem; color:#64748b; text-align:center; padding:8px; }}
        .user-info {{ display: flex; align-items: center; gap: 12px; }}
    </style>
    </head>
    <body>
    <div class="header"><h2>⚖️ {brand}</h2><div class="user-info"><span id="userDisplay">👤 Loading...</span><button class="btn" onclick="logout()">Logout</button><a href="/" class="btn">Home</a></div></div>
    <div class="chat-container">
    <div id="chatBox" class="chat-box"><div class="message ai"><strong>{brand}</strong><br>Hello! Welcome to Pocket Lawyer! 👋<br>I am your AI legal assistant for Nigerian Law.<br><br>How can I help you today?</div></div>
    <div class="input-area"><input type="text" id="userInput" placeholder="Type your legal question..." onkeypress="if(event.key===13) sendMessage()"><button onclick="sendMessage()" id="sendBtn">Send</button></div>
    <div class="disclaimer">General guidance only. Consult a lawyer for legal advice.</div>
    </div>
    <script>
    const token = localStorage.getItem('token');
    if (!token) window.location.href = '/auth/login';
    const user = JSON.parse(localStorage.getItem('user') || '{"username":"User"}');
    document.getElementById('userDisplay').textContent = '👤 ' + user.username;
    const chatBox = document.getElementById('chatBox');
    function addMessage(sender, text) {
        const div = document.createElement('div');
        div.className = 'message ' + sender;
        div.textContent = text;
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
    }
    function addTyping() {
        const div = document.createElement('div');
        div.className = 'typing';
        div.id = 'typing';
        div.textContent = 'Thinking...';
        chatBox.appendChild(div);
    }
    function removeTyping() {
        const typing = document.getElementById('typing');
        if (typing) typing.remove();
    }
    async function sendMessage() {
        const input = document.getElementById('userInput');
        const message = input.value.trim();
        if (!message) return;
        input.value = '';
        addMessage('user', message);
        addTyping();
        document.getElementById('sendBtn').disabled = true;
        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + localStorage.getItem('token')},
                body: JSON.stringify({message: message})
            });
            const data = await res.json();
            removeTyping();
            if (data.pdf_url) {
                addMessage('ai', data.reply + ' Download: ' + data.pdf_url);
            } else {
                addMessage('ai', data.reply || 'No response received');
            }
        } catch(e) {
            removeTyping();
            addMessage('ai', 'Error connecting to server.');
        }
        document.getElementById('sendBtn').disabled = false;
    }
    function logout() { localStorage.removeItem('token'); localStorage.removeItem('user'); window.location.href = '/auth/login'; }
    const params = new URLSearchParams(window.location.search);
    const q = params.get('q');
    if (q) { document.getElementById('userInput').value = q; sendMessage(); }
    </script>
    </body>
    </html>
    """)

# ============================================================
# STARTUP
# ============================================================
@app.on_event("startup")
async def startup():
    logger.info(f"Starting {APP_NAME} v{VERSION}")
    logger.info(f"PDF Generation: {'✅' if PDF_AVAILABLE else '❌'}")
    
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                email="admin@pocketlawyer.ai",
                username="admin",
                full_name="System Administrator",
                hashed_password=get_password_hash("admin123"),
                is_superuser=True,
                is_active=True
            )
            db.add(admin)
            db.commit()
            logger.info("✅ Admin user created (admin/admin123)")
        
        if db.query(LegalCase).count() == 0:
            for case in ConfigStore.get_legal_cases():
                db.add(LegalCase(title=case["title"], icon=case["icon"], category=case["category"]))
            db.commit()
            logger.info("✅ Legal cases seeded")
    except Exception as e:
        logger.error(f"Startup error: {e}")
    finally:
        db.close()

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
