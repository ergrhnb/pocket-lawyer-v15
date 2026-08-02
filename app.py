# ============================================================
# POCKET LAWYER v15.0 - COMPLETE WITH PAYMENT ENDPOINTS
# ============================================================
import os
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, status, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
import jwt
from dotenv import load_dotenv
import httpx
import stripe
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import fitz
import shutil
import uuid

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")
stripe.api_key = STRIPE_API_KEY

# ============================================================
# DATABASE SETUP
# ============================================================
SQLALCHEMY_DATABASE_URL = "sqlite:///./database/pocket_lawyer.db"
os.makedirs("database", exist_ok=True)
os.makedirs("documents", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs("logs", exist_ok=True)

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============================================================
# MODELS
# ============================================================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    stripe_customer_id = Column(String, nullable=True)
    subscription_status = Column(String, default="free")

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    title = Column(String)
    filename = Column(String)
    filepath = Column(String)
    document_type = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatHistory(Base):
    __tablename__ = "chat_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    message = Column(Text)
    reply = Column(Text)
    provider = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ============================================================
# AUTH SETUP
# ============================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_user(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(lambda: SessionLocal())):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    user = get_user(db, username=username)
    if user is None:
        raise credentials_exception
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_current_admin_user(current_user: User = Depends(get_current_active_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user

# ============================================================
# PYDANTIC SCHEMAS
# ============================================================
class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6)

class ChatRequest(BaseModel):
    message: str

class PaymentRequest(BaseModel):
    amount: float
    currency: str = "ngn"
    description: str

# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(
    title="Pocket Lawyer API",
    version="15.0.2",
    description="Nigerian Legal AI Assistant"
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================================
# AUTH ENDPOINTS
# ============================================================
@app.post("/api/auth/register")
def register(user: UserRegister, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(
        (User.email == user.email) | (User.username == user.username)
    ).first()
    if db_user:
        raise HTTPException(status_code=400, detail="User already registered")
    
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    access_token = create_access_token(data={"sub": user.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": db_user.id,
            "username": db_user.username,
            "email": db_user.email,
            "full_name": db_user.full_name,
            "is_admin": db_user.is_admin
        }
    }

@app.post("/api/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "is_admin": user.is_admin
        }
    }

@app.get("/api/auth/me")
def get_me(current_user: User = Depends(get_current_active_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_admin": current_user.is_admin,
        "subscription_status": current_user.subscription_status
    }

# ============================================================
# HEALTH CHECK
# ============================================================
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "version": "15.0.2",
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================
# CHAT ENDPOINT
# ============================================================
@app.post("/api/chat")
def chat(request: ChatRequest, current_user: Optional[User] = Depends(get_current_active_user)):
    return {
        "reply": f"I'm a Nigerian legal AI assistant. You asked: '{request.message}'. Please set up your AI API keys for full functionality.",
        "provider": "fallback"
    }

# ============================================================
# ✅ PAYMENT ENDPOINTS - FIXED
# ============================================================
@app.get("/api/payment/subscription-plans")
def get_subscription_plans():
    """Get available subscription plans"""
    return {
        "plans": [
            {"id": "free", "name": "Free", "price": 0, "features": ["5 messages/day", "Basic legal info"]},
            {"id": "basic", "name": "Basic", "price": 5000, "features": ["Unlimited messages", "Document generation", "Email support"]},
            {"id": "pro", "name": "Pro", "price": 15000, "features": ["Unlimited messages", "Document generation", "Document analysis", "Priority support", "Contract review"]},
            {"id": "enterprise", "name": "Enterprise", "price": 50000, "features": ["Everything in Pro", "Custom legal documents", "API access", "Dedicated support", "Team accounts"]}
        ]
    }

@app.post("/api/payment/create-payment-intent")
def create_payment_intent(payment: PaymentRequest, current_user: User = Depends(get_current_active_user)):
    """Create a Stripe payment intent"""
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=400, detail="Stripe not configured")
    
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(payment.amount * 100),
            currency=payment.currency.lower(),
            description=payment.description,
            metadata={"user_id": str(current_user.id), "username": current_user.username}
        )
        return {
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id,
            "amount": payment.amount,
            "currency": payment.currency
        }
    except Exception as e:
        logging.error(f"Payment error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# ============================================================
# FRONTEND ROUTES
# ============================================================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return HTMLResponse("""
    <html>
        <head><title>Pocket Lawyer</title></head>
        <body>
            <h1>🇳🇬 Pocket Lawyer v15.0</h1>
            <p>Nigerian Legal AI Assistant</p>
            <p><a href="/api/docs">API Documentation</a></p>
            <p><a href="/admin">Admin Panel</a></p>
        </body>
    </html>
    """)

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, current_user: User = Depends(get_current_admin_user)):
    return HTMLResponse(f"""
    <html>
        <head><title>Admin Dashboard</title></head>
        <body>
            <h1>Admin Dashboard</h1>
            <p>Welcome, {current_user.full_name}!</p>
            <p>User ID: {current_user.id}</p>
            <p>Admin: {current_user.is_admin}</p>
            <hr>
            <h2>Payment Endpoints Available:</h2>
            <ul>
                <li>GET /api/payment/subscription-plans</li>
                <li>POST /api/payment/create-payment-intent</li>
            </ul>
        </body>
    </html>
    """)

# ============================================================
# CREATE ADMIN USER
# ============================================================
@app.on_event("startup")
def create_admin_user():
    db = SessionLocal()
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@example.com",
            full_name="System Administrator",
            hashed_password=get_password_hash("admin123"),
            is_admin=True,
            is_active=True
        )
        db.add(admin)
        db.commit()
        print("✅ Admin user created: admin/admin123")
    db.close()

# ============================================================
# RUN APP
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)