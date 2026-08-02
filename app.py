# ============================================================
# POCKET LAWYER v15.0 - ROBUST ENHANCED COMPLETE EDITION
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
from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Depends, status, Form, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr, validator
import httpx
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, JSON, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext
import stripe
from cryptography.fernet import Fernet
import websockets
from contextlib import asynccontextmanager
import analytics
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import bcrypt

# ============================================================
# LOGGING
# ============================================================
os.makedirs('logs', exist_ok=True)
os.makedirs('data', exist_ok=True)
os.makedirs('documents', exist_ok=True)
os.makedirs('uploads', exist_ok=True)
os.makedirs('database', exist_ok=True)
os.makedirs('backups', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/pocket_lawyer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("pocket_lawyer")

VERSION = "15.0.2"
APP_NAME = "Pocket Lawyer"

# ============================================================
# SECURITY & ENCRYPTION
# ============================================================
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(64))
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
cipher_suite = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# ============================================================
# DATABASE SETUP
# ============================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database/pocket_lawyer.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True,
    pool_recycle=3600
)
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
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)
    subscription_tier = Column(String(50), default="free")
    subscription_expires = Column(DateTime)
    api_key = Column(String(100), unique=True, index=True)
    reset_token = Column(String(255))
    reset_token_expires = Column(DateTime)
    email_verified = Column(Boolean, default=False)
    email_verify_token = Column(String(255))
    
    documents = relationship("Document", back_populates="user")
    chats = relationship("Chat", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String(255))
    content = Column(Text)
    filename = Column(String(255))
    file_path = Column(String(500))
    file_size = Column(Integer)
    document_type = Column(String(50))
    is_encrypted = Column(Boolean, default=True)
    is_signed = Column(Boolean, default=False)
    signature_hash = Column(String(255))
    signature_date = Column(DateTime)
    version = Column(Integer, default=1)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document")

class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"))
    version_number = Column(Integer)
    content_hash = Column(String(255))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    document = relationship("Document", back_populates="versions")

class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    session_id = Column(String(100))
    message = Column(Text)
    response = Column(Text)
    provider = Column(String(50))
    tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="chats")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    stripe_payment_id = Column(String(255))
    amount = Column(Float)
    currency = Column(String(10))
    plan = Column(String(50))
    status = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="payments")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    action = Column(String(100))
    resource = Column(String(100))
    resource_id = Column(String(100))
    details = Column(JSON)
    ip_address = Column(String(50))
    user_agent = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="audit_logs")

class LegalCase(Base):
    __tablename__ = "legal_cases"
    id = Column(Integer, primary_key=True, index=True)
    case_type = Column(String(100))
    title = Column(String(255))
    description = Column(Text)
    category = Column(String(100))
    icon = Column(String(50))
    slug = Column(String(100))
    is_active = Column(Boolean, default=True)
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class ProviderStat(Base):
    __tablename__ = "provider_stats"
    id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String(100))
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    total_requests = Column(Integer, default=0)
    avg_response_time = Column(Float, default=0)
    last_used = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username must contain only letters, numbers, and underscores')
        return v

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
    email_verified: bool

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)

class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)

# ============================================================
# CONFIG STORE
# ============================================================
class ConfigStore:
    _config = {
        "brand_name": "Pocket Lawyer",
        "brand_color": "#1a56db",
        "currency": "NGN",
        "system_prompt": """You are Pocket Lawyer, an expert AI legal assistant for Nigerian Law.
        You provide helpful, accurate, and professional legal guidance.
        Always remind users that you are an AI and they should consult a qualified lawyer for specific legal advice.""",
        "max_free_requests": 50,
        "max_pro_requests": 1000,
        "max_enterprise_requests": 10000,
        "ai_providers": [
            {"name": "Groq", "enabled": True, "priority": 1,
             "api_key": os.getenv("GROQ_API_KEY", ""),
             "model": "llama-3.3-70b-versatile",
             "base_url": "https://api.groq.com/openai/v1"},
            {"name": "SambaNova", "enabled": True, "priority": 2,
             "api_key": os.getenv("SAMBANOVA_API_KEY", ""),
             "model": "Meta-Llama-3.3-70B-Instruct",
             "base_url": "https://api.sambanova.ai/v1"},
            {"name": "Mistral", "enabled": True, "priority": 3,
             "api_key": os.getenv("MISTRAL_API_KEY", ""),
             "model": "mistral-large-latest",
             "base_url": "https://api.mistral.ai/v1"},
            {"name": "OpenRouter", "enabled": True, "priority": 4,
             "api_key": os.getenv("OPENROUTER_API_KEY", ""),
             "model": "mistralai/mistral-large",
             "base_url": "https://openrouter.ai/api/v1"}
        ],
        "telegram": {
            "enabled": False,
            "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "bot_username": "Mypocket_lawyerbot",
            "last_offset": 0
        },
        "whatsapp": {
            "enabled": False,
            "phone_number_id": "",
            "access_token": "",
            "verify_token": "pocket_lawyer_2024"
        },
        "plans": [
            {"name": "Free", "slug": "free", "price_monthly": 0,
             "features": ["AI Chat (50 requests)", "PDF Analysis"],
             "limits": {"requests": 50}},
            {"name": "Pro", "slug": "pro", "price_monthly": 5000,
             "features": ["AI Chat (1000 requests)", "PDF Analysis", "PDF Generation", "Telegram"],
             "limits": {"requests": 1000}},
            {"name": "Enterprise", "slug": "enterprise", "price_monthly": 15000,
             "features": ["AI Chat (Unlimited)", "PDF Analysis", "PDF Generation",
                         "Telegram", "WhatsApp", "Priority Support"],
             "limits": {"requests": 10000}}
        ],
        "quick_issues": [
            {"id": "tenancy", "title": "🏠 Tenancy & Landlord Disputes", "icon": "🏠", "category": "Property"},
            {"id": "employment", "title": "💼 Employment & Labour Rights", "icon": "💼", "category": "Employment"},
            {"id": "contract", "title": "📝 Contract Disputes", "icon": "📝", "category": "Business"},
            {"id": "family", "title": "👨‍👩‍👧‍👦 Family & Marriage Law", "icon": "👨‍👩‍👧‍👦", "category": "Family"},
            {"id": "debt", "title": "💰 Debt Recovery & Banking", "icon": "💰", "category": "Finance"},
            {"id": "criminal", "title": "⚖️ Criminal Defense", "icon": "⚖️", "category": "Criminal"},
            {"id": "corporate", "title": "🏢 Corporate & Business Law", "icon": "🏢", "category": "Business"},
            {"id": "property", "title": "🏡 Property & Real Estate", "icon": "🏡", "category": "Property"}
        ]
    }

    @classmethod
    def get_all(cls):
        return cls._config

    @classmethod
    def get(cls, key, default=None):
        return cls._config.get(key, default)

    @classmethod
    def set(cls, key, value):
        cls._config[key] = value
        return True

    @classmethod
    def get_ai_providers(cls):
        return cls._config.get("ai_providers", [])

    @classmethod
    def get_plans(cls):
        return cls._config.get("plans", [])

    @classmethod
    def get_telegram(cls):
        return cls._config.get("telegram", {})

    @classmethod
    def get_whatsapp(cls):
        return cls._config.get("whatsapp", {})

    @classmethod
    def get_quick_issues(cls):
        return cls._config.get("quick_issues", [])

    @classmethod
    def get_max_requests(cls, tier="free"):
        limits = cls.get("max_free_requests", 50)
        if tier == "pro":
            limits = cls.get("max_pro_requests", 1000)
        elif tier == "enterprise":
            limits = cls.get("max_enterprise_requests", 10000)
        return limits

# ============================================================
# APP INITIALIZATION
# ============================================================
app = FastAPI(
    title=APP_NAME,
    version=VERSION,
    description="Pocket Lawyer - AI Legal Assistant for Nigerian Law",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# DATABASE DEPENDENCY
# ============================================================
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
    except Exception:
        return False

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def generate_api_key():
    return secrets.token_urlsafe(32)

def generate_reset_token():
    return secrets.token_urlsafe(32)

# ============================================================
# AUTH DEPENDENCIES
# ============================================================
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: SessionLocal = Depends(get_db)
):
    if not credentials:
        return None
    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        return None
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user or not user.is_active:
        return None
    return user

async def get_current_user_required(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: SessionLocal = Depends(get_db)
):
    user = await get_current_user(credentials, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

async def get_current_admin_user(
    current_user: User = Depends(get_current_user_required)
):
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

# ============================================================
# AUDIT LOGGING
# ============================================================
def log_audit(
    user_id: int,
    action: str,
    resource: str,
    resource_id: str,
    details: dict = None,
    request: Request = None
):
    try:
        db = SessionLocal()
        log_entry = AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details or {},
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None
        )
        db.add(log_entry)
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Audit log error: {e}")

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
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("ReportLab not available - PDF generation disabled")

try:
    import fitz
    PDF_READER_AVAILABLE = True
except ImportError:
    PDF_READER_AVAILABLE = False
    logger.warning("PyMuPDF not available - PDF analysis disabled")

# ============================================================
# AI FUNCTIONS
# ============================================================
async def call_provider(base_url, api_key, model, messages):
    try:
        if not base_url or not api_key or not model:
            return None, None
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        system_prompt = ConfigStore.get("system_prompt", "You are Pocket Lawyer.")
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        payload = {
            "model": model,
            "messages": full_messages,
            "temperature": 0.2,
            "max_tokens": 2000
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            start = time.time()
            resp = await client.post(url, json=payload, headers=headers)
            elapsed = time.time() - start
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if content:
                    return content, elapsed
            logger.error(f"Provider error: {resp.status_code} - {resp.text[:200]}")
            return None, None
    except Exception as e:
        logger.error(f"Provider call error: {e}")
        return None, None

async def get_ai_response(messages, db: SessionLocal = None):
    providers = ConfigStore.get_ai_providers()
    for provider in providers:
        if not provider.get("enabled"):
            continue
        name = provider.get("name")
        base_url = provider.get("base_url")
        api_key = provider.get("api_key")
        model = provider.get("model")
        if not base_url or not api_key or not model:
            continue
        try:
            reply, elapsed = await call_provider(base_url, api_key, model, messages)
            if reply:
                # Update provider stats
                if db:
                    stats = db.query(ProviderStat).filter(
                        ProviderStat.provider_name == name
                    ).first()
                    if not stats:
                        stats = ProviderStat(provider_name=name)
                        db.add(stats)
                    stats.success_count += 1
                    stats.total_requests += 1
                    stats.avg_response_time = (
                        (stats.avg_response_time * (stats.total_requests - 1) + elapsed) / stats.total_requests
                    )
                    stats.last_used = datetime.utcnow()
                    db.commit()
                return {"reply": reply, "provider": name}
        except Exception as e:
            logger.error(f"{name} error: {e}")
            if db:
                stats = db.query(ProviderStat).filter(
                    ProviderStat.provider_name == name
                ).first()
                if stats:
                    stats.error_count += 1
                    stats.total_requests += 1
                    db.commit()
        await asyncio.sleep(0.05)
    return {"reply": "I'm having trouble connecting. Please try again later.", "provider": "offline"}

# ============================================================
# PDF GENERATOR
# ============================================================
class PDFGenerator:
    @staticmethod
    def generate_document(title, content, author="Pocket Lawyer"):
        if not PDF_AVAILABLE:
            raise Exception("PDF generation not available")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=72,
            rightMargin=72,
            topMargin=72,
            bottomMargin=72,
            title=title,
            author=author
        )

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=styles['Heading1'],
            alignment=TA_CENTER,
            fontSize=20,
            textColor=colors.HexColor('#1a56db'),
            spaceAfter=30
        ))
        styles.add(ParagraphStyle(
            name='CustomBody',
            parent=styles['Normal'],
            fontSize=11,
            alignment=TA_JUSTIFY,
            spaceAfter=10,
            leading=16
        ))

        story = []
        story.append(Paragraph(f"{ConfigStore.get('brand_name', 'Pocket Lawyer')}", styles['CustomTitle']))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(title, styles['CustomTitle']))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}", styles['CustomBody']))
        story.append(Spacer(1, 0.2 * inch))

        for line in content.split('\n'):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.05 * inch))
            else:
                story.append(Paragraph(line, styles['CustomBody']))

        story.append(PageBreak())
        story.append(Paragraph("DISCLAIMER", styles['CustomTitle']))
        story.append(Paragraph(
            "This document is generated by Pocket Lawyer AI. "
            "Information is for general purposes only. "
            "For specific legal advice, please consult a qualified lawyer.",
            styles['CustomBody']
        ))

        doc.build(story)
        buffer.seek(0)
        return buffer

# ============================================================
# PDF ANALYZER
# ============================================================
class PDFAnalyzer:
    @staticmethod
    def extract_text_from_pdf(file_content):
        if not PDF_READER_AVAILABLE:
            raise Exception("PyMuPDF not installed")
        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except Exception as e:
            raise Exception(f"PDF reading error: {str(e)}")

# ============================================================
# ENCRYPTION FUNCTIONS
# ============================================================
def encrypt_text(text):
    try:
        return cipher_suite.encrypt(text.encode()).decode()
    except Exception:
        return text

def decrypt_text(encrypted_text):
    try:
        return cipher_suite.decrypt(encrypted_text.encode()).decode()
    except Exception:
        return encrypted_text

# ============================================================
# DIGITAL SIGNATURES
# ============================================================
def sign_document(content, user_id):
    timestamp = datetime.utcnow().isoformat()
    signature_data = f"{content}{user_id}{timestamp}"
    signature = hashlib.sha256(signature_data.encode()).hexdigest()
    return {
        "signature": signature,
        "signed_by": user_id,
        "signed_at": timestamp,
        "hash": hashlib.sha256(content.encode()).hexdigest()
    }

def verify_signature(content, signature_data):
    expected = hashlib.sha256(
        f"{content}{signature_data['signed_by']}{signature_data['signed_at']}".encode()
    ).hexdigest()
    return expected == signature_data['signature']

# ============================================================
# DOCUMENT GENERATION FROM CHAT
# ============================================================
documents = {}
uploaded_docs = {}

async def generate_document_from_chat(message):
    if not PDF_AVAILABLE:
        return {"status": "error", "message": "PDF generation not available"}

    title = "Legal Document"
    content = f"""# LEGAL DOCUMENT

Generated based on: {message}

## INTRODUCTION

This document is created based on the request provided.

## TERMS AND CONDITIONS

1. Term 1
2. Term 2
3. Term 3

## GOVERNING LAW

Federal Republic of Nigeria.

## SIGNATURES

_________________________  Date: _________

---
Disclaimer: This is a template. Review by a qualified lawyer is recommended."""

    if any(word in message.lower() for word in ["tenancy", "rent"]):
        title = "Tenancy Agreement"
        content = """# TENANCY AGREEMENT

## PARTIES
**Landlord:** _________________________
**Tenant:** _________________________
**Property Address:** _________________________

## TERMS

### 1. TERM
This agreement shall commence on ___ and continue for ___ months.

### 2. RENT
The tenant shall pay ________ per month.

### 3. GOVERNING LAW
Federal Republic of Nigeria.

## SIGNATURES
**Landlord:** ___________________  Date: _________
**Tenant:** ___________________  Date: _________

---
Disclaimer: This is a template. Review by a qualified lawyer is recommended."""

    doc_id = f"doc_{int(time.time())}_{hashlib.md5(title.encode()).hexdigest()[:6]}"

    try:
        pdf_buffer = PDFGenerator.generate_document(title, content)
        documents[doc_id] = {
            "title": title,
            "content": content,
            "pdf": pdf_buffer,
            "created_at": datetime.utcnow().isoformat()
        }
        return {
            "status": "success",
            "title": title,
            "content": content,
            "document_id": doc_id,
            "pdf_url": f"/api/documents/{doc_id}/download"
        }
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        return {"status": "error", "message": str(e)}

# ============================================================
# AUTH ENDPOINTS
# ============================================================
@app.post("/api/auth/register", response_model=Token)
async def register(user_data: UserCreate, db: SessionLocal = Depends(get_db)):
    try:
        # Check if user exists
        existing = db.query(User).filter(
            (User.email == user_data.email) | (User.username == user_data.username)
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Email or username already registered"
            )

        # Create user
        user = User(
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            hashed_password=get_password_hash(user_data.password),
            api_key=generate_api_key(),
            email_verify_token=generate_api_key()
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create token
        token = create_access_token({"user_id": user.id, "username": user.username})

        log_audit(user.id, "register", "user", str(user.id), {"email": user.email})

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse.from_orm(user)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

@app.post("/api/auth/login", response_model=Token)
async def login(login_data: UserLogin, db: SessionLocal = Depends(get_db)):
    try:
        user = db.query(User).filter(User.username == login_data.username).first()
        if not user:
            user = db.query(User).filter(User.email == login_data.username).first()

        if not user or not verify_password(login_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account disabled"
            )

        user.last_login = datetime.utcnow()
        db.commit()

        token = create_access_token({"user_id": user.id, "username": user.username})

        log_audit(user.id, "login", "user", str(user.id), {"username": user.username})

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse.from_orm(user)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user_required)):
    return UserResponse.from_orm(current_user)

@app.post("/api/auth/logout")
async def logout(current_user: User = Depends(get_current_user_required)):
    log_audit(current_user.id, "logout", "user", str(current_user.id), {})
    return {"status": "success", "message": "Logged out"}

@app.post("/api/auth/refresh")
async def refresh_token(current_user: User = Depends(get_current_user_required)):
    token = create_access_token({"user_id": current_user.id, "username": current_user.username})
    return {"access_token": token, "token_type": "bearer"}

# ============================================================
# PASSWORD RESET ENDPOINTS
# ============================================================
@app.post("/api/auth/forgot-password")
async def forgot_password(
    request: PasswordResetRequest,
    db: SessionLocal = Depends(get_db)
):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate reset token
    reset_token = generate_reset_token()
    user.reset_token = reset_token
    user.reset_token_expires = datetime.utcnow() + timedelta(hours=24)
    db.commit()

    # In production, send email with reset link
    # For now, return token for testing
    return {
        "status": "success",
        "message": "Password reset link sent",
        "reset_token": reset_token  # Remove in production
    }

@app.post("/api/auth/reset-password")
async def reset_password(
    request: PasswordResetConfirm,
    db: SessionLocal = Depends(get_db)
):
    user = db.query(User).filter(
        User.reset_token == request.token,
        User.reset_token_expires > datetime.utcnow()
    ).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user.hashed_password = get_password_hash(request.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()

    log_audit(user.id, "reset_password", "user", str(user.id), {})
    return {"status": "success", "message": "Password reset successfully"}

# ============================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================
@app.get("/api/users")
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user),
    db: SessionLocal = Depends(get_db)
):
    users = db.query(User).offset(skip).limit(limit).all()
    total = db.query(User).count()
    return {
        "status": "success",
        "total": total,
        "users": [UserResponse.from_orm(u) for u in users]
    }

@app.put("/api/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: dict,
    current_user: User = Depends(get_current_admin_user),
    db: SessionLocal = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    allowed_fields = ["is_active", "subscription_tier", "is_superuser"]
    for field in allowed_fields:
        if field in user_data:
            setattr(user, field, user_data[field])

    db.commit()
    log_audit(current_user.id, "update_user", "user", str(user_id), user_data)
    return {"status": "success", "message": "User updated"}

@app.delete("/api/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: SessionLocal = Depends(get_db)
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    db.commit()
    log_audit(current_user.id, "delete_user", "user", str(user_id), {})
    return {"status": "success", "message": "User deleted"}

# ============================================================
# LEGAL CASES ENDPOINTS
# ============================================================
@app.get("/api/legal-cases")
async def get_legal_cases(
    category: Optional[str] = None,
    db: SessionLocal = Depends(get_db)
):
    try:
        query = db.query(LegalCase).filter(LegalCase.is_active == True)
        if category:
            query = query.filter(LegalCase.category == category)
        cases = query.order_by(LegalCase.order).all()

        if not cases:
            # Return default cases
            default_cases = ConfigStore.get_quick_issues()
            return {
                "status": "success",
                "cases": [
                    {
                        "id": i + 1,
                        "title": c["title"],
                        "description": f"Legal assistance for {c['title']}",
                        "category": c.get("category", "General"),
                        "icon": c["icon"],
                        "slug": c["id"]
                    }
                    for i, c in enumerate(default_cases)
                ]
            }

        return {
            "status": "success",
            "cases": [
                {
                    "id": c.id,
                    "title": c.title,
                    "description": c.description,
                    "category": c.category,
                    "icon": c.icon or "⚖️",
                    "slug": c.slug
                }
                for c in cases
            ]
        }
    except Exception as e:
        logger.error(f"Legal cases error: {e}")
        default_cases = ConfigStore.get_quick_issues()
        return {
            "status": "success",
            "cases": [
                {
                    "id": i + 1,
                    "title": c["title"],
                    "description": f"Legal assistance for {c['title']}",
                    "category": c.get("category", "General"),
                    "icon": c["icon"],
                    "slug": c["id"]
                }
                for i, c in enumerate(default_cases)
            ]
        }

# ============================================================
# CHAT ENDPOINT
# ============================================================
@app.post("/api/chat")
async def chat(
    chat_req: ChatRequest,
    current_user: Optional[User] = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    try:
        message = chat_req.message
        if not message:
            raise HTTPException(status_code=400, detail="Message required")

        # Check rate limits for free users
        if current_user and current_user.subscription_tier == "free":
            chat_count = db.query(Chat).filter(
                Chat.user_id == current_user.id,
                Chat.created_at >= datetime.utcnow() - timedelta(days=30)
            ).count()
            max_requests = ConfigStore.get_max_requests("free")
            if chat_count >= max_requests:
                raise HTTPException(
                    status_code=429,
                    detail=f"Monthly request limit reached ({max_requests}). Upgrade to Pro."
                )

        # Check if PDF generation requested
        pdf_keywords = ["generate pdf", "create pdf", "make pdf", "tenancy agreement", "nda"]
        if any(word in message.lower() for word in pdf_keywords):
            result = await generate_document_from_chat(message)
            if result.get("status") == "success":
                if current_user:
                    log_audit(
                        current_user.id,
                        "generate_pdf",
                        "document",
                        result.get("document_id"),
                        {"title": result.get("title")}
                    )
                return {
                    "reply": f"✅ Document generated: {result.get('title')}",
                    "provider": "PDF Generator",
                    "pdf_url": result.get("pdf_url"),
                    "document_id": result.get("document_id"),
                    "is_pdf": True
                }

        # Get AI response
        result = await get_ai_response([{"role": "user", "content": message}], db)

        # Save chat history if authenticated
        if current_user:
            chat = Chat(
                user_id=current_user.id,
                session_id=f"session_{int(time.time())}",
                message=message,
                response=result["reply"],
                provider=result.get("provider", "AI")
            )
            db.add(chat)
            db.commit()

        return {
            "reply": result["reply"],
            "provider": result.get("provider", "AI")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# DOCUMENT ENDPOINTS
# ============================================================
@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user_required),
    db: SessionLocal = Depends(get_db)
):
    try:
        content = await file.read()
        filename = file.filename

        if not filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        if not PDF_READER_AVAILABLE:
            raise HTTPException(status_code=503, detail="PDF reader not available")

        extracted_text = PDFAnalyzer.extract_text_from_pdf(content)

        # Encrypt content
        encrypted_content = encrypt_text(extracted_text)

        doc_id = f"upload_{int(time.time())}_{hashlib.md5(filename.encode()).hexdigest()[:6]}"
        file_path = os.path.join("uploads", f"{doc_id}_{filename}")

        with open(file_path, 'wb') as f:
            f.write(content)

        document = Document(
            user_id=current_user.id,
            title=filename,
            content=encrypted_content,
            filename=filename,
            file_path=file_path,
            file_size=len(content),
            document_type="uploaded",
            is_encrypted=True
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        uploaded_docs[doc_id] = {
            "filename": filename,
            "content": extracted_text,
            "size": len(content),
            "created_at": datetime.utcnow().isoformat(),
            "document_id": document.id
        }

        log_audit(
            current_user.id,
            "upload_document",
            "document",
            str(document.id),
            {"filename": filename}
        )

        return {
            "status": "success",
            "document_id": doc_id,
            "db_id": document.id,
            "filename": filename,
            "characters": len(extracted_text),
            "words": len(extracted_text.split()),
            "message": "PDF uploaded and encrypted successfully!"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/documents/analyze")
async def analyze_document(
    document_id: str,
    current_user: User = Depends(get_current_user_required),
    db: SessionLocal = Depends(get_db)
):
    doc = uploaded_docs.get(document_id)
    if not doc:
        db_doc = db.query(Document).filter(Document.id == document_id).first()
        if db_doc and db_doc.user_id == current_user.id:
            content = decrypt_text(db_doc.content)
            doc = {"content": content, "db_id": db_doc.id}
        else:
            raise HTTPException(status_code=404, detail="Document not found")

    try:
        content = doc["content"]
        if len(content) > 8000:
            content = content[:8000] + "... [truncated]"

        prompt = f"""Please analyze this legal document and provide:
1. A clear summary of what this document is about
2. Key parties involved (if any)
3. Main terms and conditions
4. Potential legal issues or risks
5. Missing clauses or recommendations

Document content:
{content}"""

        result = await get_ai_response([{"role": "user", "content": prompt}], db)

        if result["reply"]:
            doc["analysis"] = result["reply"]
            log_audit(
                current_user.id,
                "analyze_document",
                "document",
                document_id,
                {"analysis_type": "full"}
            )
            return {
                "status": "success",
                "analysis": result["reply"],
                "provider": result["provider"]
            }

        raise HTTPException(status_code=500, detail="Analysis failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents")
async def get_documents(
    current_user: User = Depends(get_current_user_required),
    db: SessionLocal = Depends(get_db)
):
    docs = db.query(Document).filter(
        Document.user_id == current_user.id,
        Document.is_deleted == False
    ).all()

    return {
        "status": "success",
        "documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "filename": doc.filename,
                "file_size": doc.file_size,
                "created_at": doc.created_at,
                "is_signed": doc.is_signed,
                "is_encrypted": doc.is_encrypted,
                "version": doc.version
            }
            for doc in docs
        ]
    }

@app.get("/api/documents/{doc_id}/download")
async def download_document(
    doc_id: str,
    current_user: User = Depends(get_current_user_required)
):
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
# ADMIN DASHBOARD
# ============================================================
@app.get("/admin")
async def admin_dashboard(
    current_user: User = Depends(get_current_admin_user),
    db: SessionLocal = Depends(get_db)
):
    # Get stats
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_chats = db.query(Chat).count()
    total_docs = db.query(Document).count()
    total_payments = db.query(Payment).count()

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard - Pocket Lawyer</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
            .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
            .header h1 {{ color: #60a5fa; }}
            .header h1 span {{ color: #f59e0b; }}
            .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; transition: all 0.3s; }}
            .btn-primary {{ background: #3b82f6; color: white; }}
            .btn-primary:hover {{ background: #2563eb; transform: translateY(-2px); }}
            .btn-secondary {{ background: #334155; color: white; }}
            .btn-secondary:hover {{ background: #475569; transform: translateY(-2px); }}
            .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }}
            .stat-card {{ background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; text-align: center; transition: all 0.3s; }}
            .stat-card:hover {{ border-color: #60a5fa; transform: translateY(-4px); }}
            .stat-value {{ font-size: 2rem; font-weight: bold; color: #60a5fa; }}
            .stat-label {{ color: #94a3b8; font-size: 0.85rem; margin-top: 4px; }}
            .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
            .card {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; }}
            .card h3 {{ color: #f59e0b; margin-bottom: 12px; }}
            .card p {{ color: #94a3b8; margin: 4px 0; }}
            .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
            @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} .header {{ flex-direction: column; text-align: center; }} }}
        </style>
    </head>
    <body>
        <div class="header">
            <div><h1>⚖️ <span>Pocket</span> Lawyer Admin</h1></div>
            <div>
                <a href="/chat" class="btn btn-primary">💬 Chat</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
            </div>
        </div>
        <div class="container">
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-value">{total_users}</div><div class="stat-label">Total Users</div></div>
                <div class="stat-card"><div class="stat-value">{active_users}</div><div class="stat-label">Active Users</div></div>
                <div class="stat-card"><div class="stat-value">{total_chats}</div><div class="stat-label">Total Chats</div></div>
                <div class="stat-card"><div class="stat-value">{total_docs}</div><div class="stat-label">Documents</div></div>
                <div class="stat-card"><div class="stat-value">{total_payments}</div><div class="stat-label">Payments</div></div>
                <div class="stat-card"><div class="stat-value">v{VERSION}</div><div class="stat-label">Version</div></div>
            </div>

            <div class="grid-2">
                <div class="card">
                    <h3>🔧 Admin Actions</h3>
                    <div class="actions">
                        <a href="/admin/users" class="btn btn-primary">👥 Users</a>
                        <a href="/admin/logs" class="btn btn-primary">📋 Logs</a>
                        <a href="/admin/settings" class="btn btn-primary">⚙️ Settings</a>
                        <a href="/admin/analytics" class="btn btn-primary">📊 Analytics</a>
                    </div>
                </div>
                <div class="card">
                    <h3>ℹ️ System Info</h3>
                    <p>📊 Status: <span style="color:#10b981;">● Online</span></p>
                    <p>📄 PDF Generation: <span style="color:{"#10b981" if PDF_AVAILABLE else "#ef4444"};">{"✅" if PDF_AVAILABLE else "❌"}</span></p>
                    <p>📑 PDF Reader: <span style="color:{"#10b981" if PDF_READER_AVAILABLE else "#ef4444"};">{"✅" if PDF_READER_AVAILABLE else "❌"}</span></p>
                    <p>🤖 AI Providers: <span style="color:#60a5fa;">{len([p for p in ConfigStore.get_ai_providers() if p.get("enabled")])}/{len(ConfigStore.get_ai_providers())} Active</span></p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

# ============================================================
# ADMIN USER MANAGEMENT
# ============================================================
@app.get("/admin/users")
async def admin_users(
    current_user: User = Depends(get_current_admin_user),
    db: SessionLocal = Depends(get_db)
):
    users = db.query(User).order_by(User.created_at.desc()).all()

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>User Management - Pocket Lawyer</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
            .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
            .header h1 {{ color: #60a5fa; }}
            .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }}
            .btn-primary {{ background: #3b82f6; color: white; }}
            .btn-secondary {{ background: #334155; color: white; }}
            .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #334155; }}
            th {{ color: #94a3b8; font-weight: 600; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; }}
            td {{ color: #e2e8f0; }}
            .badge {{ padding: 4px 12px; border-radius: 12px; font-size: 0.75rem; display: inline-block; }}
            .badge-admin {{ background: #f59e0b20; color: #f59e0b; border: 1px solid #f59e0b40; }}
            .badge-user {{ background: #3b82f620; color: #60a5fa; border: 1px solid #3b82f640; }}
            .badge-active {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
            .badge-inactive {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
            .badge-free {{ background: #64748b20; color: #94a3b8; border: 1px solid #64748b40; }}
            .badge-pro {{ background: #3b82f620; color: #60a5fa; border: 1px solid #3b82f640; }}
            .badge-enterprise {{ background: #8b5cf620; color: #a78bfa; border: 1px solid #8b5cf640; }}
            @media (max-width: 768px) {{ table {{ font-size: 0.8rem; }} th, td {{ padding: 8px; }} }}
        </style>
    </head>
    <body>
        <div class="header">
            <div><h1>👥 User Management</h1></div>
            <div>
                <a href="/admin" class="btn btn-secondary">← Back</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
            </div>
        </div>
        <div class="container">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Username</th>
                        <th>Email</th>
                        <th>Full Name</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Plan</th>
                        <th>Joined</th>
                    </tr>
                </thead>
                <tbody>
    """

    for user in users:
        role = "Admin" if user.is_superuser else "User"
        badge_role = "badge-admin" if user.is_superuser else "badge-user"
        status = "Active" if user.is_active else "Inactive"
        badge_status = "badge-active" if user.is_active else "badge-inactive"
        plan = user.subscription_tier or "free"
        badge_plan = f"badge-{plan}"

        html += f"""
        <tr>
            <td>{user.id}</td>
            <td><strong>{user.username}</strong></td>
            <td>{user.email}</td>
            <td>{user.full_name or '-'}</td>
            <td><span class="badge {badge_role}">{role}</span></td>
            <td><span class="badge {badge_status}">{status}</span></td>
            <td><span class="badge {badge_plan}">{plan.capitalize()}</span></td>
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
# ADMIN LOGS VIEWER
# ============================================================
@app.get("/admin/logs")
async def admin_logs(
    current_user: User = Depends(get_current_admin_user)
):
    logs = []
    try:
        with open("logs/pocket_lawyer.log", "r") as f:
            logs = f.readlines()[-100:]
    except:
        logs = ["No logs available"]

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>System Logs - Pocket Lawyer</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
            .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
            .header h1 {{ color: #60a5fa; }}
            .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }}
            .btn-primary {{ background: #3b82f6; color: white; }}
            .btn-secondary {{ background: #334155; color: white; }}
            .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
            .log-container {{ background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 16px; font-family: 'Courier New', monospace; font-size: 0.8rem; max-height: 600px; overflow-y: auto; }}
            .log-line {{ padding: 4px 0; border-bottom: 1px solid #1e293b; color: #94a3b8; font-size: 0.75rem; line-height: 1.4; word-break: break-all; }}
            .log-error {{ color: #ef4444; }}
            .log-warning {{ color: #f59e0b; }}
            .log-info {{ color: #60a5fa; }}
            .log-success {{ color: #10b981; }}
            .log-debug {{ color: #64748b; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div><h1>📋 System Logs</h1></div>
            <div>
                <a href="/admin" class="btn btn-secondary">← Back</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
            </div>
        </div>
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
        elif "SUCCESS" in line or "✅" in line:
            cls = "log-success"
        elif "DEBUG" in line:
            cls = "log-debug"
        else:
            cls = "log-info"

        # Escape HTML entities
        line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html += f'<div class="log-line {cls}">{line}</div>'

    html += """
            </div>
            <div style="margin-top:12px;color:#64748b;font-size:0.8rem;">
                Showing last 100 log entries
            </div>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(html)

# ============================================================
# ADMIN SETTINGS
# ============================================================
@app.get("/admin/settings")
async def admin_settings(
    current_user: User = Depends(get_current_admin_user)
):
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Settings - Pocket Lawyer</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin:0; padding:0; box-sizing:border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }
            .header { background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
            .header h1 { color: #60a5fa; }
            .btn { padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }
            .btn-primary { background: #3b82f6; color: white; }
            .btn-secondary { background: #334155; color: white; }
            .container { max-width: 800px; margin: 0 auto; padding: 24px; }
            .card { background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px; }
            .card h3 { color: #f59e0b; margin-bottom: 12px; }
            .card p { color: #94a3b8; line-height: 1.6; }
            .form-group { margin-bottom: 16px; }
            .form-group label { color: #94a3b8; display: block; margin-bottom: 4px; font-size: 0.9rem; }
            .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 1rem; }
            .form-group input:focus, .form-group select:focus, .form-group textarea:focus { border-color: #3b82f6; outline: none; }
            .form-group textarea { min-height: 100px; resize: vertical; }
            .btn-save { background: #10b981; color: white; padding: 10px 24px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
            .btn-save:hover { background: #059669; }
        </style>
    </head>
    <body>
        <div class="header">
            <div><h1>⚙️ System Settings</h1></div>
            <div>
                <a href="/admin" class="btn btn-secondary">← Back</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
            </div>
        </div>
        <div class="container">
            <div class="card">
                <h3>ℹ️ Configuration</h3>
                <p>System settings can be configured using environment variables in Render.</p>
                <p style="margin-top:8px;">Current settings are loaded from the environment at startup.</p>
            </div>

            <div class="card">
                <h3>📧 Email Settings</h3>
                <p>Configure SMTP for email notifications.</p>
                <div style="margin-top:12px;color:#94a3b8;font-size:0.9rem;">
                    <p>SMTP_HOST: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">{{ SMTP_HOST or 'Not set' }}</code></p>
                    <p>SMTP_PORT: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">{{ SMTP_PORT or 'Not set' }}</code></p>
                    <p>SMTP_USER: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">{{ SMTP_USER or 'Not set' }}</code></p>
                </div>
            </div>

            <div class="card">
                <h3>🤖 AI Providers</h3>
                <p>Configure AI providers in the environment variables.</p>
                <div style="margin-top:12px;color:#94a3b8;font-size:0.9rem;">
                    <p>Available: Groq, SambaNova, Mistral, OpenRouter</p>
                </div>
            </div>

            <div class="card">
                <h3>📱 Telegram & WhatsApp</h3>
                <p>Configure messaging integrations via environment variables.</p>
                <div style="margin-top:12px;color:#94a3b8;font-size:0.9rem;">
                    <p>Telegram: <span style="color:#60a5fa;">{{ 'Enabled' if TELEGRAM_BOT_TOKEN else 'Disabled' }}</span></p>
                    <p>WhatsApp: <span style="color:#60a5fa;">{{ 'Configured' if WHATSAPP_ACCESS_TOKEN else 'Not configured' }}</span></p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

# ============================================================
# ANALYTICS DASHBOARD
# ============================================================
@app.get("/admin/analytics")
async def admin_analytics(
    current_user: User = Depends(get_current_admin_user),
    db: SessionLocal = Depends(get_db)
):
    # Get stats
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_chats = db.query(Chat).count()
    total_docs = db.query(Document).count()
    total_payments = db.query(Payment).filter(Payment.status == "completed").count()
    total_revenue = db.query(func.sum(Payment.amount)).filter(Payment.status == "completed").scalar() or 0

    # Get provider stats
    provider_stats = db.query(ProviderStat).all()

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Analytics - Pocket Lawyer</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
            .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
            .header h1 {{ color: #60a5fa; }}
            .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }}
            .btn-primary {{ background: #3b82f6; color: white; }}
            .btn-secondary {{ background: #334155; color: white; }}
            .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }}
            .stat-card {{ background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; text-align: center; }}
            .stat-value {{ font-size: 1.8rem; font-weight: bold; color: #60a5fa; }}
            .stat-label {{ color: #94a3b8; font-size: 0.85rem; margin-top: 4px; }}
            .card {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px; }}
            .card h3 {{ color: #f59e0b; margin-bottom: 12px; }}
            .provider-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #1e293b; }}
            .provider-name {{ color: #e2e8f0; }}
            .provider-stats {{ color: #94a3b8; font-size: 0.9rem; }}
            .success-rate {{ color: #10b981; }}
            .error-rate {{ color: #ef4444; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div><h1>📊 Analytics Dashboard</h1></div>
            <div>
                <a href="/admin" class="btn btn-secondary">← Back</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
            </div>
        </div>
        <div class="container">
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-value">{total_users}</div><div class="stat-label">Total Users</div></div>
                <div class="stat-card"><div class="stat-value">{active_users}</div><div class="stat-label">Active Users</div></div>
                <div class="stat-card"><div class="stat-value">{total_chats}</div><div class="stat-label">Total Chats</div></div>
                <div class="stat-card"><div class="stat-value">{total_docs}</div><div class="stat-label">Documents</div></div>
                <div class="stat-card"><div class="stat-value">{total_payments}</div><div class="stat-label">Payments</div></div>
                <div class="stat-card"><div class="stat-value">₦{total_revenue:,.0f}</div><div class="stat-label">Revenue</div></div>
            </div>

            <div class="card">
                <h3>🤖 AI Provider Performance</h3>
    """

    if provider_stats:
        for stat in provider_stats:
            success_rate = (stat.success_count / max(1, stat.total_requests)) * 100
            error_rate = (stat.error_count / max(1, stat.total_requests)) * 100
            html += f"""
            <div class="provider-row">
                <span class="provider-name">{stat.provider_name}</span>
                <span class="provider-stats">
                    Requests: {stat.total_requests} |
                    Success: <span class="success-rate">{stat.success_count}</span> |
                    Errors: <span class="error-rate">{stat.error_count}</span> |
                    Rate: <span class="success-rate">{success_rate:.1f}%</span>
                </span>
            </div>
            """
    else:
        html += """
            <p style="color:#94a3b8;">No provider data available yet. Start using the chat to collect stats.</p>
        """

    html += """
            </div>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(html)

# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/api/health")
async def health_check(db: SessionLocal = Depends(get_db)):
    try:
        # Test database connection
        db.execute("SELECT 1")
        db_status = "healthy"
    except:
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": VERSION,
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status,
        "pdf_available": PDF_AVAILABLE,
        "pdf_reader": PDF_READER_AVAILABLE,
        "providers": {
            "total": len(ConfigStore.get_ai_providers()),
            "active": len([p for p in ConfigStore.get_ai_providers() if p.get("enabled")])
        }
    }

# ============================================================
# GLOBAL ERROR HANDLER
# ============================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An unexpected error occurred",
            "detail": str(exc) if os.getenv("DEBUG", "False").lower() == "true" else None
        }
    )

# ============================================================
# STARTUP EVENT
# ============================================================
@app.on_event("startup")
async def startup():
    logger.info(f"🚀 Starting {APP_NAME} v{VERSION}")
    logger.info(f"📄 PDF Generation: {'✅' if PDF_AVAILABLE else '❌'}")
    logger.info(f"📑 PDF Reader: {'✅' if PDF_READER_AVAILABLE else '❌'}")
    logger.info(f"🗄️  Database: {DATABASE_URL.split('://')[0]}")

    # Create admin user if not exists
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
                is_active=True,
                api_key=generate_api_key(),
                email_verified=True
            )
            db.add(admin)
            db.commit()
            logger.info("✅ Admin user created (username: admin, password: admin123)")
        else:
            logger.info("✅ Admin user already exists")

        # Seed legal cases if empty
        cases = db.query(LegalCase).count()
        if cases == 0:
            default_cases = [
                {"case_type": "tenancy", "title": "🏠 Tenancy & Landlord Disputes",
                 "description": "Resolve landlord-tenant disputes, rent issues, and eviction matters",
                 "category": "Property", "icon": "🏠", "slug": "tenancy", "order": 1},
                {"case_type": "employment", "title": "💼 Employment & Labour Rights",
                 "description": "Know your rights as an employee or employer in Nigeria",
                 "category": "Employment", "icon": "💼", "slug": "employment", "order": 2},
                {"case_type": "contract", "title": "📝 Contract Disputes",
                 "description": "Breach of contract, agreement drafting, and dispute resolution",
                 "category": "Business", "icon": "📝", "slug": "contract", "order": 3},
                {"case_type": "family", "title": "👨‍👩‍👧‍👦 Family & Marriage Law",
                 "description": "Marriage, divorce, child custody, and family matters",
                 "category": "Family", "icon": "👨‍👩‍👧‍👦", "slug": "family", "order": 4},
                {"case_type": "debt", "title": "💰 Debt Recovery & Banking",
                 "description": "Debt collection, loan recovery, and banking disputes",
                 "category": "Finance", "icon": "💰", "slug": "debt", "order": 5},
                {"case_type": "criminal", "title": "⚖️ Criminal Defense",
                 "description": "Criminal charges, defense strategies, and legal representation",
                 "category": "Criminal", "icon": "⚖️", "slug": "criminal", "order": 6},
                {"case_type": "corporate", "title": "🏢 Corporate & Business Law",
                 "description": "Company registration, compliance, and corporate governance",
                 "category": "Business", "icon": "🏢", "slug": "corporate", "order": 7},
                {"case_type": "property", "title": "🏡 Property & Real Estate",
                 "description": "Property transactions, disputes, and real estate law",
                 "category": "Property", "icon": "🏡", "slug": "property", "order": 8}
            ]
            for case_data in default_cases:
                case = LegalCase(**case_data)
                db.add(case)
            db.commit()
            logger.info(f"✅ Seeded {len(default_cases)} legal cases")

        # Check AI providers
        providers = ConfigStore.get_ai_providers()
        enabled = [p for p in providers if p.get("enabled") and p.get("api_key")]
        logger.info(f"🤖 AI Providers: {len(enabled)}/{len(providers)} active")

    except Exception as e:
        logger.error(f"Startup error: {e}")
    finally:
        db.close()

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("DEBUG", "False").lower() == "true"
    )
