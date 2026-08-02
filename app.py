# ============================================================
# POCKET LAWYER v15.0 - COMPLETE WORKING VERSION
# ============================================================
import os
import json
import logging
import asyncio
import threading
import time
import io
import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request, Depends, status
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
import bcrypt

# ============================================================
# LOGGING
# ============================================================
os.makedirs('logs', exist_ok=True)
os.makedirs('database', exist_ok=True)
os.makedirs('documents', exist_ok=True)
os.makedirs('uploads', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/pocket_lawyer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("pocket_lawyer")

VERSION = "15.0.8"
APP_NAME = "Pocket Lawyer"

# ============================================================
# SECURITY
# ============================================================
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(64))
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
# DATABASE MODELS
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

class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    message = Column(Text)
    response = Column(Text)
    provider = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

class LegalCase(Base):
    __tablename__ = "legal_cases"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255))
    icon = Column(String(50))
    category = Column(String(100))
    slug = Column(String(100))
    is_active = Column(Boolean, default=True)
    order = Column(Integer, default=0)

# Create tables
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
            {"title": "🏠 Tenancy & Landlord", "icon": "🏠", "category": "Property"},
            {"title": "💼 Employment Law", "icon": "💼", "category": "Employment"},
            {"title": "📝 Contracts", "icon": "📝", "category": "Business"},
            {"title": "👨‍👩‍👧‍👦 Family Law", "icon": "👨‍👩‍👧‍👦", "category": "Family"},
            {"title": "💰 Debt Recovery", "icon": "💰", "category": "Finance"},
            {"title": "⚖️ Criminal Law", "icon": "⚖️", "category": "Criminal"},
            {"title": "🏢 Corporate Law", "icon": "🏢", "category": "Business"},
            {"title": "🏡 Property Law", "icon": "🏡", "category": "Property"}
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

    @classmethod
    def get_telegram(cls):
        return cls._config.get("telegram", {})

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
def verify_password(plain, hashed):
    try:
        return pwd_context.verify(plain, hashed)
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

async def get_admin_user(current_user: User = Depends(get_current_user_required)):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# ============================================================
# PDF FUNCTIONS
# ============================================================
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    PDF_AVAILABLE = True
except:
    PDF_AVAILABLE = False

documents = {}

async def generate_pdf(title, content):
    if not PDF_AVAILABLE:
        return None
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        story.append(Paragraph(title, styles['Heading1']))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}", styles['Normal']))
        story.append(Spacer(1, 0.2 * inch))
        for line in content.split('\n'):
            if line.strip():
                story.append(Paragraph(line.strip(), styles['Normal']))
                story.append(Spacer(1, 0.1 * inch))
        doc.build(story)
        buffer.seek(0)
        return buffer
    except:
        return None

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
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "full_name": user.full_name,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "subscription_tier": user.subscription_tier,
                "created_at": user.created_at.isoformat() if user.created_at else None
            }
        }
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/auth/login")
async def login(login_data: UserLogin, db: SessionLocal = Depends(get_db)):
    try:
        user = db.query(User).filter(User.username == login_data.username).first()
        if not user:
            user = db.query(User).filter(User.email == login_data.username).first()

        if not user:
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid credentials"})

        if not verify_password(login_data.password, user.hashed_password):
            return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid credentials"})

        if not user.is_active:
            return JSONResponse(status_code=401, content={"status": "error", "message": "Account disabled"})

        user.last_login = datetime.utcnow()
        db.commit()

        token = create_access_token({"user_id": user.id, "username": user.username})
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "full_name": user.full_name,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "subscription_tier": user.subscription_tier,
                "created_at": user.created_at.isoformat() if user.created_at else None
            }
        }
    except Exception as e:
        logger.error(f"Login error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/auth/me")
async def get_current_user_info(current_user: User = Depends(get_current_user_required)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "is_active": current_user.is_active,
        "is_superuser": current_user.is_superuser,
        "subscription_tier": current_user.subscription_tier,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    }

@app.post("/api/auth/logout")
async def logout(current_user: User = Depends(get_current_user_required)):
    return {"status": "success", "message": "Logged out"}

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
async def chat(chat_req: ChatRequest, current_user: Optional[User] = Depends(get_current_user), db: SessionLocal = Depends(get_db)):
    try:
        message = chat_req.message
        if not message:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Message required"})

        # Check for PDF generation
        pdf_keywords = ["generate pdf", "create pdf", "make pdf", "tenancy agreement", "nda"]
        if any(word in message.lower() for word in pdf_keywords):
            title = "Legal Document"
            content = f"This document is generated based on: {message}"
            if "tenancy" in message.lower() or "rent" in message.lower():
                title = "Tenancy Agreement"
                content = """TENANCY AGREEMENT

Parties:
Landlord: _________________________
Tenant: _________________________

Property Address: _________________________

Term: ___ months
Rent: ________ per month

Governing Law: Federal Republic of Nigeria

Signatures:
Landlord: ___________________  Date: _________
Tenant: ___________________  Date: _________

Disclaimer: This is a template. Review by a qualified lawyer is recommended."""
            
            pdf_buffer = await generate_pdf(title, content)
            if pdf_buffer:
                doc_id = f"doc_{int(time.time())}_{hashlib.md5(title.encode()).hexdigest()[:6]}"
                documents[doc_id] = {"title": title, "pdf": pdf_buffer}
                
                if current_user:
                    chat = Chat(user_id=current_user.id, message=message, response=f"Generated PDF: {title}", provider="PDF")
                    db.add(chat)
                    db.commit()
                
                return {
                    "reply": f"✅ Document generated: {title}",
                    "pdf_url": f"/api/documents/{doc_id}/download",
                    "document_id": doc_id,
                    "is_pdf": True
                }

        # Get AI response
        result = await get_ai_response([{"role": "user", "content": message}])
        
        # Save chat
        if current_user:
            chat = Chat(user_id=current_user.id, message=message, response=result["reply"], provider=result.get("provider", "AI"))
            db.add(chat)
            db.commit()
        
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
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={doc['title']}.pdf"}
    )

# ============================================================
# ADMIN - USERS
# ============================================================
@app.get("/admin/users")
async def admin_users(current_user: User = Depends(get_admin_user), db: SessionLocal = Depends(get_db)):
    users = db.query(User).all()
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>User Management</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }
        .header { background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { color: #60a5fa; }
        .btn { padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }
        .btn-primary { background: #3b82f6; color: white; }
        .btn-secondary { background: #334155; color: white; }
        .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; }
        .badge { padding: 4px 12px; border-radius: 12px; font-size: 0.75rem; display: inline-block; }
        .badge-admin { background: #f59e0b20; color: #f59e0b; border: 1px solid #f59e0b40; }
        .badge-user { background: #3b82f620; color: #60a5fa; border: 1px solid #3b82f640; }
        .badge-active { background: #10b98120; color: #10b981; border: 1px solid #10b98140; }
        .badge-inactive { background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }
    </style>
    </head>
    <body>
        <div class="header"><h1>👥 User Management</h1><div><a href="/admin" class="btn btn-secondary">← Back</a><a href="/" class="btn btn-secondary">🏠 Home</a></div></div>
        <div class="container">
            <table>
                <thead><tr><th>ID</th><th>Username</th><th>Email</th><th>Full Name</th><th>Role</th><th>Status</th><th>Plan</th><th>Joined</th></tr></thead>
                <tbody>
    """
    for user in users:
        role = "Admin" if user.is_superuser else "User"
        badge_role = "badge-admin" if user.is_superuser else "badge-user"
        status = "Active" if user.is_active else "Inactive"
        badge_status = "badge-active" if user.is_active else "badge-inactive"
        html += f"""
        <tr>
            <td>{user.id}</td>
            <td><strong>{user.username}</strong></td>
            <td>{user.email}</td>
            <td>{user.full_name or '-'}</td>
            <td><span class="badge {badge_role}">{role}</span></td>
            <td><span class="badge {badge_status}">{status}</span></td>
            <td>{user.subscription_tier.capitalize()}</td>
            <td>{user.created_at.strftime('%Y-%m-%d') if user.created_at else '-'}</td>
        </tr>
        """
    html += """
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)

# ============================================================
# ADMIN - LOGS
# ============================================================
@app.get("/admin/logs")
async def admin_logs(current_user: User = Depends(get_admin_user)):
    logs = []
    try:
        with open("logs/pocket_lawyer.log", "r") as f:
            logs = f.readlines()[-100:]
    except:
        logs = ["No logs available"]
    
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>System Logs</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: 'Courier New', monospace; background: #0f172a; color: #e2e8f0; }
        .header { background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { color: #60a5fa; }
        .btn { padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }
        .btn-secondary { background: #334155; color: white; }
        .container { max-width: 1400px; margin: 0 auto; padding: 24px; }
        .log-container { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 16px; max-height: 600px; overflow-y: auto; }
        .log-line { padding: 4px 0; border-bottom: 1px solid #1e293b; color: #94a3b8; font-size: 0.8rem; }
        .log-error { color: #ef4444; }
        .log-warning { color: #f59e0b; }
        .log-info { color: #60a5fa; }
        .log-success { color: #10b981; }
    </style>
    </head>
    <body>
        <div class="header"><h1>📋 System Logs</h1><div><a href="/admin" class="btn btn-secondary">← Back</a><a href="/" class="btn btn-secondary">🏠 Home</a></div></div>
        <div class="container">
            <div class="log-container">
    """
    for line in logs:
        line = line.strip()
        if not line:
            continue
        if "ERROR" in line:
            cls = "log-error"
        elif "WARNING" in line:
            cls = "log-warning"
        elif "✅" in line or "SUCCESS" in line:
            cls = "log-success"
        else:
            cls = "log-info"
        html += f'<div class="log-line {cls}">{line}</div>'
    html += """
            </div>
            <div style="margin-top:12px;color:#64748b;font-size:0.8rem;">Showing last 100 log entries</div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)

# ============================================================
# ADMIN DASHBOARD
# ============================================================
@app.get("/admin")
async def admin_dashboard(current_user: User = Depends(get_admin_user), db: SessionLocal = Depends(get_db)):
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_chats = db.query(Chat).count()
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>Admin Dashboard</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
        .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; }}
        .header h1 {{ color: #60a5fa; }}
        .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }}
        .btn-primary {{ background: #3b82f6; color: white; }}
        .btn-secondary {{ background: #334155; color: white; }}
        .btn-success {{ background: #10b981; color: white; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .stat-card {{ background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; text-align: center; }}
        .stat-value {{ font-size: 2rem; font-weight: bold; color: #60a5fa; }}
        .stat-label {{ color: #94a3b8; }}
        .card {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px; }}
        .card h3 {{ color: #f59e0b; margin-bottom: 12px; }}
        .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
        @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
    </style>
    </head>
    <body>
        <div class="header"><h1>⚖️ Admin Dashboard</h1><div><a href="/chat" class="btn btn-primary">💬 Chat</a><a href="/" class="btn btn-secondary">🏠 Home</a></div></div>
        <div class="container">
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-value">{total_users}</div><div class="stat-label">Total Users</div></div>
                <div class="stat-card"><div class="stat-value">{active_users}</div><div class="stat-label">Active Users</div></div>
                <div class="stat-card"><div class="stat-value">{total_chats}</div><div class="stat-label">Total Chats</div></div>
                <div class="stat-card"><div class="stat-value">{"✅" if PDF_AVAILABLE else "❌"}</div><div class="stat-label">PDF Generation</div></div>
            </div>
            <div class="grid-2">
                <div class="card">
                    <h3>🔧 Admin Actions</h3>
                    <div class="actions">
                        <a href="/admin/users" class="btn btn-primary">👥 Users</a>
                        <a href="/admin/logs" class="btn btn-primary">📋 Logs</a>
                    </div>
                </div>
                <div class="card">
                    <h3>ℹ️ System Info</h3>
                    <p>📊 Version: {VERSION}</p>
                    <p>📄 PDF: {"✅ Available" if PDF_AVAILABLE else "❌ Not Available"}</p>
                    <p>🤖 AI Providers: {len([p for p in ConfigStore.get_ai_providers() if p.get("enabled")])}/{len(ConfigStore.get_ai_providers())}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "version": VERSION,
        "pdf_available": PDF_AVAILABLE,
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================
# FRONTEND PAGES
# ============================================================
def read_template(filename):
    try:
        with open(f"templates/{filename}", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return f"<h1>Template {filename} not found</h1>"

@app.get("/")
async def home():
    return HTMLResponse(read_template("home.html"))

@app.get("/auth/login")
async def login_page():
    return HTMLResponse(read_template("login.html"))

@app.get("/auth/register")
async def register_page():
    return HTMLResponse(read_template("register.html"))

@app.get("/chat")
async def chat_ui():
    return HTMLResponse(read_template("chat.html"))

# ============================================================
# TELEGRAM INTEGRATION
# ============================================================
telegram_running = False

def start_telegram_polling():
    global telegram_running
    tg = ConfigStore.get_telegram()
    if not tg.get("enabled") or not tg.get("bot_token"):
        logger.info("Telegram not configured")
        return
    telegram_running = True
    threading.Thread(target=run_telegram_polling, daemon=True).start()
    logger.info("Telegram polling started")

def stop_telegram_polling():
    global telegram_running
    telegram_running = False

def run_telegram_polling():
    global telegram_running
    offset = 0
    brand = ConfigStore.get("brand_name", "Pocket Lawyer")
    while telegram_running:
        try:
            tg = ConfigStore.get_telegram()
            if not tg.get("enabled") or not tg.get("bot_token"):
                time.sleep(5)
                continue
            if offset == 0:
                offset = tg.get("last_offset", 0)
            response = httpx.get(
                f"https://api.telegram.org/bot{tg['bot_token']}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=45
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update.get("update_id", 0) + 1
                        ConfigStore.get_telegram()["last_offset"] = offset
                        if "message" in update:
                            msg = update["message"]
                            chat_id = str(msg.get("chat", {}).get("id", ""))
                            text = msg.get("text", "")
                            if chat_id and text and not text.startswith("/"):
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                result = loop.run_until_complete(get_ai_response([{"role": "user", "content": text}]))
                                loop.close()
                                reply = result.get("reply", "I'm sorry, I couldn't process that.")
                                send_url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
                                httpx.post(send_url, json={"chat_id": chat_id, "text": f"{reply}\n\n- {brand}"}, timeout=10)
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            time.sleep(5)

# ============================================================
# STARTUP
# ============================================================
@app.on_event("startup")
async def startup():
    logger.info(f"🚀 Starting {APP_NAME} v{VERSION}")
    logger.info(f"📄 PDF Generation: {'✅' if PDF_AVAILABLE else '❌'}")
    
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
            for i, case in enumerate(ConfigStore.get_legal_cases()):
                db.add(LegalCase(
                    title=case["title"],
                    icon=case["icon"],
                    category=case["category"],
                    order=i,
                    is_active=True
                ))
            db.commit()
            logger.info("✅ Legal cases seeded")
        
        start_telegram_polling()
        logger.info("✅ Services initialized")
    except Exception as e:
        logger.error(f"Startup error: {e}")
    finally:
        db.close()

@app.on_event("shutdown")
async def shutdown():
    stop_telegram_polling()
    logger.info("Shutting down")

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
