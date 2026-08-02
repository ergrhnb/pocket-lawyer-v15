# ============================================================
# POCKET LAWYER v15.0 - SIMPLE VERSION
# ============================================================
import os
import json
import logging
import asyncio
import time
import io
import secrets
import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
import httpx
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

# ============================================================
# LOGGING
# ============================================================
os.makedirs('logs', exist_ok=True)
os.makedirs('database', exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("pocket_lawyer")
VERSION = "15.0.7"
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
        "legal_cases": [
            {"title": "Tenancy & Landlord", "icon": "🏠"},
            {"title": "Employment Law", "icon": "💼"},
            {"title": "Contracts", "icon": "📝"},
            {"title": "Family Law", "icon": "👨‍👩‍👧‍👦"},
            {"title": "Debt Recovery", "icon": "💰"},
            {"title": "Criminal Law", "icon": "⚖️"},
            {"title": "Corporate Law", "icon": "🏢"},
            {"title": "Property Law", "icon": "🏡"}
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

# ============================================================
# PDF
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
# AI
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
        reply = await call_provider(provider.get("base_url"), provider.get("api_key"), provider.get("model"), messages)
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

        # PDF generation
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
# HTML PAGES - READING FROM TEMPLATE FILES
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

