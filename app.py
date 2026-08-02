# ============================================================
# POCKET LAWYER v15.0 - ENTERPRISE EDITION
# ============================================================
import os
import json
import logging
import asyncio
import threading
import httpx
def validate_telegram_token(bot_token):
    """Validate Telegram bot token before starting polling"""
    if not bot_token:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        response = httpx.get(url, timeout=10)
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get("ok"):
                    logger.info(f"✅ Telegram bot validated: @{data.get('result', {}).get('username', 'unknown')}")
                    return True
            except:
                pass
        logger.error(f"❌ Telegram token validation failed: {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"❌ Telegram validation error: {e}")
        return False
import time
import re
import io
import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request, File, UploadFile, WebSocket, WebSocketDisconnect, Depends, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
import httpx
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext
import stripe
from cryptography.fernet import Fernet
from typing import List, Optional
import websockets
from datetime import datetime
import asyncio
from contextlib import asynccontextmanager
import analytics
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import hashlib
from itsdangerous import URLSafeTimedSerializer
from email.mime.text import MIMEText
import smtplib
import ssl

# ============================================================
# LOGGING
# ============================================================
os.makedirs('logs', exist_ok=True)
os.makedirs('data', exist_ok=True)
os.makedirs('documents', exist_ok=True)
os.makedirs('uploads', exist_ok=True)
os.makedirs('database', exist_ok=True)
os.makedirs('certs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/pocket_lawyer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("pocket_lawyer")

VERSION = "15.0.0"
APP_NAME = "Pocket Lawyer"

# ============================================================
# SECURITY & ENCRYPTION
# ============================================================
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(64))
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key())
cipher_suite = Fernet(ENCRYPTION_KEY)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
serializer = URLSafeTimedSerializer(SECRET_KEY)

# ============================================================
# DATABASE SETUP
# ============================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./database/pocket_lawyer.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String(255))
    
    documents = relationship("Document", back_populates="user")
    chats = relationship("Chat", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
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
    shared_with = Column(JSON, default=[])
    
    user = relationship("User", back_populates="documents")
    versions = relationship("DocumentVersion", back_populates="document")

class DocumentVersion(Base):
    __tablename__ = "document_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    version_number = Column(Integer)
    content_hash = Column(String(255))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    document = relationship("Document", back_populates="versions")

class Chat(Base):
    __tablename__ = "chats"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(String(100))
    message = Column(Text)
    response = Column(Text)
    provider = Column(String(50))
    tokens_used = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="chats")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
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
    user_id = Column(Integer, ForeignKey("users.id"))
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
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

# ============================================================
# ANALYTICS
# ============================================================
analytics.write_key = os.getenv("ANALYTICS_KEY", "local")
analytics.debug = True

# Prometheus metrics
REQUESTS = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUESTS_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency', ['method', 'endpoint'])
ACTIVE_USERS = Gauge('active_users', 'Number of active users')
PDF_GENERATED = Counter('pdf_generated_total', 'Total PDFs generated')
PDF_ANALYZED = Counter('pdf_analyzed_total', 'Total PDFs analyzed')
CHAT_MESSAGES = Counter('chat_messages_total', 'Total chat messages')
API_CALLS = Counter('api_calls_total', 'Total API calls')

# ============================================================
# STRIPE PAYMENTS
# ============================================================
stripe.api_key = os.getenv("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

PLANS = {
    "free": {"price": 0, "features": ["AI Chat", "PDF Analysis", "3 Documents"], "requests": 50},
    "pro": {"price": 5000, "features": ["AI Chat", "PDF Analysis", "PDF Generation", "Telegram", "50 Documents", "Digital Signatures"], "requests": 1000},
    "business": {"price": 15000, "features": ["AI Chat", "PDF Analysis", "PDF Generation", "Telegram", "WhatsApp", "Unlimited Documents", "Digital Signatures", "Team Access"], "requests": 10000},
    "enterprise": {"price": 50000, "features": ["All Features", "Unlimited Everything", "24/7 Support", "Custom Integration", "Dedicated Support"], "requests": 100000}
}

# ============================================================
# WEBSOCKET MANAGER
# ============================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[websockets.WebSocketServerProtocol]] = {}
        self.user_connections: Dict[str, str] = {}
    
    async def connect(self, websocket: websockets.WebSocketServerProtocol, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        self.user_connections[id(websocket)] = user_id
    
    def disconnect(self, websocket: websockets.WebSocketServerProtocol):
        user_id = self.user_connections.pop(id(websocket), None)
        if user_id and user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
    
    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_text(message)
                except:
                    pass
    
    async def broadcast(self, message: str):
        for user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_text(message)
                except:
                    pass

manager = ConnectionManager()

# ============================================================
# AUTH FUNCTIONS
# ============================================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError:
        return None

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: SessionLocal = Depends(get_db)):
    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication")
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user

def generate_api_key():
    return secrets.token_urlsafe(32)

# ============================================================
# EMAIL FUNCTIONS
# ============================================================
def send_email(to_email, subject, html_content):
    try:
        msg = MIMEText(html_content, 'html')
        msg['Subject'] = subject
        msg['From'] = os.getenv("SMTP_FROM", "noreply@pocketlawyer.ai")
        msg['To'] = to_email
        
        context = ssl.create_default_context()
        with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", 587))) as server:
            server.starttls(context=context)
            server.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False

# ============================================================
# DIGITAL SIGNATURE
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
    expected = hashlib.sha256(f"{content}{signature_data['signed_by']}{signature_data['signed_at']}".encode()).hexdigest()
    return expected == signature_data['signature']

# ============================================================
# ENCRYPTION FUNCTIONS
# ============================================================
def encrypt_data(data):
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data):
    return cipher_suite.decrypt(encrypted_data.encode()).decode()

# ============================================================
# AUDIT LOGGING
# ============================================================
def log_audit(user_id, action, resource, resource_id, details, request=None):
    db = SessionLocal()
    try:
        log_entry = AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Audit log error: {e}")
    finally:
        db.close()

# ============================================================
# PDF GENERATION & READING (from v14)
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
# CONFIGURATION
# ============================================================
class ConfigStore:
    _config = {
        "brand_name": "Pocket Lawyer",
        "brand_color": "#1a56db",
        "currency": "NGN",
        "firm_name": "Pocket Law Firm",
        "firm_address": "Lagos, Nigeria",
        "firm_phone": "+234 800 000 0000",
        "firm_email": "info@pocketlawyer.ai",
        "system_prompt": """Welcome to Pocket Lawyer - Your Trusted Legal AI Assistant.

I am here to provide you with professional legal guidance and support. 
Whether you need legal advice, document generation, or case analysis,
I am here to help.

How can I assist you with your legal needs today?""",
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
        "telegram": {"enabled": True,
                     "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
                     "bot_username": "Mypocket_lawyerbot",
                     "last_offset": 0},
        "whatsapp": {"enabled": False, "phone_number_id": "", "access_token": "",
                     "verify_token": "pocket_lawyer_2024"},
        "quick_issues": [
            {"id": "tenancy", "title": "🏠 Tenancy & Landlord Disputes", "icon": "🏠", "category": "Property"},
            {"id": "employment", "title": "💼 Employment & Labour Rights", "icon": "💼", "category": "Employment"},
            {"id": "contract", "title": "📝 Contract Disputes", "icon": "📝", "category": "Business"},
            {"id": "family", "title": "👨‍👩‍👧‍👦 Family & Marriage Law", "icon": "👨‍👩‍👧‍👦", "category": "Family"},
            {"id": "debt", "title": "💰 Debt Recovery & Banking", "icon": "💰", "category": "Finance"},
            {"id": "criminal", "title": "⚖️ Criminal Defense", "icon": "⚖️", "category": "Criminal"},
            {"id": "corporate", "title": "🏢 Corporate & Business Law", "icon": "🏢", "category": "Business"},
            {"id": "property", "title": "🏡 Property & Real Estate", "icon": "🏡", "category": "Property"},
            {"id": "divorce", "title": "💔 Divorce & Separation", "icon": "💔", "category": "Family"},
            {"id": "injury", "title": "🏥 Personal Injury Claims", "icon": "🏥", "category": "Tort"},
            {"id": "tax", "title": "💰 Tax Law & Compliance", "icon": "💰", "category": "Finance"},
            {"id": "immigration", "title": "🌍 Immigration & Visas", "icon": "🌍", "category": "Immigration"},
            {"id": "intellectual", "title": "💡 Intellectual Property", "icon": "💡", "category": "Business"},
            {"id": "consumer", "title": "🛒 Consumer Protection", "icon": "🛒", "category": "Consumer"},
            {"id": "environmental", "title": "🌱 Environmental Law", "icon": "🌱", "category": "Environmental"},
            {"id": "labor", "title": "👷 Labor & Union Rights", "icon": "👷", "category": "Employment"}
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

# ============================================================
# PROVIDER ROTATOR (from v14)
# ============================================================
class ProviderRotator:
    _provider_stats = {}
    _model_index = 0
    _lock = threading.Lock()

    @classmethod
    def get_ordered_providers(cls, providers):
        with cls._lock:
            enabled = [p for p in providers if p.get("enabled", True)]
            for p in enabled:
                name = p.get("name")
                stats = cls._provider_stats.get(name, {})
                success_rate = stats.get("success", 0) / max(1, stats.get("total", 0))
                avg_time = stats.get("avg_time", 1)
                p["_performance"] = (1 - p.get("priority", 999) / 100) * 0.5 + success_rate * 0.3 + max(0, (1 - avg_time / 5)) * 0.2
            return sorted(enabled, key=lambda x: x.get("_performance", 0), reverse=True)

    @classmethod
    def record_success(cls, name, response_time):
        with cls._lock:
            if name not in cls._provider_stats:
                cls._provider_stats[name] = {"success": 0, "errors": 0, "total": 0, "avg_time": 0}
            stats = cls._provider_stats[name]
            stats["success"] += 1
            stats["total"] += 1
            stats["avg_time"] = stats["avg_time"] * 0.7 + response_time * 0.3

    @classmethod
    def record_error(cls, name):
        with cls._lock:
            if name not in cls._provider_stats:
                cls._provider_stats[name] = {"success": 0, "errors": 0, "total": 0, "avg_time": 0}
            stats = cls._provider_stats[name]
            stats["errors"] += 1
            stats["total"] += 1

    @classmethod
    def get_stats(cls):
        with cls._lock:
            return cls._provider_stats.copy()

app = FastAPI(title=APP_NAME, version=VERSION)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": str(exc)}
    )

# ============================================================
# MIDDLEWARE
# ============================================================
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    REQUESTS.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    REQUESTS_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)
    
    API_CALLS.inc()
    
    return response

# ============================================================
# MODELS
# ============================================================
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    full_name: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: str
    is_active: bool
    subscription_tier: str
    created_at: datetime
    api_key: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)

class ConfigUpdateRequest(BaseModel):
    configs: Dict[str, Any]

class AnalyzeRequest(BaseModel):
    document_id: str

class DocumentCreate(BaseModel):
    title: str
    content: str

class DocumentSignRequest(BaseModel):
    document_id: str

class PaymentRequest(BaseModel):
    plan: str
    payment_method: str = "card"

class WebSocketMessage(BaseModel):
    type: str
    data: Any

class LegalCaseResponse(BaseModel):
    id: int
    case_type: str
    title: str
    description: str
    category: str
    icon: str
    slug: str

# ============================================================
# AI FUNCTIONS (from v14)
# ============================================================
async def call_provider(base_url, api_key, model, messages):
    try:
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        system_prompt = ConfigStore.get("system_prompt", "You are Pocket Lawyer.")
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        payload = {"model": model, "messages": full_messages, "temperature": 0.2, "max_tokens": 2000}
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
    providers = ProviderRotator.get_ordered_providers(ConfigStore.get_ai_providers())
    for provider in providers:
        name = provider.get("name")
        base_url = provider.get("base_url")
        api_key = provider.get("api_key")
        model = provider.get("model")
        if not base_url or not api_key or not model:
            continue
        try:
            reply, elapsed = await call_provider(base_url, api_key, model, messages)
            if reply:
                ProviderRotator.record_success(name, elapsed)
                return {"reply": reply, "provider": name}
            ProviderRotator.record_error(name)
        except Exception as e:
            logger.error(f"{name} error: {e}")
            ProviderRotator.record_error(name)
        await asyncio.sleep(0.05)
    return {"reply": "I'm having trouble connecting. Please try again later.", "provider": "offline"}

# ============================================================
# PDF GENERATOR (from v14)
# ============================================================
class PDFGenerator:
    @staticmethod
    def generate_document(title, content, author="Pocket Lawyer"):
        if not PDF_AVAILABLE:
            raise Exception("PDF generation not available")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=72, rightMargin=72,
                                topMargin=72, bottomMargin=72, title=title, author=author)

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
        return buffer

# ============================================================
# PDF READER & ANALYZER (from v14)
# ============================================================
class PDFAnalyzer:
    @staticmethod
    def extract_text_from_pdf(file_content):
        if not PDF_READER_AVAILABLE:
            raise Exception("PyMuPDF not installed.")
        
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
# DOCUMENT STORAGE
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

    if "tenancy" in message.lower() or "rent" in message.lower():
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
    # Check if user exists
    existing = db.query(User).filter(
        (User.email == user_data.email) | (User.username == user_data.username)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email or username already registered")
    
    # Create user
    user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
        api_key=generate_api_key()
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Send welcome email
    send_email(
        user.email,
        "Welcome to Pocket Lawyer!",
        f"""
        <h1>Welcome to Pocket Lawyer!</h1>
        <p>Hi {user.full_name},</p>
        <p>Your account has been created successfully.</p>
        <p>Start using Pocket Lawyer today!</p>
        """
    )
    
    # Create token
    token = create_access_token({"user_id": user.id, "username": user.username})
    
    log_audit(user.id, "register", "user", str(user.id), {"email": user.email})
    ACTIVE_USERS.inc()
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserResponse.from_orm(user)
    }

@app.post("/api/auth/login", response_model=Token)
async def login(login_data: UserLogin, db: SessionLocal = Depends(get_db)):
    user = db.query(User).filter(User.username == login_data.username).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")
    
    user.last_login = datetime.utcnow()
    db.commit()
    
    token = create_access_token({"user_id": user.id, "username": user.username})
    
    log_audit(user.id, "login", "user", str(user.id), {"username": user.username})
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserResponse.from_orm(user)
    }

@app.post("/api/auth/logout")
async def logout(current_user: User = Depends(get_current_user)):
    log_audit(current_user.id, "logout", "user", str(current_user.id), {})
    return {"status": "success"}

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserResponse.from_orm(current_user)

@app.post("/api/auth/verify-email/{token}")
async def verify_email(token: str, db: SessionLocal = Depends(get_db)):
    try:
        email = serializer.loads(token, salt="email-verify", max_age=86400)
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.is_active = True
            db.commit()
            return {"status": "success", "message": "Email verified"}
    except:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

@app.post("/api/auth/reset-password")
async def reset_password(email: str, db: SessionLocal = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    token = serializer.dumps(email, salt="password-reset")
    reset_link = f"https://pocket-lawyer-v15.onrender.com/reset-password?token={token}"
    
    send_email(
        email,
        "Reset Your Password",
        f"""
        <h1>Reset Your Password</h1>
        <p>Click <a href="{reset_link}">here</a> to reset your password.</p>
        <p>This link expires in 24 hours.</p>
        """
    )
    return {"status": "success", "message": "Reset email sent"}

@app.post("/api/auth/change-password")
async def change_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    
    current_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    log_audit(current_user.id, "change_password", "user", str(current_user.id), {})
    return {"status": "success", "message": "Password changed"}

# ============================================================
# LEGAL CASES ENDPOINTS
# ============================================================
@app.get("/api/legal-cases")
async def get_legal_cases(db: SessionLocal = Depends(get_db)):
    cases = db.query(LegalCase).all()
    return {"cases": [{"id": c.id, "title": c.title, "description": c.description, "category": c.category, "icon": c.icon, "slug": c.slug} for c in cases]}

@app.get("/api/legal-cases/{case_id}")
async def get_legal_case(case_id: int, db: SessionLocal = Depends(get_db)):
    case = db.query(LegalCase).filter(LegalCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"case": {"id": case.id, "title": case.title, "description": case.description, "category": case.category, "icon": case.icon}}

@app.post("/api/legal-cases/seed")
async def seed_legal_cases(db: SessionLocal = Depends(get_db)):
    cases = ConfigStore.get_quick_issues()
    for case_data in cases:
        case = LegalCase(
            case_type=case_data["id"],
            title=case_data["title"],
            description=f"Legal assistance for {case_data['title']}",
            category=case_data.get("category", "General"),
            icon=case_data["icon"],
            slug=case_data["id"]
        )
        db.add(case)
    db.commit()
    return {"status": "success", "message": f"Seeded {len(cases)} cases"}

# ============================================================
# CHAT ENDPOINT (Enhanced)
# ============================================================
@app.post("/api/chat")
async def chat(
    chat_req: ChatRequest,
    current_user: Optional[User] = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    brand = ConfigStore.get("brand_name", "Pocket Lawyer")
    
    # Track chat
    CHAT_MESSAGES.inc()
    
    # Check subscription limits
    if current_user:
        plan = PLANS.get(current_user.subscription_tier, PLANS["free"])
        chat_count = db.query(Chat).filter(Chat.user_id == current_user.id).count()
        if chat_count >= plan["requests"]:
            raise HTTPException(status_code=429, detail="Monthly request limit reached")
    
    # Generate PDF if requested
    pdf_keywords = ["generate pdf", "create pdf", "make pdf", "tenancy agreement", "nda"]
    if any(word in chat_req.message.lower() for word in pdf_keywords):
        result = await generate_document_from_chat(chat_req.message)
        if result.get("status") == "success":
            PDF_GENERATED.inc()
            
            # Save to database if authenticated
            if current_user:
                doc = Document(
                    user_id=current_user.id,
                    title=result.get("title"),
                    content=result.get("content"),
                    document_type="generated",
                    file_path=result.get("document_id"),
                    is_encrypted=True
                )
                db.add(doc)
                db.commit()
                
                log_audit(current_user.id, "generate_pdf", "document", result.get("document_id"), {"title": result.get("title")})
            
            return {
                "reply": f"✅ Document generated: {result.get('title')}",
                "provider": brand,
                "pdf_url": result.get("pdf_url"),
                "document_id": result.get("document_id"),
                "is_pdf": True
            }
    
    # Get AI response
    result = await get_ai_response([{"role": "user", "content": chat_req.message}])
    
    # Save chat if authenticated
    if current_user:
        chat = Chat(
            user_id=current_user.id,
            session_id=f"session_{int(time.time())}",
            message=chat_req.message,
            response=result["reply"],
            provider=result.get("provider", brand)
        )
        db.add(chat)
        db.commit()
        
        log_audit(current_user.id, "chat", "chat", str(chat.id), {"message": chat_req.message[:50]})
    
    return {
        "reply": result["reply"],
        "provider": result.get("provider", brand)
    }

# ============================================================
# DOCUMENT ENDPOINTS (Enhanced)
# ============================================================
@app.post("/api/documents/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    try:
        content = await file.read()
        filename = file.filename
        
        if not filename.lower().endswith('.pdf'):
            return {"status": "error", "message": "Only PDF files are supported"}
        
        if not PDF_READER_AVAILABLE:
            return {"status": "error", "message": "PDF reader not available"}
        
        extracted_text = PDFAnalyzer.extract_text_from_pdf(content)
        
        # Encrypt content
        encrypted_content = encrypt_data(extracted_text)
        
        doc_id = f"upload_{int(time.time())}_{hashlib.md5(filename.encode()).hexdigest()[:6]}"
        file_path = os.path.join("uploads", f"{doc_id}_{filename}")
        
        # Save encrypted file
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # Save to database
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
            "document_id": document.id,
            "analysis": None
        }
        
        PDF_ANALYZED.inc()
        
        log_audit(current_user.id, "upload_document", "document", str(document.id), {"filename": filename})
        
        return {
            "status": "success",
            "document_id": doc_id,
            "db_id": document.id,
            "filename": filename,
            "characters": len(extracted_text),
            "words": len(extracted_text.split()),
            "message": "PDF uploaded and encrypted successfully!"
        }
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/documents/analyze")
async def analyze_pdf(
    request: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    doc = uploaded_docs.get(request.document_id)
    if not doc:
        # Check database
        db_doc = db.query(Document).filter(Document.id == request.document_id).first()
        if db_doc:
            content = decrypt_data(db_doc.content)
            doc = {"content": content}
    
    if not doc:
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
        
        messages = [{"role": "user", "content": prompt}]
        result = await get_ai_response(messages)
        
        if result["reply"]:
            doc["analysis"] = result["reply"]
            
            log_audit(current_user.id, "analyze_document", "document", request.document_id, {"analysis_type": "full"})
            
            return {
                "status": "success",
                "analysis": result["reply"],
                "provider": result["provider"]
            }
        
        return {"status": "error", "message": "Analysis failed"}
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/documents/sign")
async def sign_document(
    request: DocumentSignRequest,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    doc = uploaded_docs.get(request.document_id)
    if not doc:
        db_doc = db.query(Document).filter(Document.id == request.document_id).first()
        if db_doc:
            content = decrypt_data(db_doc.content)
            doc = {"content": content, "db_id": db_doc.id}
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Create digital signature
    signature_data = sign_document(doc["content"], current_user.id)
    
    # Update database if applicable
    if "db_id" in doc:
        db_doc = db.query(Document).filter(Document.id == doc["db_id"]).first()
        if db_doc:
            db_doc.is_signed = True
            db_doc.signature_hash = signature_data["signature"]
            db_doc.signature_date = datetime.utcnow()
            db.commit()
    
    log_audit(current_user.id, "sign_document", "document", request.document_id, {"signature": signature_data["signature"][:20]})
    
    return {
        "status": "success",
        "signature": signature_data,
        "message": "Document signed successfully"
    }

@app.get("/api/documents/verify/{document_id}")
async def verify_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    doc = uploaded_docs.get(document_id)
    if not doc:
        db_doc = db.query(Document).filter(Document.id == document_id).first()
        if db_doc:
            content = decrypt_data(db_doc.content)
            doc = {"content": content, "db_id": db_doc.id}
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "status": "success",
        "verified": True,
        "message": "Document integrity verified"
    }

@app.get("/api/documents")
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    docs = db.query(Document).filter(Document.user_id == current_user.id).all()
    return {
        "status": "success",
        "documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "filename": doc.filename,
                "created_at": doc.created_at,
                "is_signed": doc.is_signed,
                "is_encrypted": doc.is_encrypted,
                "version": doc.version
            }
            for doc in docs
        ]
    }

# ============================================================
# PAYMENT ENDPOINTS
# ============================================================
@app.post("/api/payments/create-intent")
async def create_payment_intent(
    request: PaymentRequest,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payment service unavailable")
    
    plan = PLANS.get(request.plan)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid plan")
    
    try:
        # Convert NGN to cents (for Stripe) - assuming you're using NGN
        amount = plan["price"] * 100  # Convert to kobo/cents
        
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="NGN",
            metadata={"plan": request.plan, "user_id": current_user.id},
            payment_method_types=["card", "bank_transfer"]
        )
        
        payment = Payment(
            user_id=current_user.id,
            stripe_payment_id=intent.id,
            amount=plan["price"],
            currency="NGN",
            plan=request.plan,
            status="pending"
        )
        db.add(payment)
        db.commit()
        
        log_audit(current_user.id, "create_payment", "payment", intent.id, {"plan": request.plan})
        
        return {
            "status": "success",
            "client_secret": intent.client_secret,
            "payment_id": intent.id
        }
    except Exception as e:
        logger.error(f"Payment error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/payments/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        payment_id = intent["id"]
        user_id = int(intent["metadata"]["user_id"])
        plan = intent["metadata"]["plan"]
        
        db = SessionLocal()
        try:
            payment = db.query(Payment).filter(Payment.stripe_payment_id == payment_id).first()
            if payment:
                payment.status = "completed"
                
                # Update user subscription
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user.subscription_tier = plan
                    # Set expiration (30 days from now)
                    user.subscription_expires = datetime.utcnow() + timedelta(days=30)
                    
                    log_audit(user_id, "subscription_upgrade", "payment", payment_id, {"plan": plan})
                
                db.commit()
                
                # Send confirmation email
                if user:
                    send_email(
                        user.email,
                        "Subscription Confirmed",
                        f"""
                        <h1>Subscription Confirmed!</h1>
                        <p>Hi {user.full_name},</p>
                        <p>Your {plan} plan is now active.</p>
                        <p>Thank you for choosing Pocket Lawyer!</p>
                        """
                    )
        finally:
            db.close()
    
    return {"status": "success"}

@app.get("/api/payments/subscription")
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    plan = PLANS.get(current_user.subscription_tier, PLANS["free"])
    return {
        "status": "success",
        "plan": current_user.subscription_tier,
        "expires": current_user.subscription_expires,
        "features": plan["features"],
        "requests": plan["requests"]
    }

# ============================================================
# WEBSOCKET ENDPOINTS
# ============================================================
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "timestamp": datetime.utcnow().isoformat()}))
            elif message.get("type") == "chat":
                # Process chat message in real-time
                msg = message.get("data", "")
                response = await get_ai_response([{"role": "user", "content": msg}])
                await websocket.send_text(json.dumps({
                    "type": "chat_response",
                    "data": response,
                    "timestamp": datetime.utcnow().isoformat()
                }))
            elif message.get("type") == "typing":
                await websocket.send_text(json.dumps({"type": "typing", "timestamp": datetime.utcnow().isoformat()}))
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)

# ============================================================
# ANALYTICS ENDPOINTS
# ============================================================
@app.get("/api/analytics/metrics")
async def get_metrics(current_user: User = Depends(get_current_user)):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return {
        "status": "success",
        "metrics": {
            "total_requests": API_CALLS._value.get(),
            "pdf_generated": PDF_GENERATED._value.get(),
            "pdf_analyzed": PDF_ANALYZED._value.get(),
            "chat_messages": CHAT_MESSAGES._value.get(),
            "active_users": ACTIVE_USERS._value.get()
        }
    }

@app.get("/api/analytics/prometheus")
async def prometheus_metrics(current_user: User = Depends(get_current_user)):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return Response(content=generate_latest(), media_type="text/plain")

@app.get("/api/analytics/usage")
async def get_usage(current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        chats = db.query(Chat).filter(Chat.user_id == current_user.id).count()
        documents = db.query(Document).filter(Document.user_id == current_user.id).count()
        
        return {
            "status": "success",
            "usage": {
                "chats": chats,
                "documents": documents,
                "subscription": current_user.subscription_tier,
                "expires": current_user.subscription_expires
            }
        }
    finally:
        db.close()

# ============================================================
# ADMIN ENDPOINTS
# ============================================================
@app.get("/api/admin/users")
async def list_users(
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    users = db.query(User).all()
    return {
        "status": "success",
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "full_name": u.full_name,
                "subscription_tier": u.subscription_tier,
                "is_active": u.is_active,
                "last_login": u.last_login,
                "created_at": u.created_at
            }
            for u in users
        ]
    }

@app.put("/api/admin/users/{user_id}")
async def update_user(
    user_id: int,
    updates: dict,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if "subscription_tier" in updates:
        user.subscription_tier = updates["subscription_tier"]
    if "is_active" in updates:
        user.is_active = updates["is_active"]
    if "is_superuser" in updates:
        user.is_superuser = updates["is_superuser"]
    
    db.commit()
    
    log_audit(current_user.id, "admin_update_user", "user", str(user_id), updates)
    
    return {"status": "success", "message": "User updated"}

# ============================================================
# TELEGRAM (from v14 with enhancements)
# ============================================================
telegram_running = False
telegram_thread = None
telegram_lock = threading.Lock()

def start_telegram_polling():
    global telegram_running, telegram_thread
    with telegram_lock:
        if telegram_running: return
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
                time.sleep(5); continue
            if offset == 0: offset = tg.get("last_offset", 0)
            url = f"https://api.telegram.org/bot{tg['bot_token']}/getUpdates"
            response = httpx.get(url, params={"offset": offset, "timeout": 5}, timeout=15)
            if response.status_code == 200:
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
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                
                                # Check if PDF generation requested
                                pdf_keywords = ["generate pdf", "create pdf", "make pdf", "tenancy agreement", "nda"]
                                if any(word in text.lower() for word in pdf_keywords):
                                    result = loop.run_until_complete(generate_document_from_chat(text))
                                    if result.get("status") == "success":
                                        reply = f"📄 Document generated: {result.get('title')}\n\nDownload: https://pocket-lawyer-v15.onrender.com/api/documents/{result.get('document_id')}/download"
                                    else:
                                        reply = f"❌ Failed to generate PDF: {result.get('message', 'Unknown error')}"
                                else:
                                    ai_response = loop.run_until_complete(get_ai_response([{"role": "user", "content": text}]))
                                    reply = ai_response.get("reply", "I'm sorry, I couldn't process that.")
                                
                                loop.close()
                                full_reply = f"{reply}\n\n- {brand}"
                                send_url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
                                httpx.post(send_url, json={"chat_id": chat_id, "text": full_reply[:4000]})
            elif response.status_code == 409:
                time.sleep(10)
        except Exception as e:
            logger.error(f"Telegram error: {e}")
        time.sleep(2)

# ============================================================
# LIFECYCLE
# ============================================================
@app.on_event("startup")
async def startup():
    logger.info(f"Starting {APP_NAME} v{VERSION}")
    logger.info(f"PDF Generation: {'✅' if PDF_AVAILABLE else '❌'}")
    logger.info(f"PDF Reader: {'✅' if PDF_READER_AVAILABLE else '❌'}")
    logger.info(f"Database: {'✅' if DATABASE_URL else '❌'}")
    logger.info(f"Stripe: {'✅' if stripe.api_key else '❌'}")
    logger.info(f"Analytics: {'✅' if analytics.write_key else '❌'}")
    
    # Start Telegram polling
    start_telegram_polling()
    
    # Seed initial data
    db = SessionLocal()
    try:
        # Create admin user if not exists
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
            logger.info("Admin user created")
        
        # Seed legal cases
        cases_count = db.query(LegalCase).count()
        if cases_count == 0:
            cases = ConfigStore.get_quick_issues()
            for case_data in cases:
                case = LegalCase(
                    case_type=case_data["id"],
                    title=case_data["title"],
                    description=f"Legal assistance for {case_data['title']}",
                    category=case_data.get("category", "General"),
                    icon=case_data["icon"],
                    slug=case_data["id"]
                )
                db.add(case)
            db.commit()
            logger.info(f"Seeded {len(cases)} legal cases")
    except Exception as e:
        logger.error(f"Startup error: {e}")
    finally:
        db.close()

@app.on_event("shutdown")
async def shutdown():
    stop_telegram_polling()
    logger.info("Shutting down")

# ============================================================
# FRONTEND UI - WELCOME PAGE WITH CASES
# ============================================================
@app.get("/")
async def home(request: Request):
    brand = ConfigStore.get("brand_name", "Pocket Lawyer")
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
    <title>{brand} - Legal AI Assistant</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="description" content="Your trusted AI legal assistant for Nigerian Law">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
        
        /* Header */
        .header {{ background: #1e293b; padding: 20px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
        .header h1 {{ color: #60a5fa; font-size: 1.8rem; }}
        .header h1 span {{ color: #f59e0b; }}
        
        /* Hero Section */
        .hero {{ text-align: center; padding: 60px 20px; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-bottom: 1px solid #334155; }}
        .hero h1 {{ font-size: 3.5rem; color: #60a5fa; margin-bottom: 16px; }}
        .hero h1 .highlight {{ color: #f59e0b; }}
        .hero p {{ font-size: 1.3rem; color: #94a3b8; max-width: 700px; margin: 0 auto 24px; }}
        .hero .subtitle {{ font-size: 1rem; color: #64748b; max-width: 600px; margin: 0 auto; }}
        
        .btn-group {{ display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 24px; }}
        .btn {{ padding: 12px 32px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; transition: all 0.3s; }}
        .btn-primary {{ background: #3b82f6; color: white; }}
        .btn-primary:hover {{ background: #2563eb; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(59,130,246,0.4); }}
        .btn-success {{ background: #10b981; color: white; }}
        .btn-success:hover {{ background: #059669; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(16,185,129,0.4); }}
        .btn-outline {{ background: transparent; color: #94a3b8; border: 1px solid #334155; }}
        .btn-outline:hover {{ background: #1e293b; transform: translateY(-2px); }}
        
        /* Stats */
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; max-width: 800px; margin: -24px auto 0; position: relative; z-index: 10; }}
        .stat-card {{ background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; text-align: center; backdrop-filter: blur(10px); }}
        .stat-value {{ font-size: 2rem; font-weight: bold; color: #60a5fa; }}
        .stat-label {{ color: #94a3b8; font-size: 0.85rem; }}
        
        /* Features */
        .features {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; padding: 40px 20px; max-width: 1200px; margin: 0 auto; }}
        .feature {{ background: #1e293b; padding: 30px; border-radius: 12px; border: 1px solid #334155; text-align: center; transition: all 0.3s; }}
        .feature:hover {{ border-color: #60a5fa; transform: translateY(-4px); box-shadow: 0 8px 24px rgba(59,130,246,0.1); }}
        .feature .icon {{ font-size: 3rem; margin-bottom: 12px; display: block; }}
        .feature h3 {{ color: #60a5fa; margin: 8px 0; }}
        .feature p {{ color: #94a3b8; font-size: 0.9rem; line-height: 1.6; }}
        
        /* Legal Cases Grid */
        .cases-section {{ padding: 40px 20px; max-width: 1200px; margin: 0 auto; }}
        .cases-section h2 {{ text-align: center; margin-bottom: 24px; color: #f59e0b; font-size: 2rem; }}
        .cases-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }}
        .case-card {{ background: #1e293b; padding: 16px 20px; border-radius: 10px; border: 1px solid #334155; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: all 0.3s; }}
        .case-card:hover {{ border-color: #60a5fa; transform: translateX(4px) scale(1.02); background: #253450; box-shadow: 0 4px 12px rgba(59,130,246,0.2); }}
        .case-icon {{ font-size: 1.8rem; flex-shrink: 0; }}
        .case-title {{ color: #e2e8f0; font-size: 0.95rem; }}
        .case-badge {{ background: #3b82f620; color: #60a5fa; padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; margin-left: auto; }}
        
        /* Footer */
        .footer {{ text-align: center; color: #64748b; font-size: 0.8rem; padding: 24px; border-top: 1px solid #1e293b; }}
        
        @media (max-width: 768px) {{
            .header {{ flex-direction: column; text-align: center; padding: 16px; }}
            .hero h1 {{ font-size: 2.2rem; }}
            .features {{ grid-template-columns: 1fr; padding: 20px; }}
            .cases-grid {{ grid-template-columns: 1fr; }}
        }}
        
        /* Animations */
        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(30px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .hero, .features, .cases-section {{ animation: fadeInUp 0.8s ease-out; }}
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
        <div class="cases-grid" id="casesGrid"></div>
    </div>
    
    <div class="footer">
        <p>⚖️ Pocket Lawyer v15.0 • Enterprise Edition • General guidance only</p>
        <p style="margin-top:4px;">For specific legal advice, please consult a qualified lawyer</p>
    </div>
    
    <script>
        // Load legal cases from API
        async function loadCases() {{
            try {{
                const response = await fetch('/api/legal-cases');
                const data = await response.json();
                const grid = document.getElementById('casesGrid');
                
                data.cases.forEach(caseItem => {{
                    const card = document.createElement('div');
                    card.className = 'case-card';
                    card.innerHTML = `
                        <span class="case-icon">${{caseItem.icon || '⚖️'}}</span>
                        <span class="case-title">${{caseItem.title}}</span>
                        <span class="case-badge">${{caseItem.category || 'Legal'}}</span>
                    `;
                    card.onclick = () => {{
                        window.location.href = "/chat?q=" + encodeURIComponent(caseItem.title);
                    }};
                    grid.appendChild(card);
                }});
            }} catch(e) {{
                console.error('Error loading cases:', e);
            }}
        }}
        
        loadCases();
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
.login-container h2 { color: #60a5fa; text-align: center; margin-bottom: 24px; }
.form-group { margin-bottom: 16px; }
.form-group label { color: #94a3b8; display: block; margin-bottom: 4px; }
.form-group input { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 1rem; }
.form-group input:focus { border-color: #3b82f6; outline: none; }
.btn { width: 100%; padding: 12px; border: none; border-radius: 8px; background: #3b82f6; color: white; font-weight: 600; cursor: pointer; font-size: 1rem; }
.btn:hover { background: #2563eb; }
.links { text-align: center; margin-top: 16px; color: #94a3b8; }
.links a { color: #60a5fa; text-decoration: none; }
.links a:hover { text-decoration: underline; }
</style>
</head>
<body>
<div class="login-container">
    <h2>⚖️ Welcome Back</h2>
    <form onsubmit="login(event)">
        <div class="form-group">
            <label>Username</label>
            <input type="text" id="username" required placeholder="Enter your username">
        </div>
        <div class="form-group">
            <label>Password</label>
            <input type="password" id="password" required placeholder="Enter your password">
        </div>
        <button type="submit" class="btn">Sign In</button>
    </form>
    <div class="links">
        <p>Don't have an account? <a href="/auth/register">Register</a></p>
        <p><a href="/auth/forgot-password">Forgot Password?</a></p>
    </div>
</div>
<script>
async function login(e) {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, password})
        });
        const data = await response.json();
        if (response.ok) {
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('user', JSON.stringify(data.user));
            window.location.href = '/chat';
        } else {
            alert(data.detail || 'Login failed');
        }
    } catch(e) {
        alert('Error: ' + e.message);
    }
}
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
.register-container h2 { color: #60a5fa; text-align: center; margin-bottom: 24px; }
.form-group { margin-bottom: 16px; }
.form-group label { color: #94a3b8; display: block; margin-bottom: 4px; }
.form-group input { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 1rem; }
.form-group input:focus { border-color: #3b82f6; outline: none; }
.btn { width: 100%; padding: 12px; border: none; border-radius: 8px; background: #10b981; color: white; font-weight: 600; cursor: pointer; font-size: 1rem; }
.btn:hover { background: #059669; }
.links { text-align: center; margin-top: 16px; color: #94a3b8; }
.links a { color: #60a5fa; text-decoration: none; }
.links a:hover { text-decoration: underline; }
</style>
</head>
<body>
<div class="register-container">
    <h2>🚀 Create Your Account</h2>
    <p style="text-align:center;color:#94a3b8;margin-bottom:20px;">Start using Pocket Lawyer today</p>
    <form onsubmit="register(event)">
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
            <label>Password</label>
            <input type="password" id="password" required placeholder="Create a password (min 6 chars)">
        </div>
        <button type="submit" class="btn">Create Account</button>
    </form>
    <div class="links">
        <p>Already have an account? <a href="/auth/login">Login</a></p>
    </div>
</div>
<script>
async function register(e) {
    e.preventDefault();
    const full_name = document.getElementById('full_name').value;
    const username = document.getElementById('username').value;
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    
    if (password.length < 6) {
        alert('Password must be at least 6 characters');
        return;
    }
    
    try {
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({full_name, username, email, password})
        });
        const data = await response.json();
        if (response.ok) {
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('user', JSON.stringify(data.user));
            window.location.href = '/chat';
        } else {
            alert(data.detail || 'Registration failed');
        }
    } catch(e) {
        alert('Error: ' + e.message);
    }
}
</script>
</body>
</html>
""")

# ============================================================
# CHAT UI (Enhanced with Authentication)
# ============================================================
@app.get("/chat")
async def chat_ui():
    brand = ConfigStore.get("brand_name", "Pocket Lawyer")
    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head><title>{brand} - AI Chat</title>
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
.user-info {{ color: #94a3b8; font-size: 0.9rem; display: flex; align-items: center; gap: 12px; }}
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
<div class="message ai"><strong>{brand}</strong><br>Hello! I am your AI legal assistant.<br>How can I help you today?</div>
</div>
<div class="input-area">
<input type="text" id="userInput" placeholder="Type your legal question..." onkeypress="if(event.key===13) sendMessage()">
<button onclick="sendMessage()">Send</button>
</div>
<div class="disclaimer">General guidance only. Consult a lawyer for legal advice.</div>
</div>
<script>
// Check authentication
const token = localStorage.getItem('token');
if (!token) {{
    window.location.href = '/auth/login';
}}

// Load user info
const user = JSON.parse(localStorage.getItem('user') || '{{"username":"User"}}');
document.getElementById('userDisplay').textContent = `👤 ${{user.username}}`;

const chatBox=document.getElementById('chatBox');
function addMessage(sender, text, isHTML = false) {{
    const div=document.createElement('div');
    div.className='message '+sender;
    if (isHTML) {{ div.innerHTML = text; }} else {{ div.textContent = text; }}
    chatBox.appendChild(div);
    chatBox.scrollTop=chatBox.scrollHeight;
}}
function addTyping() {{
    const div=document.createElement('div');
    div.className='typing';
    div.id='typing';
    div.textContent='Thinking...';
    chatBox.appendChild(div);
}}
function removeTyping() {{
    const typing=document.getElementById('typing');
    if(typing) typing.remove();
}}
async function sendMessage() {{
    const input=document.getElementById('userInput');
    const message=input.value.trim();
    if(!message) return;
    input.value='';
    addMessage('user', message);
    addTyping();
    try {{
        const res=await fetch('/api/chat', {{
            method:'POST',
            headers:{{
                'Content-Type':'application/json',
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            }},
            body:JSON.stringify({{message:message}})
        }});
        const data=await res.json();
        removeTyping();
        if (data.pdf_url) {{
            const pdfLink = `<a href="${{data.pdf_url}}" target="_blank" class="pdf-link">📄 Download PDF</a>`;
            addMessage('ai', data.reply + '<br>' + pdfLink, true);
        }} else {{
            addMessage('ai', data.reply);
        }}
    }} catch(e) {{
        removeTyping();
        addMessage('ai','Error connecting to server.');
    }}
}}

function logout() {{
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/auth/login';
}}

// Handle query parameter for quick cases
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
# MAIN
# ============================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)





