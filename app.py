# ============================================================
# POCKET LAWYER v15.0 - FULLY ROBUST ENTERPRISE EDITION
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
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Depends, status, Form
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
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

VERSION = "15.0.11"
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
    phone_number = Column(String(20))
    telegram_chat_id = Column(String(100))
    whatsapp_number = Column(String(20))

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
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    order = Column(Integer, default=0)

class SystemSetting(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text)
    setting_type = Column(String(50), default="string")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)

class TelegramSettings(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    bot_username: str = ""

class WhatsAppSettings(BaseModel):
    enabled: bool = False
    phone_number_id: str = ""
    access_token: str = ""
    verify_token: str = ""

# ============================================================
# CONFIG STORE WITH DATABASE FALLBACK
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
        "telegram": {"enabled": False, "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""), "bot_username": "Mypocket_lawyerbot"},
        "whatsapp": {"enabled": False, "phone_number_id": "", "access_token": "", "verify_token": "pocket_lawyer_2024"},
        "legal_cases": [
            {"title": "🏠 Tenancy & Landlord Disputes", "icon": "🏠", "category": "Property", 
             "description": "Resolve landlord-tenant disputes, rent issues, and eviction matters"},
            {"title": "💼 Employment & Labour Rights", "icon": "💼", "category": "Employment",
             "description": "Know your rights as an employee or employer in Nigeria"},
            {"title": "📝 Contract Disputes", "icon": "📝", "category": "Business",
             "description": "Breach of contract, agreement drafting, and dispute resolution"},
            {"title": "👨‍👩‍👧‍👦 Family & Marriage Law", "icon": "👨‍👩‍👧‍👦", "category": "Family",
             "description": "Marriage, divorce, child custody, and family matters"},
            {"title": "💰 Debt Recovery & Banking", "icon": "💰", "category": "Finance",
             "description": "Debt collection, loan recovery, and banking disputes"},
            {"title": "⚖️ Criminal Defense", "icon": "⚖️", "category": "Criminal",
             "description": "Criminal charges, defense strategies, and legal representation"},
            {"title": "🏢 Corporate & Business Law", "icon": "🏢", "category": "Business",
             "description": "Company registration, compliance, and corporate governance"},
            {"title": "🏡 Property & Real Estate", "icon": "🏡", "category": "Property",
             "description": "Property transactions, disputes, and real estate law"},
            {"title": "💔 Divorce & Separation", "icon": "💔", "category": "Family",
             "description": "Divorce proceedings, property division, and custody arrangements"},
            {"title": "🏥 Personal Injury Claims", "icon": "🏥", "category": "Tort",
             "description": "Personal injury, medical malpractice, and compensation claims"},
            {"title": "💰 Tax Law & Compliance", "icon": "💰", "category": "Finance",
             "description": "Tax planning, compliance, and dispute resolution"},
            {"title": "🌍 Immigration & Visas", "icon": "🌍", "category": "Immigration",
             "description": "Visa applications, immigration processes, and citizenship"},
            {"title": "💡 Intellectual Property", "icon": "💡", "category": "Business",
             "description": "Trademarks, copyrights, patents, and IP protection"},
            {"title": "🛒 Consumer Protection", "icon": "🛒", "category": "Consumer",
             "description": "Consumer rights, product liability, and fair trading"},
            {"title": "🌱 Environmental Law", "icon": "🌱", "category": "Environmental",
             "description": "Environmental compliance, pollution, and sustainability"},
            {"title": "👷 Labor & Union Rights", "icon": "👷", "category": "Employment",
             "description": "Labor rights, union activities, and workplace disputes"}
        ],
        "plans": [
            {"name": "Free", "slug": "free", "price_monthly": 0, 
             "features": ["AI Chat (50 requests)", "PDF Analysis", "Basic Support"]},
            {"name": "Pro", "slug": "pro", "price_monthly": 5000,
             "features": ["AI Chat (1000 requests)", "PDF Analysis", "PDF Generation", 
                         "Telegram Bot", "Priority Support"]},
            {"name": "Enterprise", "slug": "enterprise", "price_monthly": 15000,
             "features": ["AI Chat (Unlimited)", "PDF Analysis", "PDF Generation",
                         "Telegram Bot", "WhatsApp Bot", "Dedicated Support"]}
        ]
    }

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
    def get_legal_cases(cls):
        return cls._config.get("legal_cases", [])

    @classmethod
    def get_telegram(cls):
        return cls._config.get("telegram", {})

    @classmethod
    def get_whatsapp(cls):
        return cls._config.get("whatsapp", {})

    @classmethod
    def get_plans(cls):
        return cls._config.get("plans", [])

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
        system_prompt = ConfigStore.get("system_prompt", "You are Pocket Lawyer.")
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        payload = {"model": model, "messages": full_messages, "temperature": 0.2, "max_tokens": 2000}
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
            hashed_password=get_password_hash(user_data.password),
            phone_number=user_data.phone_number
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
                "is_superuser": user.is_superuser,
                "subscription_tier": user.subscription_tier,
                "phone_number": user.phone_number,
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
                "is_superuser": user.is_superuser,
                "subscription_tier": user.subscription_tier,
                "phone_number": user.phone_number,
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
        "is_superuser": current_user.is_superuser,
        "subscription_tier": current_user.subscription_tier,
        "phone_number": current_user.phone_number,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None
    }

# ============================================================
# LEGAL CASES
# ============================================================
@app.get("/api/legal-cases")
async def get_legal_cases(db: SessionLocal = Depends(get_db)):
    try:
        cases = db.query(LegalCase).filter(LegalCase.is_active == True).order_by(LegalCase.order).all()
        if not cases:
            return {"status": "success", "cases": ConfigStore.get_legal_cases()}
        return {"status": "success", "cases": [{"title": c.title, "icon": c.icon, "category": c.category, "description": c.description} for c in cases]}
    except:
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
                return {
                    "reply": f"✅ Document generated: {title}",
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
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={doc['title']}.pdf"}
    )

# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "version": VERSION,
        "pdf_available": PDF_AVAILABLE,
        "telegram_enabled": ConfigStore.get_telegram().get("enabled", False),
        "whatsapp_enabled": ConfigStore.get_whatsapp().get("enabled", False),
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================
# TELEGRAM INTEGRATION
# ============================================================
telegram_running = False
telegram_thread = None

def start_telegram_polling():
    global telegram_running, telegram_thread
    if telegram_running:
        return
    tg = ConfigStore.get_telegram()
    if not tg.get("enabled") or not tg.get("bot_token"):
        logger.info("Telegram not configured or disabled")
        return
    telegram_running = True
    telegram_thread = threading.Thread(target=run_telegram_polling, daemon=True)
    telegram_thread.start()
    logger.info("Telegram polling started")

def stop_telegram_polling():
    global telegram_running
    telegram_running = False
    logger.info("Telegram polling stopped")

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
                        tg["last_offset"] = offset
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

@app.post("/api/telegram/test")
async def test_telegram(request: Request, db: SessionLocal = Depends(get_db)):
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        message = data.get("message", "Test message from Pocket Lawyer!")
        
        tg = ConfigStore.get_telegram()
        if not tg.get("enabled") or not tg.get("bot_token"):
            return JSONResponse(status_code=400, content={"status": "error", "message": "Telegram not configured"})
        
        send_url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
        response = httpx.post(send_url, json={"chat_id": chat_id, "text": f"🤖 Test from Pocket Lawyer:\n\n{message}"}, timeout=10)
        
        if response.status_code == 200:
            return {"status": "success", "message": "Test message sent successfully!"}
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Telegram error: {response.status_code}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# ============================================================
# WHATSAPP INTEGRATION
# ============================================================
@app.post("/api/whatsapp/test")
async def test_whatsapp(request: Request):
    try:
        data = await request.json()
        to = data.get("to")
        message = data.get("message", "Test message from Pocket Lawyer!")
        
        wa = ConfigStore.get_whatsapp()
        if not wa.get("enabled") or not wa.get("access_token") or not wa.get("phone_number_id"):
            return JSONResponse(status_code=400, content={"status": "error", "message": "WhatsApp not configured"})
        
        url = f"https://graph.facebook.com/v18.0/{wa['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {wa['access_token']}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": f"🤖 Test from Pocket Lawyer:\n\n{message}"}
        }
        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201, 202]:
            return {"status": "success", "message": "Test message sent successfully!"}
        return JSONResponse(status_code=400, content={"status": "error", "message": f"WhatsApp error: {response.status_code}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# ============================================================
# ADMIN - COMPLETE UI
# ============================================================
@app.get("/admin")
async def admin_dashboard(current_user: User = Depends(get_admin_user), db: SessionLocal = Depends(get_db)):
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_chats = db.query(Chat).count()
    tg = ConfigStore.get_telegram()
    wa = ConfigStore.get_whatsapp()
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>Admin Dashboard - Pocket Lawyer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
        .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
        .header h1 {{ color: #60a5fa; font-size: 1.5rem; }}
        .header h1 span {{ color: #f59e0b; }}
        .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; transition: all 0.3s; }}
        .btn-primary {{ background: #3b82f6; color: white; }}
        .btn-primary:hover {{ background: #2563eb; transform: translateY(-2px); }}
        .btn-success {{ background: #10b981; color: white; }}
        .btn-success:hover {{ background: #059669; transform: translateY(-2px); }}
        .btn-danger {{ background: #ef4444; color: white; }}
        .btn-danger:hover {{ background: #dc2626; transform: translateY(-2px); }}
        .btn-secondary {{ background: #334155; color: white; }}
        .btn-secondary:hover {{ background: #475569; transform: translateY(-2px); }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .stat-card {{ background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; text-align: center; transition: all 0.3s; }}
        .stat-card:hover {{ border-color: #60a5fa; transform: translateY(-4px); }}
        .stat-value {{ font-size: 2rem; font-weight: bold; color: #60a5fa; }}
        .stat-label {{ color: #94a3b8; font-size: 0.85rem; margin-top: 4px; }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
        .card {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; }}
        .card h3 {{ color: #f59e0b; margin-bottom: 12px; font-size: 1.1rem; }}
        .card p {{ color: #94a3b8; margin: 4px 0; }}
        .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
        .toggle-on {{ background: #10b98120; color: #10b981; padding: 4px 12px; border-radius: 12px; border: 1px solid #10b98140; display: inline-block; font-size: 0.8rem; }}
        .toggle-off {{ background: #ef444420; color: #ef4444; padding: 4px 12px; border-radius: 12px; border: 1px solid #ef444440; display: inline-block; font-size: 0.8rem; }}
        .badge {{ padding: 4px 12px; border-radius: 12px; font-size: 0.75rem; display: inline-block; }}
        .badge-admin {{ background: #f59e0b20; color: #f59e0b; border: 1px solid #f59e0b40; }}
        .badge-user {{ background: #3b82f620; color: #60a5fa; border: 1px solid #3b82f640; }}
        .badge-active {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
        .badge-inactive {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
        @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} .header {{ flex-direction: column; text-align: center; }} }}
    </style>
    </head>
    <body>
        <div class="header">
            <div><h1>⚖️ <span>Pocket</span> Lawyer Admin</h1></div>
            <div>
                <a href="/admin/users" class="btn btn-primary">👥 Users</a>
                <a href="/admin/telegram" class="btn btn-primary">🤖 Telegram</a>
                <a href="/admin/whatsapp" class="btn btn-primary">💬 WhatsApp</a>
                <a href="/admin/logs" class="btn btn-primary">📋 Logs</a>
                <a href="/chat" class="btn btn-success">💬 Chat</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
            </div>
        </div>
        <div class="container">
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-value">{total_users}</div><div class="stat-label">Total Users</div></div>
                <div class="stat-card"><div class="stat-value">{active_users}</div><div class="stat-label">Active Users</div></div>
                <div class="stat-card"><div class="stat-value">{total_chats}</div><div class="stat-label">Total Chats</div></div>
                <div class="stat-card"><div class="stat-value">{"✅" if PDF_AVAILABLE else "❌"}</div><div class="stat-label">PDF Generation</div></div>
                <div class="stat-card"><div class="stat-value"><span class="{"toggle-on" if tg.get("enabled") else "toggle-off"}">{"🟢" if tg.get("enabled") else "🔴"}</span></div><div class="stat-label">Telegram</div></div>
                <div class="stat-card"><div class="stat-value"><span class="{"toggle-on" if wa.get("enabled") else "toggle-off"}">{"🟢" if wa.get("enabled") else "🔴"}</span></div><div class="stat-label">WhatsApp</div></div>
            </div>
            <div class="grid-2">
                <div class="card">
                    <h3>🔧 Quick Actions</h3>
                    <div class="actions">
                        <a href="/admin/users" class="btn btn-primary">👥 Users</a>
                        <a href="/admin/telegram" class="btn btn-primary">🤖 Telegram</a>
                        <a href="/admin/whatsapp" class="btn btn-primary">💬 WhatsApp</a>
                        <a href="/admin/logs" class="btn btn-primary">📋 Logs</a>
                        <a href="/admin/settings" class="btn btn-primary">⚙️ Settings</a>
                    </div>
                </div>
                <div class="card">
                    <h3>ℹ️ System Info</h3>
                    <p>📊 Version: {VERSION}</p>
                    <p>📄 PDF: {"✅ Available" if PDF_AVAILABLE else "❌ Not Available"}</p>
                    <p>🤖 AI Providers: {len([p for p in ConfigStore.get_ai_providers() if p.get("enabled")])}/{len(ConfigStore.get_ai_providers())}</p>
                    <p>📱 Telegram: {"🟢 Enabled" if tg.get("enabled") else "🔴 Disabled"}</p>
                    <p>💬 WhatsApp: {"🟢 Enabled" if wa.get("enabled") else "🔴 Disabled"}</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """)

# ============================================================
# ADMIN - TELEGRAM SETTINGS
# ============================================================
@app.get("/admin/telegram")
async def admin_telegram(current_user: User = Depends(get_admin_user)):
    tg = ConfigStore.get_telegram()
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>Telegram Settings - Pocket Lawyer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
        .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
        .header h1 {{ color: #60a5fa; }}
        .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; transition: all 0.3s; }}
        .btn-primary {{ background: #3b82f6; color: white; }}
        .btn-primary:hover {{ background: #2563eb; transform: translateY(-2px); }}
        .btn-success {{ background: #10b981; color: white; }}
        .btn-success:hover {{ background: #059669; transform: translateY(-2px); }}
        .btn-danger {{ background: #ef4444; color: white; }}
        .btn-danger:hover {{ background: #dc2626; transform: translateY(-2px); }}
        .btn-secondary {{ background: #334155; color: white; }}
        .btn-secondary:hover {{ background: #475569; transform: translateY(-2px); }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 24px; }}
        .card {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px; }}
        .card h3 {{ color: #f59e0b; margin-bottom: 12px; }}
        .form-group {{ margin-bottom: 16px; }}
        .form-group label {{ color: #94a3b8; display: block; margin-bottom: 4px; font-size: 0.9rem; }}
        .form-group input, .form-group select {{ width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 1rem; }}
        .form-group input:focus, .form-group select:focus {{ border-color: #3b82f6; outline: none; }}
        .status-badge {{ padding: 4px 12px; border-radius: 12px; display: inline-block; font-size: 0.9rem; }}
        .status-on {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
        .status-off {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
        .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
        .message {{ padding: 12px; border-radius: 8px; margin-top: 12px; display: none; }}
        .message-success {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
        .message-error {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
    </style>
    </head>
    <body>
        <div class="header">
            <div><h1>🤖 Telegram Settings</h1></div>
            <div>
                <a href="/admin" class="btn btn-secondary">← Back</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
            </div>
        </div>
        <div class="container">
            <div class="card">
                <h3>📊 Status</h3>
                <p>Status: <span class="status-badge {"status-on" if tg.get("enabled") else "status-off"}">{"🟢 Enabled" if tg.get("enabled") else "🔴 Disabled"}</span></p>
                <p>Bot: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">@{tg.get("bot_username", "Not set")}</code></p>
                <p>Token: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">{"Configured" if tg.get("bot_token") else "Not configured"}</code></p>
            </div>
            <div class="card">
                <h3>🔧 Configuration</h3>
                <form id="telegramForm">
                    <div class="form-group">
                        <label>Bot Token</label>
                        <input type="text" id="bot_token" value="{tg.get("bot_token", "")}" placeholder="Enter your bot token">
                    </div>
                    <div class="form-group">
                        <label>Bot Username</label>
                        <input type="text" id="bot_username" value="{tg.get("bot_username", "")}" placeholder="e.g., MyBot">
                    </div>
                    <div class="form-group">
                        <label>Enabled</label>
                        <select id="enabled">
                            <option value="true" {"selected" if tg.get("enabled") else ""}>Yes - Enabled</option>
                            <option value="false" {"selected" if not tg.get("enabled") else ""}>No - Disabled</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">💾 Save Settings</button>
                </form>
                <div id="saveMessage" class="message"></div>
            </div>
            <div class="card">
                <h3>🧪 Test Bot</h3>
                <form id="testForm">
                    <div class="form-group">
                        <label>Chat ID</label>
                        <input type="text" id="test_chat_id" placeholder="Enter your Telegram chat ID" required>
                    </div>
                    <div class="form-group">
                        <label>Message</label>
                        <input type="text" id="test_message" value="Hello from Pocket Lawyer! 🚀">
                    </div>
                    <button type="submit" class="btn btn-success">📤 Send Test Message</button>
                </form>
                <div id="testMessage" class="message"></div>
            </div>
        </div>
        <script>
            document.getElementById('telegramForm').addEventListener('submit', async function(e) {{
                e.preventDefault();
                const msg = document.getElementById('saveMessage');
                msg.style.display = 'block';
                msg.className = 'message';
                msg.textContent = 'Saving...';
                
                try {{
                    const response = await fetch('/api/config/batch', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            configs: {{
                                telegram: {{
                                    enabled: document.getElementById('enabled').value === 'true',
                                    bot_token: document.getElementById('bot_token').value,
                                    bot_username: document.getElementById('bot_username').value
                                }}
                            }}
                        }})
                    }});
                    const data = await response.json();
                    if (response.ok) {{
                        msg.className = 'message message-success';
                        msg.textContent = '✅ Settings saved successfully!';
                        setTimeout(() => location.reload(), 1500);
                    }} else {{
                        msg.className = 'message message-error';
                        msg.textContent = '❌ Failed to save: ' + (data.message || 'Unknown error');
                    }}
                }} catch(e) {{
                    msg.className = 'message message-error';
                    msg.textContent = '❌ Error: ' + e.message;
                }}
            }});
            
            document.getElementById('testForm').addEventListener('submit', async function(e) {{
                e.preventDefault();
                const msg = document.getElementById('testMessage');
                msg.style.display = 'block';
                msg.className = 'message';
                msg.textContent = 'Sending...';
                
                try {{
                    const response = await fetch('/api/telegram/test', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            chat_id: document.getElementById('test_chat_id').value,
                            message: document.getElementById('test_message').value
                        }})
                    }});
                    const data = await response.json();
                    if (response.ok) {{
                        msg.className = 'message message-success';
                        msg.textContent = '✅ ' + data.message;
                    }} else {{
                        msg.className = 'message message-error';
                        msg.textContent = '❌ ' + data.message;
                    }}
                }} catch(e) {{
                    msg.className = 'message message-error';
                    msg.textContent = '❌ Error: ' + e.message;
                }}
            }});
        </script>
    </body>
    </html>
    """)

# ============================================================
# ADMIN - WHATSAPP SETTINGS
# ============================================================
@app.get("/admin/whatsapp")
async def admin_whatsapp(current_user: User = Depends(get_admin_user)):
    wa = ConfigStore.get_whatsapp()
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>WhatsApp Settings - Pocket Lawyer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }}
        .header {{ background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
        .header h1 {{ color: #60a5fa; }}
        .btn {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; transition: all 0.3s; }}
        .btn-primary {{ background: #3b82f6; color: white; }}
        .btn-primary:hover {{ background: #2563eb; transform: translateY(-2px); }}
        .btn-success {{ background: #10b981; color: white; }}
        .btn-success:hover {{ background: #059669; transform: translateY(-2px); }}
        .btn-secondary {{ background: #334155; color: white; }}
        .btn-secondary:hover {{ background: #475569; transform: translateY(-2px); }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 24px; }}
        .card {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px; }}
        .card h3 {{ color: #f59e0b; margin-bottom: 12px; }}
        .form-group {{ margin-bottom: 16px; }}
        .form-group label {{ color: #94a3b8; display: block; margin-bottom: 4px; font-size: 0.9rem; }}
        .form-group input, .form-group select {{ width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 1rem; }}
        .form-group input:focus, .form-group select:focus {{ border-color: #3b82f6; outline: none; }}
        .status-badge {{ padding: 4px 12px; border-radius: 12px; display: inline-block; font-size: 0.9rem; }}
        .status-on {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
        .status-off {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
        .message {{ padding: 12px; border-radius: 8px; margin-top: 12px; display: none; }}
        .message-success {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
        .message-error {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
    </style>
    </head>
    <body>
        <div class="header">
            <div><h1>💬 WhatsApp Settings</h1></div>
            <div>
                <a href="/admin" class="btn btn-secondary">← Back</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
            </div>
        </div>
        <div class="container">
            <div class="card">
                <h3>📊 Status</h3>
                <p>Status: <span class="status-badge {"status-on" if wa.get("enabled") else "status-off"}">{"🟢 Enabled" if wa.get("enabled") else "🔴 Disabled"}</span></p>
                <p>Phone Number ID: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">{"Configured" if wa.get("phone_number_id") else "Not configured"}</code></p>
                <p>Access Token: <code style="background:#0f172a;padding:2px 8px;border-radius:4px;">{"Configured" if wa.get("access_token") else "Not configured"}</code></p>
            </div>
            <div class="card">
                <h3>🔧 Configuration</h3>
                <form id="whatsappForm">
                    <div class="form-group">
                        <label>Phone Number ID</label>
                        <input type="text" id="phone_number_id" value="{wa.get("phone_number_id", "")}" placeholder="Enter phone number ID">
                    </div>
                    <div class="form-group">
                        <label>Access Token</label>
                        <input type="text" id="access_token" value="{wa.get("access_token", "")}" placeholder="Enter access token">
                    </div>
                    <div class="form-group">
                        <label>Verify Token</label>
                        <input type="text" id="verify_token" value="{wa.get("verify_token", "pocket_lawyer_2024")}" placeholder="Enter verify token">
                    </div>
                    <div class="form-group">
                        <label>Enabled</label>
                        <select id="enabled">
                            <option value="true" {"selected" if wa.get("enabled") else ""}>Yes - Enabled</option>
                            <option value="false" {"selected" if not wa.get("enabled") else ""}>No - Disabled</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">💾 Save Settings</button>
                </form>
                <div id="saveMessage" class="message"></div>
            </div>
            <div class="card">
                <h3>🧪 Test WhatsApp</h3>
                <form id="testForm">
                    <div class="form-group">
                        <label>Phone Number (with country code)</label>
                        <input type="text" id="test_to" placeholder="e.g., 2348012345678" required>
                    </div>
                    <div class="form-group">
                        <label>Message</label>
                        <input type="text" id="test_message" value="Hello from Pocket Lawyer! 🚀">
                    </div>
                    <button type="submit" class="btn btn-success">📤 Send Test Message</button>
                </form>
                <div id="testMessage" class="message"></div>
            </div>
        </div>
        <script>
            document.getElementById('whatsappForm').addEventListener('submit', async function(e) {{
                e.preventDefault();
                const msg = document.getElementById('saveMessage');
                msg.style.display = 'block';
                msg.className = 'message';
                msg.textContent = 'Saving...';
                
                try {{
                    const response = await fetch('/api/config/batch', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            configs: {{
                                whatsapp: {{
                                    enabled: document.getElementById('enabled').value === 'true',
                                    phone_number_id: document.getElementById('phone_number_id').value,
                                    access_token: document.getElementById('access_token').value,
                                    verify_token: document.getElementById('verify_token').value
                                }}
                            }}
                        }})
                    }});
                    const data = await response.json();
                    if (response.ok) {{
                        msg.className = 'message message-success';
                        msg.textContent = '✅ Settings saved successfully!';
                        setTimeout(() => location.reload(), 1500);
                    }} else {{
                        msg.className = 'message message-error';
                        msg.textContent = '❌ Failed to save: ' + (data.message || 'Unknown error');
                    }}
                }} catch(e) {{
                    msg.className = 'message message-error';
                    msg.textContent = '❌ Error: ' + e.message;
                }}
            }});
            
            document.getElementById('testForm').addEventListener('submit', async function(e) {{
                e.preventDefault();
                const msg = document.getElementById('testMessage');
                msg.style.display = 'block';
                msg.className = 'message';
                msg.textContent = 'Sending...';
                
                try {{
                    const response = await fetch('/api/whatsapp/test', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            to: document.getElementById('test_to').value,
                            message: document.getElementById('test_message').value
                        }})
                    }});
                    const data = await response.json();
                    if (response.ok) {{
                        msg.className = 'message message-success';
                        msg.textContent = '✅ ' + data.message;
                    }} else {{
                        msg.className = 'message message-error';
                        msg.textContent = '❌ ' + data.message;
                    }}
                }} catch(e) {{
                    msg.className = 'message message-error';
                    msg.textContent = '❌ Error: ' + e.message;
                }}
            }});
        </script>
    </body>
    </html>
    """)

# ============================================================
# ADMIN - USERS
# ============================================================
@app.get("/admin/users")
async def admin_users(current_user: User = Depends(get_admin_user), db: SessionLocal = Depends(get_db)):
    users = db.query(User).all()
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>User Management - Pocket Lawyer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }
        .header { background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
        .header h1 { color: #60a5fa; }
        .btn { padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }
        .btn-secondary { background: #334155; color: white; }
        .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; font-weight: 600; }
        .badge { padding: 4px 12px; border-radius: 12px; font-size: 0.75rem; display: inline-block; }
        .badge-admin { background: #f59e0b20; color: #f59e0b; border: 1px solid #f59e0b40; }
        .badge-user { background: #3b82f620; color: #60a5fa; border: 1px solid #3b82f640; }
        .badge-active { background: #10b98120; color: #10b981; border: 1px solid #10b98140; }
        .badge-inactive { background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }
        .badge-free { background: #64748b20; color: #94a3b8; border: 1px solid #64748b40; }
        .badge-pro { background: #3b82f620; color: #60a5fa; border: 1px solid #3b82f640; }
        .badge-enterprise { background: #8b5cf620; color: #a78bfa; border: 1px solid #8b5cf640; }
        @media (max-width: 768px) { table { font-size: 0.8rem; } th, td { padding: 8px; } }
    </style>
    </head>
    <body>
        <div class="header"><h1>👥 User Management</h1><div><a href="/admin" class="btn btn-secondary">← Back</a><a href="/" class="btn btn-secondary">🏠 Home</a></div></div>
        <div class="container">
            <table>
                <thead><tr><th>ID</th><th>Username</th><th>Email</th><th>Full Name</th><th>Role</th><th>Status</th><th>Plan</th><th>Phone</th><th>Joined</th></tr></thead>
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
    <head><title>System Logs - Pocket Lawyer</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: 'Courier New', monospace; background: #0f172a; color: #e2e8f0; }
        .header { background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
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
# ADMIN - SETTINGS
# ============================================================
@app.get("/admin/settings")
async def admin_settings(current_user: User = Depends(get_admin_user)):
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Settings - Pocket Lawyer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; }
        .header { background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
        .header h1 { color: #60a5fa; }
        .btn { padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 600; }
        .btn-secondary { background: #334155; color: white; }
        .container { max-width: 800px; margin: 0 auto; padding: 24px; }
        .card { background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px; }
        .card h3 { color: #f59e0b; margin-bottom: 12px; }
        .card p { color: #94a3b8; line-height: 1.6; }
        .form-group { margin-bottom: 16px; }
        .form-group label { color: #94a3b8; display: block; margin-bottom: 4px; font-size: 0.9rem; }
        .form-group input, .form-group textarea { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 1rem; }
        .form-group textarea { min-height: 120px; resize: vertical; }
        .form-group input:focus, .form-group textarea:focus { border-color: #3b82f6; outline: none; }
        .btn-primary { background: #3b82f6; color: white; padding: 10px 24px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
        .btn-primary:hover { background: #2563eb; }
    </style>
    </head>
    <body>
        <div class="header"><h1>⚙️ System Settings</h1><div><a href="/admin" class="btn btn-secondary">← Back</a><a href="/" class="btn btn-secondary">🏠 Home</a></div></div>
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
                <p style="margin-top:8px;color:#94a3b8;font-size:0.9rem;">Stripe: {{ '✅ Enabled' if ConfigStore.get('stripe', {}).get('enabled') else '❌ Disabled' }}</p>
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
# CONFIG BATCH UPDATE
# ============================================================
@app.post("/api/config/batch")
async def update_config(request: Request, current_user: User = Depends(get_admin_user)):
    try:
        data = await request.json()
        configs = data.get("configs", {})
        for key, value in configs.items():
            ConfigStore.set(key, value)
        return {"status": "success", "message": "Configuration updated"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# ============================================================
# WELCOME PAGE - ENHANCED WITH CLICKABLE CASES
# ============================================================
@app.get("/")
async def home():
    brand = ConfigStore.get("brand_name", "Pocket Lawyer")
    cases = ConfigStore.get_legal_cases()
    
    # Build cases HTML with clickable cards
    cases_html = ""
    for case in cases:
        cases_html += f'''
        <div class="case-card" onclick="window.location.href='/chat?q={case["title"]}'">
            <span class="case-icon">{case.get("icon", "⚖️")}</span>
            <div class="case-info">
                <span class="case-title">{case["title"]}</span>
                <span class="case-category">{case.get("category", "Legal")}</span>
            </div>
        </div>
        '''
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>{brand} - Legal AI Assistant</title>
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
        .cases-section .subtitle {{ text-align: center; color: #94a3b8; margin-bottom: 20px; }}
        .cases-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }}
        .case-card {{ background: #1e293b; padding: 16px 20px; border-radius: 10px; border: 1px solid #334155; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: all 0.3s; }}
        .case-card:hover {{ border-color: #60a5fa; transform: translateX(4px); background: #253450; box-shadow: 0 4px 12px rgba(59,130,246,0.2); }}
        .case-icon {{ font-size: 1.8rem; flex-shrink: 0; }}
        .case-info {{ flex: 1; }}
        .case-title {{ color: #e2e8f0; font-size: 0.95rem; font-weight: 500; }}
        .case-category {{ color: #64748b; font-size: 0.75rem; display: block; margin-top: 2px; }}
        .features {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 32px 0; }}
        .feature {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; text-align: center; transition: all 0.3s; }}
        .feature:hover {{ border-color: #60a5fa; transform: translateY(-4px); }}
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
                <p class="subtitle">Click any case to start a conversation with our AI</p>
                <div class="cases-grid">
                    {cases_html}
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>⚖️ {brand} v{VERSION} • General guidance only</p>
            <p style="margin-top:4px;">For specific legal advice, please consult a qualified lawyer</p>
        </div>
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
        .user-info {{ display: flex; align-items: center; gap: 12px; }}
        .quick-actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }}
        .quick-btn {{ padding: 6px 14px; border-radius: 20px; border: 1px solid #334155; background: #1e293b; color: #94a3b8; font-size: 0.8rem; cursor: pointer; transition: all 0.3s; }}
        .quick-btn:hover {{ border-color: #60a5fa; color: #60a5fa; }}
    </style>
    </head>
    <body>
    <div class="header"><h2>⚖️ {brand}</h2><div class="user-info"><span id="userDisplay">👤 Loading...</span><button class="btn" onclick="logout()">Logout</button><a href="/" class="btn">Home</a></div></div>
    <div class="chat-container">
    <div class="quick-actions">
        <button class="quick-btn" onclick="quickSend('Generate a tenancy agreement PDF')">📄 Tenancy Agreement</button>
        <button class="quick-btn" onclick="quickSend('What are tenant rights in Lagos?')">🏠 Tenant Rights</button>
        <button class="quick-btn" onclick="quickSend('Create an NDA')">📝 NDA</button>
        <button class="quick-btn" onclick="quickSend('What is Nigerian contract law?')">⚖️ Contract Law</button>
        <button class="quick-btn" onclick="quickSend('Employment rights in Nigeria')">💼 Employment</button>
        <button class="quick-btn" onclick="quickSend('How to file for divorce?')">💔 Divorce</button>
    </div>
    <div id="chatBox" class="chat-box">
    <div class="message ai"><strong>{brand}</strong><br>Hello! Welcome to Pocket Lawyer! 👋<br>I am your AI legal assistant for Nigerian Law.<br><br>You can:<br>• Ask legal questions<br>• Generate PDF documents<br>• Get legal guidance 24/7<br><br>How can I help you today?</div>
    </div>
    <div class="input-area">
    <input type="text" id="userInput" placeholder="Type your legal question..." onkeypress="if(event.key===13) sendMessage()">
    <button onclick="sendMessage()" id="sendBtn">Send</button>
    </div>
    <div class="disclaimer">General guidance only. Consult a lawyer for legal advice.</div>
    </div>
    <script>
    const token=localStorage.getItem('token');
    if(!token)window.location.href='/auth/login';
    const user=JSON.parse(localStorage.getItem('user')||'{"username":"User"}');
    document.getElementById('userDisplay').textContent='👤 '+user.username;
    const chatBox=document.getElementById('chatBox');
    function addMessage(sender, text, isHTML) {{
        const div=document.createElement('div');
        div.className='message '+sender;
        if(isHTML) div.innerHTML=text; else div.textContent=text;
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
    function quickSend(message) {{
        document.getElementById('userInput').value=message;
        sendMessage();
    }}
    async function sendMessage() {{
        const input=document.getElementById('userInput');
        const message=input.value.trim();
        if(!message) return;
        input.value='';
        addMessage('user', message);
        addTyping();
        document.getElementById('sendBtn').disabled=true;
        try {{
            const res=await fetch('/api/chat', {{
                method:'POST',
                headers:{{'Content-Type':'application/json','Authorization':'Bearer '+localStorage.getItem('token')}},
                body:JSON.stringify({{message:message}})
            }});
            const data=await res.json();
            removeTyping();
            if(data.pdf_url) {{
                addMessage('ai', data.reply + '<br><a href="'+data.pdf_url+'" target="_blank" class="pdf-link">📄 Download PDF</a>', true);
            }} else {{
                addMessage('ai', data.reply || 'No response received');
            }}
        }} catch(e) {{
            removeTyping();
            addMessage('ai', 'Error connecting to server.');
        }}
        document.getElementById('sendBtn').disabled=false;
    }}
    function logout() {{ localStorage.removeItem('token'); localStorage.removeItem('user'); window.location.href='/auth/login'; }}
    const params=new URLSearchParams(window.location.search);
    const q=params.get('q');
    if(q) {{ document.getElementById('userInput').value=q; sendMessage(); }}
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
        .links { text-align: center; margin-top: 16px; color: #94a3b8; }
        .links a { color: #60a5fa; text-decoration: none; }
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
            <div class="form-group"><label>Username or Email</label><input type="text" id="username" required placeholder="Enter your username or email"></div>
            <div class="form-group"><label>Password</label><input type="password" id="password" required placeholder="Enter your password"></div>
            <button type="submit" class="btn" id="loginBtn">Sign In</button>
        </form>
        <div class="links"><p>Don't have an account? <a href="/auth/register">Register</a></p>
        <p style="margin-top:8px;font-size:0.8rem;color:#64748b;">Demo: admin / admin123</p></div>
    </div>
    <script>
    document.getElementById('loginForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn=document.getElementById('loginBtn');
        const errorMsg=document.getElementById('errorMsg');
        const successMsg=document.getElementById('successMsg');
        btn.disabled=true;
        btn.textContent='Logging in...';
        errorMsg.style.display='none';
        successMsg.style.display='none';
        try {
            const response=await fetch('/api/auth/login', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    username:document.getElementById('username').value.trim(),
                    password:document.getElementById('password').value
                })
            });
            const data=await response.json();
            if(response.ok) {
                localStorage.setItem('token',data.access_token);
                localStorage.setItem('user',JSON.stringify(data.user));
                successMsg.textContent='✅ Login successful! Redirecting...';
                successMsg.style.display='block';
                setTimeout(()=>window.location.href='/chat',1000);
            } else {
                errorMsg.textContent='❌ '+(data.message||'Invalid credentials');
                errorMsg.style.display='block';
            }
        } catch(e) {
            errorMsg.textContent='❌ Connection error. Please try again.';
            errorMsg.style.display='block';
        }
        btn.disabled=false;
        btn.textContent='Sign In';
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
        .links { text-align: center; margin-top: 16px; color: #94a3b8; }
        .links a { color: #60a5fa; text-decoration: none; }
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
            <div class="form-group"><label>Full Name</label><input type="text" id="full_name" required placeholder="Enter your full name"></div>
            <div class="form-group"><label>Username</label><input type="text" id="username" required placeholder="Choose a username" minlength="3"></div>
            <div class="form-group"><label>Email</label><input type="email" id="email" required placeholder="Enter your email"></div>
            <div class="form-group"><label>Phone (Optional)</label><input type="tel" id="phone" placeholder="e.g., 2348012345678"></div>
            <div class="form-group"><label>Password</label><input type="password" id="password" required placeholder="Min 6 characters" minlength="6"></div>
            <button type="submit" class="btn" id="registerBtn">Create Account</button>
        </form>
        <div class="links"><p>Already have an account? <a href="/auth/login">Login</a></p></div>
    </div>
    <script>
    document.getElementById('registerForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn=document.getElementById('registerBtn');
        const errorMsg=document.getElementById('errorMsg');
        const successMsg=document.getElementById('successMsg');
        btn.disabled=true;
        btn.textContent='Creating account...';
        errorMsg.style.display='none';
        successMsg.style.display='none';
        try {
            const response=await fetch('/api/auth/register', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    full_name:document.getElementById('full_name').value.trim(),
                    username:document.getElementById('username').value.trim(),
                    email:document.getElementById('email').value.trim(),
                    phone_number:document.getElementById('phone').value.trim(),
                    password:document.getElementById('password').value
                })
            });
            const data=await response.json();
            if(response.ok) {
                localStorage.setItem('token',data.access_token);
                localStorage.setItem('user',JSON.stringify(data.user));
                successMsg.textContent='✅ Account created! Redirecting...';
                successMsg.style.display='block';
                setTimeout(()=>window.location.href='/chat',1000);
            } else {
                errorMsg.textContent='❌ '+(data.message||'Registration failed');
                errorMsg.style.display='block';
            }
        } catch(e) {
            errorMsg.textContent='❌ Connection error. Please try again.';
            errorMsg.style.display='block';
        }
        btn.disabled=false;
        btn.textContent='Create Account';
    });
    </script>
    </body>
    </html>
    """)

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
                    category=case.get("category", "General"),
                    description=case.get("description", ""),
                    order=i,
                    is_active=True
                ))
            db.commit()
            logger.info(f"✅ Seeded {len(ConfigStore.get_legal_cases())} legal cases")
        
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
