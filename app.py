# ============================================================
# POCKET LAWYER v15.0 - COMPLETE ENHANCED EDITION
# ============================================================
# Features: Full Auth · Telegram · WhatsApp · Payments (Online/Manual) · Legal Cases
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
from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Depends, status, Form, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr, validator
import httpx
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, JSON, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext
import stripe
from cryptography.fernet import Fernet
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import bcrypt
from typing import Optional
import json
import re

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

VERSION = "15.0.3"
APP_NAME = "Pocket Lawyer"

# ============================================================
# SECURITY
# ============================================================
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(64))
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
cipher_suite = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# ============================================================
# DATABASE
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
    phone_number = Column(String(20))
    telegram_chat_id = Column(String(100))
    whatsapp_number = Column(String(20))
    email_verified = Column(Boolean, default=False)
    reset_token = Column(String(255))
    reset_token_expires = Column(DateTime)

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    payment_id = Column(String(255), unique=True)
    amount = Column(Float)
    currency = Column(String(10), default="NGN")
    plan = Column(String(50))
    payment_method = Column(String(50))  # 'stripe', 'bank_transfer', 'manual'
    status = Column(String(50))  # 'pending', 'completed', 'failed', 'cancelled'
    reference = Column(String(255))
    transaction_id = Column(String(255))
    payment_date = Column(DateTime)
    expiry_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

class TelegramMessage(Base):
    __tablename__ = "telegram_messages"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String(100))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    message = Column(Text)
    response = Column(Text)
    is_processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"
    id = Column(Integer, primary_key=True, index=True)
    from_number = Column(String(20))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    message = Column(Text)
    response = Column(Text)
    is_processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

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
    phone_number: Optional[str] = None

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
    phone_number: Optional[str]
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)

class PaymentRequest(BaseModel):
    plan: str
    payment_method: str = "stripe"  # 'stripe', 'bank_transfer', 'manual'

class BankTransferPayment(BaseModel):
    plan: str
    amount: float
    reference: str
    transaction_id: str

class ManualPayment(BaseModel):
    plan: str
    amount: float
    reference: str
    notes: Optional[str] = None

class TelegramTestRequest(BaseModel):
    chat_id: str
    message: str = "Test message"

class WhatsAppTestRequest(BaseModel):
    to: str
    message: str = "Test message"

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
        Always remind users that you are an AI and they should consult a qualified lawyer for specific legal advice.
        Be warm, welcoming, and professional in your responses.""",
        "bank_details": {
            "bank_name": "GTBank",
            "account_name": "Pocket Lawyer Limited",
            "account_number": "0123456789",
            "bank_code": "058"
        },
        "plans": [
            {"name": "Free", "slug": "free", "price_monthly": 0,
             "features": ["AI Chat (50 requests)", "PDF Analysis", "Basic Support"],
             "limits": {"requests": 50}},
            {"name": "Pro", "slug": "pro", "price_monthly": 5000,
             "features": ["AI Chat (1000 requests)", "PDF Analysis", "PDF Generation", 
                         "Telegram Bot", "Priority Support", "Document Storage"],
             "limits": {"requests": 1000}},
            {"name": "Enterprise", "slug": "enterprise", "price_monthly": 15000,
             "features": ["AI Chat (Unlimited)", "PDF Analysis", "PDF Generation",
                         "Telegram Bot", "WhatsApp Bot", "Dedicated Support",
                         "Document Storage", "Team Access", "Custom Integration"],
             "limits": {"requests": 10000}}
        ],
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
            "enabled": True,
            "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "bot_username": "Mypocket_lawyerbot",
            "last_offset": 0
        },
        "whatsapp": {
            "enabled": False,
            "phone_number_id": os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
            "access_token": os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
            "verify_token": "pocket_lawyer_2024"
        },
        "stripe": {
            "enabled": bool(os.getenv("STRIPE_API_KEY", "")),
            "api_key": os.getenv("STRIPE_API_KEY", ""),
            "webhook_secret": os.getenv("STRIPE_WEBHOOK_SECRET", "")
        },
        "legal_cases": [
            {"id": "tenancy", "title": "🏠 Tenancy & Landlord Disputes", 
             "description": "Resolve landlord-tenant disputes, rent issues, and eviction matters",
             "category": "Property", "icon": "🏠"},
            {"id": "employment", "title": "💼 Employment & Labour Rights",
             "description": "Know your rights as an employee or employer in Nigeria",
             "category": "Employment", "icon": "💼"},
            {"id": "contract", "title": "📝 Contract Disputes",
             "description": "Breach of contract, agreement drafting, and dispute resolution",
             "category": "Business", "icon": "📝"},
            {"id": "family", "title": "👨‍👩‍👧‍👦 Family & Marriage Law",
             "description": "Marriage, divorce, child custody, and family matters",
             "category": "Family", "icon": "👨‍👩‍👧‍👦"},
            {"id": "debt", "title": "💰 Debt Recovery & Banking",
             "description": "Debt collection, loan recovery, and banking disputes",
             "category": "Finance", "icon": "💰"},
            {"id": "criminal", "title": "⚖️ Criminal Defense",
             "description": "Criminal charges, defense strategies, and legal representation",
             "category": "Criminal", "icon": "⚖️"},
            {"id": "corporate", "title": "🏢 Corporate & Business Law",
             "description": "Company registration, compliance, and corporate governance",
             "category": "Business", "icon": "🏢"},
            {"id": "property", "title": "🏡 Property & Real Estate",
             "description": "Property transactions, disputes, and real estate law",
             "category": "Property", "icon": "🏡"},
            {"id": "divorce", "title": "💔 Divorce & Separation",
             "description": "Divorce proceedings, property division, and custody arrangements",
             "category": "Family", "icon": "💔"},
            {"id": "injury", "title": "🏥 Personal Injury Claims",
             "description": "Personal injury, medical malpractice, and compensation claims",
             "category": "Tort", "icon": "🏥"},
            {"id": "tax", "title": "💰 Tax Law & Compliance",
             "description": "Tax planning, compliance, and dispute resolution",
             "category": "Finance", "icon": "💰"},
            {"id": "immigration", "title": "🌍 Immigration & Visas",
             "description": "Visa applications, immigration processes, and citizenship",
             "category": "Immigration", "icon": "🌍"},
            {"id": "intellectual", "title": "💡 Intellectual Property",
             "description": "Trademarks, copyrights, patents, and IP protection",
             "category": "Business", "icon": "💡"},
            {"id": "consumer", "title": "🛒 Consumer Protection",
             "description": "Consumer rights, product liability, and fair trading",
             "category": "Consumer", "icon": "🛒"},
            {"id": "environmental", "title": "🌱 Environmental Law",
             "description": "Environmental compliance, pollution, and sustainability",
             "category": "Environmental", "icon": "🌱"},
            {"id": "labor", "title": "👷 Labor & Union Rights",
             "description": "Labor rights, union activities, and workplace disputes",
             "category": "Employment", "icon": "👷"}
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
    def get_legal_cases(cls):
        return cls._config.get("legal_cases", [])

    @classmethod
    def get_bank_details(cls):
        return cls._config.get("bank_details", {})

    @classmethod
    def get_stripe(cls):
        return cls._config.get("stripe", {})

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
    except:
        return None

def generate_api_key():
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

try:
    import fitz
    PDF_READER_AVAILABLE = True
except ImportError:
    PDF_READER_AVAILABLE = False

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
            return None, None
    except Exception as e:
        logger.error(f"Provider error: {e}")
        return None, None

async def get_ai_response(messages):
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
                return {"reply": reply, "provider": name}
        except Exception as e:
            logger.error(f"{name} error: {e}")
        await asyncio.sleep(0.05)
    return {"reply": "I'm having trouble connecting. Please try again later.", "provider": "offline"}

# ============================================================
# DOCUMENT GENERATION
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
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=72, rightMargin=72,
                                topMargin=72, bottomMargin=72, title=title, author="Pocket Lawyer")
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='CustomTitle', parent=styles['Heading1'], alignment=TA_CENTER,
            fontSize=20, textColor=colors.HexColor('#1a56db'), spaceAfter=30
        ))
        styles.add(ParagraphStyle(
            name='CustomBody', parent=styles['Normal'], fontSize=11,
            alignment=TA_JUSTIFY, spaceAfter=10, leading=16
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
            "This document is generated by Pocket Lawyer AI. Information is for general purposes only.",
            styles['CustomBody']
        ))

        doc.build(story)
        buffer.seek(0)
        
        documents[doc_id] = {
            "title": title,
            "content": content,
            "pdf": buffer,
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
@app.post("/api/auth/register")
async def register(user_data: UserCreate, db: SessionLocal = Depends(get_db)):
    try:
        existing = db.query(User).filter(
            (User.email == user_data.email) | (User.username == user_data.username)
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email or username already registered")

        user = User(
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            hashed_password=get_password_hash(user_data.password),
            api_key=generate_api_key(),
            phone_number=user_data.phone_number
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_access_token({"user_id": user.id, "username": user.username})

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")

@app.post("/api/auth/login")
async def login(login_data: UserLogin, db: SessionLocal = Depends(get_db)):
    try:
        user = db.query(User).filter(User.username == login_data.username).first()
        if not user:
            user = db.query(User).filter(User.email == login_data.username).first()

        if not user or not verify_password(login_data.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not user.is_active:
            raise HTTPException(status_code=401, detail="Account disabled")

        user.last_login = datetime.utcnow()
        db.commit()

        token = create_access_token({"user_id": user.id, "username": user.username})

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")

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
            # Return default cases from config
            default_cases = ConfigStore.get_legal_cases()
            return {
                "status": "success",
                "cases": [
                    {
                        "id": i + 1,
                        "title": c["title"],
                        "description": c.get("description", f"Legal assistance for {c['title']}"),
                        "category": c.get("category", "General"),
                        "icon": c.get("icon", "⚖️"),
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
        default_cases = ConfigStore.get_legal_cases()
        return {
            "status": "success",
            "cases": [
                {
                    "id": i + 1,
                    "title": c["title"],
                    "description": c.get("description", f"Legal assistance for {c['title']}"),
                    "category": c.get("category", "General"),
                    "icon": c.get("icon", "⚖️"),
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

        # Check if PDF generation requested
        pdf_keywords = ["generate pdf", "create pdf", "make pdf", "tenancy agreement", "nda"]
        if any(word in message.lower() for word in pdf_keywords):
            result = await generate_document_from_chat(message)
            if result.get("status") == "success":
                return {
                    "reply": f"✅ Document generated: {result.get('title')}",
                    "provider": "PDF Generator",
                    "pdf_url": result.get("pdf_url"),
                    "document_id": result.get("document_id"),
                    "is_pdf": True
                }

        # Get AI response
        result = await get_ai_response([{"role": "user", "content": message}])

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
# PAYMENT ENDPOINTS
# ============================================================
@app.get("/api/payments/plans")
async def get_plans():
    return {"status": "success", "plans": ConfigStore.get_plans()}

@app.post("/api/payments/create")
async def create_payment(
    request: PaymentRequest,
    current_user: User = Depends(get_current_user_required),
    db: SessionLocal = Depends(get_db)
):
    try:
        plan = None
        for p in ConfigStore.get_plans():
            if p["slug"] == request.plan:
                plan = p
                break
        
        if not plan:
            raise HTTPException(status_code=400, detail="Invalid plan")

        # Generate unique reference
        reference = f"PAY-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"

        payment = Payment(
            user_id=current_user.id,
            payment_id=reference,
            amount=plan["price_monthly"],
            currency="NGN",
            plan=request.plan,
            payment_method=request.payment_method,
            status="pending",
            reference=reference
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        # If Stripe is enabled and payment method is stripe
        stripe_config = ConfigStore.get_stripe()
        if stripe_config.get("enabled") and request.payment_method == "stripe":
            try:
                import stripe
                stripe.api_key = stripe_config.get("api_key")
                intent = stripe.PaymentIntent.create(
                    amount=int(plan["price_monthly"] * 100),
                    currency="NGN",
                    metadata={"reference": reference, "user_id": current_user.id},
                    payment_method_types=["card"]
                )
                return {
                    "status": "success",
                    "payment": {
                        "id": payment.id,
                        "reference": reference,
                        "amount": plan["price_monthly"],
                        "plan": request.plan,
                        "payment_method": request.payment_method,
                        "status": "pending",
                        "client_secret": intent.client_secret,
                        "stripe_payment_intent_id": intent.id
                    }
                }
            except Exception as e:
                logger.error(f"Stripe error: {e}")
                # Fall back to manual payment

        # Return payment details for manual/bank transfer
        bank_details = ConfigStore.get_bank_details()
        return {
            "status": "success",
            "payment": {
                "id": payment.id,
                "reference": reference,
                "amount": plan["price_monthly"],
                "plan": request.plan,
                "payment_method": request.payment_method,
                "status": "pending"
            },
            "bank_details": bank_details if request.payment_method in ["bank_transfer", "manual"] else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/payments/verify")
async def verify_payment(
    reference: str,
    current_user: User = Depends(get_current_user_required),
    db: SessionLocal = Depends(get_db)
):
    try:
        payment = db.query(Payment).filter(
            Payment.reference == reference,
            Payment.user_id == current_user.id
        ).first()

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        # For manual/bank transfer, status is updated manually by admin
        if payment.payment_method in ["bank_transfer", "manual"]:
            return {
                "status": "success",
                "payment": {
                    "id": payment.id,
                    "reference": payment.reference,
                    "amount": payment.amount,
                    "plan": payment.plan,
                    "status": payment.status
                }
            }

        # For Stripe, check with Stripe API
        stripe_config = ConfigStore.get_stripe()
        if stripe_config.get("enabled"):
            try:
                import stripe
                stripe.api_key = stripe_config.get("api_key")
                # Get payment intent by reference
                # This is simplified - in production, store the payment intent ID
                return {
                    "status": "success",
                    "payment": {
                        "id": payment.id,
                        "reference": payment.reference,
                        "amount": payment.amount,
                        "plan": payment.plan,
                        "status": payment.status
                    }
                }
            except Exception as e:
                logger.error(f"Stripe verification error: {e}")

        return {
            "status": "success",
            "payment": {
                "id": payment.id,
                "reference": payment.reference,
                "amount": payment.amount,
                "plan": payment.plan,
                "status": payment.status
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/payments/manual")
async def manual_payment(
    request: ManualPayment,
    current_user: User = Depends(get_current_user_required),
    db: SessionLocal = Depends(get_db)
):
    try:
        # Create manual payment record
        reference = f"MANUAL-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
        
        payment = Payment(
            user_id=current_user.id,
            payment_id=reference,
            amount=request.amount,
            currency="NGN",
            plan=request.plan,
            payment_method="manual",
            status="pending",
            reference=reference
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        bank_details = ConfigStore.get_bank_details()
        
        return {
            "status": "success",
            "message": "Manual payment initiated. Please transfer the amount to the bank details below.",
            "payment": {
                "id": payment.id,
                "reference": reference,
                "amount": request.amount,
                "plan": request.plan,
                "status": "pending"
            },
            "bank_details": bank_details
        }
    except Exception as e:
        logger.error(f"Manual payment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ADMIN PAYMENT MANAGEMENT
# ============================================================
@app.put("/api/admin/payments/{payment_id}")
async def update_payment_status(
    payment_id: int,
    status: str,
    current_user: User = Depends(get_current_admin_user),
    db: SessionLocal = Depends(get_db)
):
    try:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        payment.status = status
        if status == "completed":
            payment.payment_date = datetime.utcnow()
            # Update user subscription
            user = db.query(User).filter(User.id == payment.user_id).first()
            if user:
                user.subscription_tier = payment.plan
                user.subscription_expires = datetime.utcnow() + timedelta(days=30)
        
        payment.updated_at = datetime.utcnow()
        db.commit()

        return {"status": "success", "message": "Payment status updated"}
    except Exception as e:
        logger.error(f"Update payment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# TELEGRAM INTEGRATION
# ============================================================
telegram_running = False
telegram_thread = None
telegram_lock = threading.Lock()

def start_telegram_polling():
    global telegram_running, telegram_thread
    with telegram_lock:
        if telegram_running:
            return
        tg = ConfigStore.get_telegram()
        if not tg.get("bot_token"):
            logger.warning("Telegram bot token not configured")
            return
        if not tg.get("enabled"):
            logger.info("Telegram is disabled")
            return
        telegram_running = True
        telegram_thread = threading.Thread(target=run_telegram_polling, daemon=True)
        telegram_thread.start()
        logger.info("Telegram polling started")

def stop_telegram_polling():
    global telegram_running
    with telegram_lock:
        telegram_running = False
        logger.info("Telegram polling stopped")

def run_telegram_polling():
    global telegram_running
    logger.info("Telegram polling loop started")
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
                
            url = f"https://api.telegram.org/bot{tg['bot_token']}/getUpdates"
            
            try:
                response = httpx.get(url, params={"offset": offset, "timeout": 30}, timeout=45)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data.get("ok"):
                            for update in data.get("result", []):
                                offset = update.get("update_id", 0) + 1
                                ConfigStore.set("telegram", {**tg, "last_offset": offset})
                                
                                if "message" in update:
                                    msg = update["message"]
                                    chat_id = str(msg.get("chat", {}).get("id", ""))
                                    text = msg.get("text", "")
                                    
                                    if chat_id and text and not text.startswith("/"):
                                        # Process in background
                                        threading.Thread(
                                            target=process_telegram_message,
                                            args=(chat_id, text, brand)
                                        ).start()
                    except Exception as e:
                        logger.error(f"Telegram parse error: {e}")
                elif response.status_code == 409:
                    time.sleep(10)
            except Exception as e:
                logger.error(f"Telegram request error: {e}")
                time.sleep(5)
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            time.sleep(2)

def process_telegram_message(chat_id, text, brand):
    try:
        # Check if PDF generation requested
        pdf_keywords = ["generate pdf", "create pdf", "make pdf", "tenancy agreement", "nda"]
        if any(word in text.lower() for word in pdf_keywords):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(generate_document_from_chat(text))
            loop.close()
            if result.get("status") == "success":
                reply = f"📄 Document generated: {result.get('title')}\n\nDownload: https://pocket-lawyer-v15.onrender.com/api/documents/{result.get('document_id')}/download"
            else:
                reply = f"❌ Failed to generate PDF: {result.get('message', 'Unknown error')}"
        else:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(get_ai_response([{"role": "user", "content": text}]))
            loop.close()
            reply = result.get("reply", "I'm sorry, I couldn't process that.")
        
        full_reply = f"{reply}\n\n- {brand}"
        
        tg = ConfigStore.get_telegram()
        if tg.get("bot_token"):
            send_url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
            httpx.post(send_url, json={"chat_id": chat_id, "text": full_reply[:4000]}, timeout=10)
    except Exception as e:
        logger.error(f"Process telegram error: {e}")

@app.post("/api/telegram/test")
async def test_telegram(request: TelegramTestRequest):
    tg = ConfigStore.get_telegram()
    if not tg.get("bot_token"):
        return {"status": "error", "message": "Bot token not configured"}
    
    try:
        url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
        response = httpx.post(url, json={
            "chat_id": request.chat_id,
            "text": f"🤖 {ConfigStore.get('brand_name', 'Pocket Lawyer')} is online!\n\n{request.message}"
        }, timeout=10)
        
        if response.status_code == 200:
            return {"status": "success", "message": "Test message sent"}
        return {"status": "error", "message": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ============================================================
# WHATSAPP INTEGRATION
# ============================================================
@app.post("/api/whatsapp/test")
async def test_whatsapp(request: WhatsAppTestRequest):
    wa = ConfigStore.get_whatsapp()
    if not wa.get("access_token") or not wa.get("phone_number_id"):
        return {"status": "error", "message": "WhatsApp not configured"}
    
    try:
        url = f"https://graph.facebook.com/v18.0/{wa['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {wa['access_token']}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": request.to,
            "type": "text",
            "text": {"body": f"🤖 {ConfigStore.get('brand_name', 'Pocket Lawyer')} is online!\n\n{request.message}"}
        }
        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201, 202]:
            return {"status": "success", "message": "Test message sent"}
        return {"status": "error", "message": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    try:
        data = await request.json()
        wa = ConfigStore.get_whatsapp()
        if not wa.get("enabled"):
            return {"status": "disabled"}
        
        # Process WhatsApp messages
        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        
        if not messages:
            return {"status": "ignored"}
        
        msg = messages[0]
        from_number = msg.get("from")
        text = msg.get("text", {}).get("body")
        
        if from_number and text:
            # Process in background
            threading.Thread(
                target=process_whatsapp_message,
                args=(from_number, text)
            ).start()
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/webhook/whatsapp")
async def verify_whatsapp(
    hub_mode: Optional[str] = None,
    hub_token: Optional[str] = None,
    hub_challenge: Optional[str] = None
):
    wa = ConfigStore.get_whatsapp()
    if hub_mode == "subscribe" and hub_token == wa.get("verify_token"):
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")

def process_whatsapp_message(from_number, text):
    try:
        brand = ConfigStore.get("brand_name", "Pocket Lawyer")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(get_ai_response([{"role": "user", "content": text}]))
        loop.close()
        reply = result.get("reply", "I'm sorry, I couldn't process that.")
        full_reply = f"{reply}\n\n- {brand}"
        
        wa = ConfigStore.get_whatsapp()
        if wa.get("access_token") and wa.get("phone_number_id"):
            url = f"https://graph.facebook.com/v18.0/{wa['phone_number_id']}/messages"
            headers = {
                "Authorization": f"Bearer {wa['access_token']}",
                "Content-Type": "application/json"
            }
            payload = {
                "messaging_product": "whatsapp",
                "to": from_number,
                "type": "text",
                "text": {"body": full_reply[:4000]}
            }
            httpx.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        logger.error(f"Process WhatsApp error: {e}")

# ============================================================
# ADMIN DASHBOARD
# ============================================================
@app.get("/admin")
async def admin_dashboard(
    current_user: User = Depends(get_current_admin_user),
    db: SessionLocal = Depends(get_db)
):
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_chats = db.query(Chat).count()
    total_docs = db.query(Document).count()
    total_payments = db.query(Payment).count()
    pending_payments = db.query(Payment).filter(Payment.status == "pending").count()
    
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
            .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }}
            .btn-primary {{ background: #3b82f6; color: white; }}
            .btn-primary:hover {{ background: #2563eb; }}
            .btn-secondary {{ background: #334155; color: white; }}
            .btn-secondary:hover {{ background: #475569; }}
            .btn-success {{ background: #10b981; color: white; }}
            .btn-success:hover {{ background: #059669; }}
            .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }}
            .stat-card {{ background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; text-align: center; }}
            .stat-value {{ font-size: 2rem; font-weight: bold; color: #60a5fa; }}
            .stat-label {{ color: #94a3b8; font-size: 0.85rem; margin-top: 4px; }}
            .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
            .card {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; }}
            .card h3 {{ color: #f59e0b; margin-bottom: 12px; }}
            .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
            @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} .header {{ flex-direction: column; text-align: center; }} }}
        </style>
    </head>
    <body>
        <div class="header">
            <div><h1>⚖️ <span>Pocket</span> Lawyer Admin</h1></div>
            <div>
                <a href="/admin/payments" class="btn btn-success">💰 Payments</a>
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
                <div class="stat-card"><div class="stat-value">{pending_payments}</div><div class="stat-label">Pending Payments</div></div>
            </div>

            <div class="grid-2">
                <div class="card">
                    <h3>🔧 Admin Actions</h3>
                    <div class="actions">
                        <a href="/admin/users" class="btn btn-primary">👥 Users</a>
                        <a href="/admin/payments" class="btn btn-success">💰 Payments</a>
                        <a href="/admin/logs" class="btn btn-primary">📋 Logs</a>
                        <a href="/admin/telegram" class="btn btn-primary">🤖 Telegram</a>
                        <a href="/admin/whatsapp" class="btn btn-primary">💬 WhatsApp</a>
                        <a href="/admin/settings" class="btn btn-primary">⚙️ Settings</a>
                    </div>
                </div>
                <div class="card">
                    <h3>ℹ️ System Info</h3>
                    <p>📊 Status: <span style="color:#10b981;">● Online</span></p>
                    <p>📄 PDF Generation: <span style="color:{"#10b981" if PDF_AVAILABLE else "#ef4444"};">{"✅" if PDF_AVAILABLE else "❌"}</span></p>
                    <p>📑 PDF Reader: <span style="color:{"#10b981" if PDF_READER_AVAILABLE else "#ef4444"};">{"✅" if PDF_READER_AVAILABLE else "❌"}</span></p>
                    <p>🤖 AI Providers: <span style="color:#60a5fa;">{len([p for p in ConfigStore.get_ai_providers() if p.get("enabled")])}/{len(ConfigStore.get_ai_providers())} Active</span></p>
                    <p>📱 Telegram: <span style="color:{"#10b981" if ConfigStore.get_telegram().get("enabled") else "#ef4444"};">{"✅" if ConfigStore.get_telegram().get("enabled") else "❌"}</span></p>
                    <p>💬 WhatsApp: <span style="color:{"#10b981" if ConfigStore.get_whatsapp().get("enabled") else "#ef4444"};">{"✅" if ConfigStore.get_whatsapp().get("enabled") else "❌"}</span></p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

# ============================================================
# ADMIN PAYMENT MANAGEMENT PAGE
# ============================================================
@app.get("/admin/payments")
async def admin_payments(
    current_user: User = Depends(get_current_admin_user),
    db: SessionLocal = Depends(get_db)
):
    payments = db.query(Payment).order_by(Payment.created_at.desc()).all()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Payment Management - Pocket Lawyer</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
            .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
            .header h1 {{ color: #60a5fa; }}
            .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }}
            .btn-primary {{ background: #3b82f6; color: white; }}
            .btn-secondary {{ background: #334155; color: white; }}
            .btn-success {{ background: #10b981; color: white; }}
            .btn-danger {{ background: #ef4444; color: white; }}
            .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #334155; }}
            th {{ color: #94a3b8; font-weight: 600; }}
            .badge {{ padding: 4px 12px; border-radius: 12px; font-size: 0.75rem; display: inline-block; }}
            .badge-pending {{ background: #f59e0b20; color: #f59e0b; border: 1px solid #f59e0b40; }}
            .badge-completed {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
            .badge-failed {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
            .badge-cancelled {{ background: #64748b20; color: #94a3b8; border: 1px solid #64748b40; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div><h1>💰 Payment Management</h1></div>
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
                        <th>User</th>
                        <th>Plan</th>
                        <th>Amount</th>
                        <th>Method</th>
                        <th>Reference</th>
                        <th>Status</th>
                        <th>Date</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for p in payments:
        user = db.query(User).filter(User.id == p.user_id).first()
        username = user.username if user else "Unknown"
        status_class = f"badge-{p.status}"
        
        html += f"""
        <tr>
            <td>{p.id}</td>
            <td>{username}</td>
            <td>{p.plan}</td>
            <td>₦{p.amount:,.0f}</td>
            <td>{p.payment_method}</td>
            <td><code style="background:#0f172a;padding:2px 6px;border-radius:4px;font-size:0.8rem;">{p.reference}</code></td>
            <td><span class="badge {status_class}">{p.status.upper()}</span></td>
            <td>{p.created_at.strftime('%Y-%m-%d') if p.created_at else '-'}</td>
            <td>
                <form method="POST" action="/admin/payments/{p.id}/update" style="display:inline;">
                    <input type="hidden" name="status" value="completed">
                    <button type="submit" class="btn btn-success" style="padding:4px 12px;font-size:0.8rem;">✓ Complete</button>
                </form>
                <form method="POST" action="/admin/payments/{p.id}/update" style="display:inline;">
                    <input type="hidden" name="status" value="failed">
                    <button type="submit" class="btn btn-danger" style="padding:4px 12px;font-size:0.8rem;">✗ Fail</button>
                </form>
            </td>
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
# ADMIN TELEGRAM MANAGEMENT
# ============================================================
@app.get("/admin/telegram")
async def admin_telegram(
    current_user: User = Depends(get_current_admin_user)
):
    tg = ConfigStore.get_telegram()
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Telegram Management - Pocket Lawyer</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
            .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
            .header h1 {{ color: #60a5fa; }}
            .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }}
            .btn-primary {{ background: #3b82f6; color: white; }}
            .btn-secondary {{ background: #334155; color: white; }}
            .btn-success {{ background: #10b981; color: white; }}
            .btn-danger {{ background: #ef4444; color: white; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 24px; }}
            .card {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px; }}
            .card h3 {{ color: #f59e0b; margin-bottom: 12px; }}
            .form-group {{ margin-bottom: 12px; }}
            .form-group label {{ color: #94a3b8; display: block; margin-bottom: 4px; }}
            .form-group input {{ width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; }}
            .status-badge {{ padding: 4px 12px; border-radius: 12px; display: inline-block; }}
            .status-on {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
            .status-off {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div><h1>🤖 Telegram Management</h1></div>
            <div>
                <a href="/admin" class="btn btn-secondary">← Back</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
            </div>
        </div>
        <div class="container">
            <div class="card">
                <h3>📊 Status</h3>
                <p>Bot: <span class="status-badge {"status-on" if tg.get("enabled") else "status-off"}">{"🟢 Online" if tg.get("enabled") else "🔴 Offline"}</span></p>
                <p>Username: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">@{tg.get("bot_username", "Not set")}</code></p>
                <p>Token: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">{"Configured" if tg.get("bot_token") else "Not configured"}</code></p>
            </div>
            
            <div class="card">
                <h3>🔧 Configuration</h3>
                <form method="POST" action="/admin/telegram/update">
                    <div class="form-group">
                        <label>Bot Token</label>
                        <input type="text" name="bot_token" value="{tg.get("bot_token", "")}" placeholder="Enter your bot token">
                    </div>
                    <div class="form-group">
                        <label>Bot Username</label>
                        <input type="text" name="bot_username" value="{tg.get("bot_username", "")}" placeholder="e.g., MyBot">
                    </div>
                    <div class="form-group">
                        <label>Enabled</label>
                        <select name="enabled" style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0;">
                            <option value="true" {"selected" if tg.get("enabled") else ""}>Yes</option>
                            <option value="false" {"selected" if not tg.get("enabled") else ""}>No</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">💾 Save</button>
                </form>
            </div>
            
            <div class="card">
                <h3>🧪 Test Bot</h3>
                <form method="POST" action="/admin/telegram/test">
                    <div class="form-group">
                        <label>Chat ID</label>
                        <input type="text" name="chat_id" placeholder="Enter your Telegram chat ID" required>
                    </div>
                    <div class="form-group">
                        <label>Message</label>
                        <input type="text" name="message" value="Hello from Pocket Lawyer! 🚀" placeholder="Test message">
                    </div>
                    <button type="submit" class="btn btn-success">📤 Send Test</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """)

# ============================================================
# ADMIN WHATSAPP MANAGEMENT
# ============================================================
@app.get("/admin/whatsapp")
async def admin_whatsapp(
    current_user: User = Depends(get_current_admin_user)
):
    wa = ConfigStore.get_whatsapp()
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>WhatsApp Management - Pocket Lawyer</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
            .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
            .header h1 {{ color: #60a5fa; }}
            .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }}
            .btn-primary {{ background: #3b82f6; color: white; }}
            .btn-secondary {{ background: #334155; color: white; }}
            .btn-success {{ background: #10b981; color: white; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 24px; }}
            .card {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px; }}
            .card h3 {{ color: #f59e0b; margin-bottom: 12px; }}
            .form-group {{ margin-bottom: 12px; }}
            .form-group label {{ color: #94a3b8; display: block; margin-bottom: 4px; }}
            .form-group input {{ width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; }}
            .status-badge {{ padding: 4px 12px; border-radius: 12px; display: inline-block; }}
            .status-on {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
            .status-off {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div><h1>💬 WhatsApp Management</h1></div>
            <div>
                <a href="/admin" class="btn btn-secondary">← Back</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
            </div>
        </div>
        <div class="container">
            <div class="card">
                <h3>📊 Status</h3>
                <p>Status: <span class="status-badge {"status-on" if wa.get("enabled") else "status-off"}">{"🟢 Online" if wa.get("enabled") else "🔴 Offline"}</span></p>
                <p>Phone Number ID: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">{"Configured" if wa.get("phone_number_id") else "Not configured"}</code></p>
                <p>Access Token: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">{"Configured" if wa.get("access_token") else "Not configured"}</code></p>
            </div>
            
            <div class="card">
                <h3>🔧 Configuration</h3>
                <form method="POST" action="/admin/whatsapp/update">
                    <div class="form-group">
                        <label>Phone Number ID</label>
                        <input type="text" name="phone_number_id" value="{wa.get("phone_number_id", "")}" placeholder="Enter phone number ID">
                    </div>
                    <div class="form-group">
                        <label>Access Token</label>
                        <input type="text" name="access_token" value="{wa.get("access_token", "")}" placeholder="Enter access token">
                    </div>
                    <div class="form-group">
                        <label>Verify Token</label>
                        <input type="text" name="verify_token" value="{wa.get("verify_token", "pocket_lawyer_2024")}" placeholder="Enter verify token">
                    </div>
                    <div class="form-group">
                        <label>Enabled</label>
                        <select name="enabled" style="width:100%;padding:10px 12px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0;">
                            <option value="true" {"selected" if wa.get("enabled") else ""}>Yes</option>
                            <option value="false" {"selected" if not wa.get("enabled") else ""}>No</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">💾 Save</button>
                </form>
            </div>
            
            <div class="card">
                <h3>🧪 Test WhatsApp</h3>
                <form method="POST" action="/admin/whatsapp/test">
                    <div class="form-group">
                        <label>Phone Number (with country code)</label>
                        <input type="text" name="to" placeholder="e.g., 2348012345678" required>
                    </div>
                    <div class="form-group">
                        <label>Message</label>
                        <input type="text" name="message" value="Hello from Pocket Lawyer! 🚀" placeholder="Test message">
                    </div>
                    <button type="submit" class="btn btn-success">📤 Send Test</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """)

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
                <p style="margin-top:8px;color:#94a3b8;font-size:0.9rem;">SMTP_HOST: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">{{ os.getenv('SMTP_HOST', 'Not set') }}</code></p>
            </div>

            <div class="card">
                <h3>💳 Payment Settings</h3>
                <p>Configure payment methods and bank details.</p>
                <p style="margin-top:8px;color:#94a3b8;font-size:0.9rem;">Stripe: {{ '✅ Enabled' if ConfigStore.get_stripe().get('enabled') else '❌ Disabled' }}</p>
                <p style="color:#94a3b8;font-size:0.9rem;">Bank Transfer: Available</p>
                <p style="color:#94a3b8;font-size:0.9rem;">Manual Payment: Available</p>
            </div>

            <div class="card">
                <h3>🤖 AI Providers</h3>
                <p>Configure AI providers in the environment variables.</p>
                <p style="margin-top:8px;color:#94a3b8;font-size:0.9rem;">Available: Groq, SambaNova, Mistral, OpenRouter</p>
            </div>
        </div>
    </body>
    </html>
    """)

# ============================================================
# ADMIN LOGS
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
            .log-line {{ padding: 4px 0; border-bottom: 1px solid #1e293b; color: #94a3b8; }}
            .log-error {{ color: #ef4444; }}
            .log-warning {{ color: #f59e0b; }}
            .log-info {{ color: #60a5fa; }}
            .log-success {{ color: #10b981; }}
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
        elif "✅" in line or "SUCCESS" in line:
            cls = "log-success"
        else:
            cls = "log-info"
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
            th {{ color: #94a3b8; font-weight: 600; }}
            .badge {{ padding: 4px 12px; border-radius: 12px; font-size: 0.75rem; display: inline-block; }}
            .badge-admin {{ background: #f59e0b20; color: #f59e0b; border: 1px solid #f59e0b40; }}
            .badge-user {{ background: #3b82f620; color: #60a5fa; border: 1px solid #3b82f640; }}
            .badge-active {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
            .badge-inactive {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
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
                        <th>Phone</th>
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
        
        html += f"""
        <tr>
            <td>{user.id}</td>
            <td><strong>{user.username}</strong></td>
            <td>{user.email}</td>
            <td>{user.full_name or '-'}</td>
            <td><span class="badge {badge_role}">{role}</span></td>
            <td><span class="badge {badge_status}">{status}</span></td>
            <td>{user.subscription_tier.capitalize()}</td>
            <td>{user.phone_number or '-'}</td>
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
# HOME PAGE - WELCOME WITH LEGAL CASES
# ============================================================
@app.get("/")
async def home():
    brand = ConfigStore.get("brand_name", "Pocket Lawyer")
    legal_cases = ConfigStore.get_legal_cases()
    
    # Build cases HTML
    cases_html = ""
    for case in legal_cases[:12]:  # Show 12 cases
        cases_html += f'''
        <div class="case-card" onclick="window.location.href='/chat?q={case["title"]}'">
            <span class="case-icon">{case["icon"]}</span>
            <span class="case-title">{case["title"]}</span>
        </div>
        '''
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{brand} - Legal AI Assistant</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
            .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
            .header h1 {{ color: #60a5fa; font-size: 1.5rem; }}
            .header h1 span {{ color: #f59e0b; }}
            .btn {{ padding: 10px 24px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; transition: all 0.3s; }}
            .btn-primary {{ background: #3b82f6; color: white; }}
            .btn-primary:hover {{ background: #2563eb; transform: translateY(-2px); }}
            .btn-outline {{ background: transparent; color: #94a3b8; border: 1px solid #334155; }}
            .btn-outline:hover {{ background: #1e293b; transform: translateY(-2px); }}
            .btn-success {{ background: #10b981; color: white; }}
            .btn-success:hover {{ background: #059669; transform: translateY(-2px); }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
            .hero {{ text-align: center; padding: 60px 20px; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 16px; border: 1px solid #334155; margin-bottom: 32px; }}
            .hero h1 {{ font-size: 3rem; color: #60a5fa; }}
            .hero h1 .highlight {{ color: #f59e0b; }}
            .hero p {{ font-size: 1.2rem; color: #94a3b8; margin: 16px 0; max-width: 600px; margin-left: auto; margin-right: auto; }}
            .hero .subtitle {{ font-size: 1rem; color: #64748b; }}
            .btn-group {{ display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 24px; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 16px; max-width: 700px; margin: -20px auto 24px; }}
            .stat-card {{ background: #1e293b; padding: 16px; border-radius: 12px; border: 1px solid #334155; text-align: center; }}
            .stat-value {{ font-size: 1.5rem; font-weight: bold; color: #60a5fa; }}
            .stat-label {{ color: #94a3b8; font-size: 0.8rem; }}
            .cases-section {{ padding: 40px 20px; max-width: 1200px; margin: 0 auto; }}
            .cases-section h2 {{ text-align: center; margin-bottom: 24px; color: #f59e0b; font-size: 1.8rem; }}
            .cases-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }}
            .case-card {{ background: #1e293b; padding: 16px 20px; border-radius: 10px; border: 1px solid #334155; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: all 0.3s; }}
            .case-card:hover {{ border-color: #60a5fa; transform: translateX(4px); background: #253450; box-shadow: 0 4px 12px rgba(59,130,246,0.2); }}
            .case-icon {{ font-size: 1.5rem; flex-shrink: 0; }}
            .case-title {{ color: #e2e8f0; font-size: 0.9rem; }}
            .features {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 32px 0; }}
            .feature {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; text-align: center; }}
            .feature .icon {{ font-size: 2.5rem; }}
            .feature h3 {{ color: #60a5fa; margin: 8px 0; }}
            .feature p {{ color: #94a3b8; font-size: 0.9rem; }}
            .footer {{ text-align: center; color: #64748b; font-size: 0.8rem; padding: 24px; border-top: 1px solid #1e293b; margin-top: 40px; }}
            @media (max-width: 768px) {{ .header {{ flex-direction: column; text-align: center; padding: 16px; }} .hero h1 {{ font-size: 2rem; }} .cases-grid {{ grid-template-columns: 1fr; }} }}
        </style>
    </head>
    <body>
        <div class="header">
            <div><h1>⚖️ <span>Pocket</span> Lawyer</h1></div>
            <div>
                <a href="/auth/login" class="btn btn-outline">Login</a>
                <a href="/auth/register" class="btn btn-primary">Get Started</a>
            </div>
        </div>
        
        <div class="container">
            <div class="hero">
                <h1>Your <span class="highlight">Trusted</span> Legal AI Assistant</h1>
                <p>🇳🇬 Nigerian Law, Powered by Advanced AI</p>
                <div class="subtitle">Get instant legal guidance, generate professional documents, and analyze contracts — all in one place.</div>
                <div class="btn-group">
                    <a href="/auth/register" class="btn btn-primary">🚀 Start Now — It's Free</a>
                    <a href="/chat" class="btn btn-success">💬 Try AI Chat</a>
                </div>
            </div>
            
            <div class="stats">
                <div class="stat-card"><div class="stat-value">16+</div><div class="stat-label">Legal Areas</div></div>
                <div class="stat-card"><div class="stat-value">4</div><div class="stat-label">AI Providers</div></div>
                <div class="stat-card"><div class="stat-value">📄</div><div class="stat-label">PDF Generation</div></div>
                <div class="stat-card"><div class="stat-value">🤖</div><div class="stat-label">Telegram Bot</div></div>
            </div>
            
            <div class="features">
                <div class="feature">
                    <span class="icon">📄</span>
                    <h3>Generate PDF Documents</h3>
                    <p>Create professional legal documents, contracts, and agreements instantly with AI.</p>
                </div>
                <div class="feature">
                    <span class="icon">🔍</span>
                    <h3>Analyze Legal Documents</h3>
                    <p>Upload PDFs and get AI-powered analysis, risk assessment, and recommendations.</p>
                </div>
                <div class="feature">
                    <span class="icon">💬</span>
                    <h3>AI Legal Chat</h3>
                    <p>Chat with our AI about any legal matter. Get answers in seconds, 24/7.</p>
                </div>
                <div class="feature">
                    <span class="icon">📱</span>
                    <h3>Telegram & WhatsApp</h3>
                    <p>Access Pocket Lawyer from your favorite messaging apps. Always available.</p>
                </div>
            </div>
            
            <div class="cases-section">
                <h2>📌 Choose Your Legal Matter</h2>
                <p style="text-align:center;color:#94a3b8;margin-bottom:20px;">Click any case to start a conversation with our AI</p>
                <div class="cases-grid">
                    {cases_html}
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>⚖️ {brand} v{VERSION} • General guidance only</p>
            <p style="margin-top:4px;">For specific legal advice, please consult a qualified lawyer</p>
        </div>
        
        <script>
            // Quick action for case cards
            document.querySelectorAll('.case-card').forEach(card => {{
                card.addEventListener('click', function() {{
                    const title = this.querySelector('.case-title').textContent;
                    window.location.href = `/chat?q=${{encodeURIComponent(title)}}`;
                }});
            }});
        </script>
    </body>
    </html>
    """)

# ============================================================
# CHAT UI
# ============================================================
@app.get("/chat")
async def chat_ui():
    brand = ConfigStore.get("brand_name", "Pocket Lawyer")
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>{brand} - AI Chat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; overflow: hidden; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 24px; background: #1e293b; border-bottom: 1px solid #334155; }}
        .header h2 {{ color: #60a5fa; }}
        .btn {{ background: #1e293b; color: #e2e8f0; padding: 6px 16px; border-radius: 8px; text-decoration: none; border: 1px solid #334155; cursor: pointer; }}
        .btn:hover {{ background: #334155; }}
        .chat-container {{ max-width: 900px; margin: 0 auto; padding: 20px; height: calc(100vh - 80px); display: flex; flex-direction: column; }}
        .chat-box {{ flex:1; overflow-y:auto; padding:20px; background:#0f172a; border:1px solid #1e293b; border-radius:12px; margin-bottom:16px; }}
        .message {{ padding: 12px 18px; margin: 8px 0; border-radius: 12px; max-width: 85%; word-wrap: break-word; line-height: 1.6; }}
        .user {{ background: #3b82f6; margin-left: auto; }}
        .ai {{ background: #1e293b; border: 1px solid #334155; }}
        .ai .pdf-link {{ display: inline-block; background: #10b981; color: white; padding: 8px 16px; border-radius: 8px; text-decoration: none; margin-top: 8px; }}
        .input-area {{ display: flex; gap: 12px; padding: 16px 0; }}
        .input-area input {{ flex:1; padding:12px 18px; border-radius:12px; border:1px solid #334155; background:#1e293b; color:#e2e8f0; font-size:1rem; outline:none; }}
        .input-area input:focus {{ border-color:#3b82f6; }}
        .input-area button {{ padding:12px 28px; border-radius:12px; border:none; background:#3b82f6; color:white; font-weight:600; cursor:pointer; }}
        .input-area button:hover {{ background:#2563eb; }}
        .disclaimer {{ font-size:0.7rem; color:#64748b; text-align:center; padding:8px; }}
        .typing {{ color: #94a3b8; font-style: italic; padding: 8px 16px; }}
        .user-info {{ display: flex; align-items: center; gap: 12px; }}
        .user-info span {{ color: #94a3b8; font-size: 0.9rem; }}
    </style>
    </head>
    <body>
    <div class="header">
        <h2>⚖️ {brand}</h2>
        <div class="user-info">
            <span id="userDisplay">👤 Loading...</span>
            <button class="btn" onclick="logout()">Logout</button>
            <a href="/" class="btn">Home</a>
        </div>
    </div>
    <div class="chat-container">
    <div id="chatBox" class="chat-box">
    <div class="message ai"><strong>{brand}</strong><br>Hello! Welcome to Pocket Lawyer! 👋<br>I am your AI legal assistant for Nigerian Law.<br><br>You can:<br>• Ask legal questions<br>• Generate PDF documents (try "Generate a tenancy agreement PDF")<br>• Upload and analyze contracts<br>• Get legal guidance 24/7<br><br>How can I help you today?</div>
    </div>
    <div class="input-area">
    <input type="text" id="userInput" placeholder="Type your legal question..." onkeypress="if(event.key===13) sendMessage()">
    <button onclick="sendMessage()" id="sendBtn">Send</button>
    </div>
    <div class="disclaimer">General guidance only. Consult a lawyer for legal advice.</div>
    </div>
    <script>
    const token = localStorage.getItem('token');
    if (!token) {{
        window.location.href = '/auth/login';
    }}
    try {{
        const user = JSON.parse(localStorage.getItem('user') || '{{"username":"User"}}');
        document.getElementById('userDisplay').textContent = '👤 ' + user.username;
    }} catch(e) {{
        document.getElementById('userDisplay').textContent = '👤 User';
    }}
    const chatBox = document.getElementById('chatBox');
    function addMessage(sender, text, isHTML = false) {{
        const div = document.createElement('div');
        div.className = 'message ' + sender;
        if (isHTML) {{ div.innerHTML = text; }} else {{ div.textContent = text; }}
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
    }}
    function addTyping() {{
        const div = document.createElement('div');
        div.className = 'typing';
        div.id = 'typing';
        div.textContent = 'Thinking...';
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
    }}
    function removeTyping() {{
        const typing = document.getElementById('typing');
        if (typing) typing.remove();
    }}
    async function sendMessage() {{
        const input = document.getElementById('userInput');
        const message = input.value.trim();
        if (!message) return;
        input.value = '';
        addMessage('user', message);
        addTyping();
        const sendBtn = document.getElementById('sendBtn');
        sendBtn.disabled = true;
        try {{
            const res = await fetch('/api/chat', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + localStorage.getItem('token')
                }},
                body: JSON.stringify({{message: message}})
            }});
            const data = await res.json();
            removeTyping();
            if (data.pdf_url) {{
                const pdfLink = `<a href="${{data.pdf_url}}" target="_blank" class="pdf-link">📄 Download PDF</a>`;
                addMessage('ai', data.reply + '<br>' + pdfLink, true);
            }} else {{
                addMessage('ai', data.reply || 'No response received');
            }}
        }} catch(e) {{
            removeTyping();
            addMessage('ai', 'Error connecting to server. Please try again.');
        }}
        sendBtn.disabled = false;
    }}
    function logout() {{
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/auth/login';
    }}
    const params = new URLSearchParams(window.location.search);
    const q = params.get('q');
    if (q) {{
        document.getElementById('userInput').value = q;
        sendMessage();
    }}
    </script>
    </body>
    </html>
    """)

# ============================================================
# AUTH PAGES
# ============================================================
@app.get("/auth/login")
async def login_page():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Login - Pocket Lawyer</title>
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
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .links { text-align: center; margin-top: 16px; color: #94a3b8; }
        .links a { color: #60a5fa; text-decoration: none; }
        .links a:hover { text-decoration: underline; }
        .error { background: #ef444420; color: #ef4444; padding: 12px; border-radius: 8px; margin-bottom: 16px; display: none; border: 1px solid #ef444440; }
        .success { background: #10b98120; color: #10b981; padding: 12px; border-radius: 8px; margin-bottom: 16px; display: none; border: 1px solid #10b98140; }
    </style>
    </head>
    <body>
    <div class="login-container">
        <h2>⚖️ Welcome Back</h2>
        <p class="subtitle">Login to your Pocket Lawyer account</p>
        <div class="error" id="errorMsg"></div>
        <div class="success" id="successMsg"></div>
        <form id="loginForm">
            <div class="form-group">
                <label>Username or Email</label>
                <input type="text" id="username" required placeholder="Enter your username or email">
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" id="password" required placeholder="Enter your password">
            </div>
            <button type="submit" class="btn" id="loginBtn">Sign In</button>
        </form>
        <div class="links">
            <p>Don't have an account? <a href="/auth/register">Register</a></p>
            <p style="margin-top:8px;font-size:0.8rem;color:#64748b;">Demo: admin / admin123</p>
        </div>
    </div>
    <script>
    document.getElementById('loginForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn = document.getElementById('loginBtn');
        const errorMsg = document.getElementById('errorMsg');
        const successMsg = document.getElementById('successMsg');
        btn.disabled = true;
        btn.textContent = 'Logging in...';
        errorMsg.style.display = 'none';
        successMsg.style.display = 'none';
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
                successMsg.textContent = '✅ Login successful! Redirecting...';
                successMsg.style.display = 'block';
                setTimeout(() => window.location.href = '/chat', 1000);
            } else {
                errorMsg.textContent = '❌ ' + (data.detail || 'Invalid credentials');
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
    <head><title>Register - Pocket Lawyer</title>
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
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .links { text-align: center; margin-top: 16px; color: #94a3b8; }
        .links a { color: #60a5fa; text-decoration: none; }
        .links a:hover { text-decoration: underline; }
        .error { background: #ef444420; color: #ef4444; padding: 12px; border-radius: 8px; margin-bottom: 16px; display: none; border: 1px solid #ef444440; }
        .success { background: #10b98120; color: #10b981; padding: 12px; border-radius: 8px; margin-bottom: 16px; display: none; border: 1px solid #10b98140; }
    </style>
    </head>
    <body>
    <div class="register-container">
        <h2>🚀 Create Account</h2>
        <p class="subtitle">Start using Pocket Lawyer today</p>
        <div class="error" id="errorMsg"></div>
        <div class="success" id="successMsg"></div>
        <form id="registerForm">
            <div class="form-group">
                <label>Full Name</label>
                <input type="text" id="full_name" required placeholder="Enter your full name">
            </div>
            <div class="form-group">
                <label>Username</label>
                <input type="text" id="username" required placeholder="Choose a username">
            </div>
            <div class="form-group">
                <label>Email</label>
                <input type="email" id="email" required placeholder="Enter your email">
            </div>
            <div class="form-group">
                <label>Phone Number (Optional)</label>
                <input type="tel" id="phone" placeholder="e.g., 2348012345678">
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" id="password" required placeholder="Min 6 characters" minlength="6">
            </div>
            <button type="submit" class="btn" id="registerBtn">Create Account</button>
        </form>
        <div class="links">
            <p>Already have an account? <a href="/auth/login">Login</a></p>
        </div>
    </div>
    <script>
    document.getElementById('registerForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn = document.getElementById('registerBtn');
        const errorMsg = document.getElementById('errorMsg');
        const successMsg = document.getElementById('successMsg');
        btn.disabled = true;
        btn.textContent = 'Creating account...';
        errorMsg.style.display = 'none';
        successMsg.style.display = 'none';
        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    full_name: document.getElementById('full_name').value.trim(),
                    username: document.getElementById('username').value.trim(),
                    email: document.getElementById('email').value.trim(),
                    phone_number: document.getElementById('phone').value.trim(),
                    password: document.getElementById('password').value
                })
            });
            const data = await response.json();
            if (response.ok) {
                localStorage.setItem('token', data.access_token);
                localStorage.setItem('user', JSON.stringify(data.user));
                successMsg.textContent = '✅ Account created! Redirecting...';
                successMsg.style.display = 'block';
                setTimeout(() => window.location.href = '/chat', 1000);
            } else {
                errorMsg.textContent = '❌ ' + (data.detail || 'Registration failed');
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

# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "version": VERSION,
        "timestamp": datetime.utcnow().isoformat(),
        "pdf_available": PDF_AVAILABLE,
        "pdf_reader": PDF_READER_AVAILABLE,
        "telegram_enabled": ConfigStore.get_telegram().get("enabled", False),
        "whatsapp_enabled": ConfigStore.get_whatsapp().get("enabled", False)
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
    
    db = SessionLocal()
    try:
        # Create admin user
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                email="admin@pocketlawyer.ai",
                username="admin",
                full_name="System Administrator",
                hashed_password=get_password_hash("admin123"),
                is_superuser=True,
                is_active=True,
                api_key=generate_api_key()
            )
            db.add(admin)
            db.commit()
            logger.info("✅ Admin user created (username: admin, password: admin123)")
        
        # Seed legal cases
        cases = db.query(LegalCase).count()
        if cases == 0:
            for i, case_data in enumerate(ConfigStore.get_legal_cases()):
                case = LegalCase(
                    case_type=case_data["id"],
                    title=case_data["title"],
                    description=case_data.get("description", ""),
                    category=case_data.get("category", "General"),
                    icon=case_data.get("icon", "⚖️"),
                    slug=case_data["id"],
                    order=i
                )
                db.add(case)
            db.commit()
            logger.info(f"✅ Seeded {len(ConfigStore.get_legal_cases())} legal cases")
        
        # Start Telegram polling
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

