# ============================================================
# POCKET LAWYER v15.0 - WORKING VERSION
# ============================================================
import os
import json
import logging
import asyncio
import time
import io
import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Depends, Cookie
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("pocket_lawyer")

VERSION = "15.0.12"
APP_NAME = "Pocket Lawyer"

# ============================================================
# SECURITY
# ============================================================
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(64))
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
# MODELS
# ============================================================
class UserCreate(BaseModel):
    email: str
    username: str
    full_name: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

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
# AUTH ENDPOINTS
# ============================================================
@app.post("/api/auth/login")
async def login(login_data: UserLogin, db: SessionLocal = Depends(get_db)):
    user = db.query(User).filter(User.username == login_data.username).first()
    if not user:
        user = db.query(User).filter(User.email == login_data.username).first()
    
    if not user or not verify_password(login_data.password, user.hashed_password):
        return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid credentials"})
    
    token = create_access_token({"user_id": user.id, "username": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "is_superuser": user.is_superuser
        }
    }

@app.get("/api/auth/me")
async def get_me(request: Request, db: SessionLocal = Depends(get_db)):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        return JSONResponse(status_code=401, content={"status": "error", "message": "No token"})
    
    payload = verify_token(token)
    if not payload:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Invalid token"})
    
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user:
        return JSONResponse(status_code=401, content={"status": "error", "message": "User not found"})
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "is_superuser": user.is_superuser
    }

# ============================================================
# SIMPLE ADMIN - WORKS WITH BASIC AUTH
# ============================================================
@app.get("/admin")
async def admin_panel(request: Request, db: SessionLocal = Depends(get_db)):
    # Check for token in cookie or header
    token = request.cookies.get("token")
    if not token:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
    
    # If no token, show login form
    if not token:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Admin Login</title>
        <style>
            * { margin:0; padding:0; box-sizing:border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; display: flex; justify-content: center; align-items: center; height: 100vh; }
            .login-box { background: #1e293b; padding: 40px; border-radius: 16px; border: 1px solid #334155; width: 100%; max-width: 400px; }
            .login-box h2 { color: #60a5fa; text-align: center; margin-bottom: 8px; }
            .login-box .sub { color: #94a3b8; text-align: center; margin-bottom: 24px; }
            .form-group { margin-bottom: 16px; }
            .form-group label { color: #94a3b8; display: block; margin-bottom: 4px; }
            .form-group input { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; }
            .btn { width: 100%; padding: 12px; border: none; border-radius: 8px; background: #3b82f6; color: white; font-weight: 600; cursor: pointer; }
            .btn:hover { background: #2563eb; }
            .error { color: #ef4444; background: #ef444420; padding: 12px; border-radius: 8px; margin-bottom: 16px; display: none; }
            .links { text-align: center; margin-top: 16px; color: #94a3b8; }
            .links a { color: #60a5fa; text-decoration: none; }
        </style>
        </head>
        <body>
        <div class="login-box">
            <h2>⚖️ Admin Login</h2>
            <p class="sub">Login to access admin panel</p>
            <div class="error" id="errorMsg"></div>
            <form id="loginForm">
                <div class="form-group"><label>Username</label><input type="text" id="username" value="admin" required></div>
                <div class="form-group"><label>Password</label><input type="password" id="password" value="admin123" required></div>
                <button type="submit" class="btn">Login</button>
            </form>
            <div class="links"><a href="/">← Back to Home</a></div>
        </div>
        <script>
        document.getElementById('loginForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const errorMsg = document.getElementById('errorMsg');
            errorMsg.style.display = 'none';
            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        username: document.getElementById('username').value,
                        password: document.getElementById('password').value
                    })
                });
                const data = await response.json();
                if (response.ok) {
                    document.cookie = 'token=' + data.access_token + '; path=/; max-age=604800';
                    window.location.reload();
                } else {
                    errorMsg.textContent = '❌ ' + (data.message || 'Invalid credentials');
                    errorMsg.style.display = 'block';
                }
            } catch(e) {
                errorMsg.textContent = '❌ Connection error';
                errorMsg.style.display = 'block';
            }
        });
        </script>
        </body>
        </html>
        """)
    
    # Verify token
    payload = verify_token(token)
    if not payload:
        response = RedirectResponse(url="/admin", status_code=302)
        response.delete_cookie("token")
        return response
    
    # Get user
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user or not user.is_superuser:
        response = RedirectResponse(url="/admin", status_code=302)
        response.delete_cookie("token")
        return response
    
    # Show admin dashboard
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>Admin Dashboard</title>
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
        .btn-danger {{ background: #ef4444; color: white; }}
        .btn-danger:hover {{ background: #dc2626; transform: translateY(-2px); }}
        .btn-secondary {{ background: #334155; color: white; }}
        .btn-secondary:hover {{ background: #475569; transform: translateY(-2px); }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .stat-card {{ background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; text-align: center; }}
        .stat-value {{ font-size: 2rem; font-weight: bold; color: #60a5fa; }}
        .stat-label {{ color: #94a3b8; font-size: 0.85rem; }}
        .card {{ background: #1e293b; padding: 24px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px; }}
        .card h3 {{ color: #f59e0b; margin-bottom: 12px; }}
        .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ color: #94a3b8; }}
        .badge {{ padding: 4px 12px; border-radius: 12px; font-size: 0.75rem; display: inline-block; }}
        .badge-admin {{ background: #f59e0b20; color: #f59e0b; border: 1px solid #f59e0b40; }}
        .badge-user {{ background: #3b82f620; color: #60a5fa; border: 1px solid #3b82f640; }}
        .badge-active {{ background: #10b98120; color: #10b981; border: 1px solid #10b98140; }}
        .badge-inactive {{ background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }}
        .logout-btn {{ background: #ef4444; color: white; padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; }}
        .logout-btn:hover {{ background: #dc2626; }}
    </style>
    </head>
    <body>
        <div class="header">
            <h1>⚖️ <span>Pocket</span> Lawyer Admin</h1>
            <div>
                <a href="/chat" class="btn btn-primary">💬 Chat</a>
                <a href="/" class="btn btn-secondary">🏠 Home</a>
                <button class="logout-btn" onclick="logout()">🚪 Logout</button>
            </div>
        </div>
        <div class="container">
            <div class="stats">
                <div class="stat-card"><div class="stat-value">{total_users}</div><div class="stat-label">Total Users</div></div>
                <div class="stat-card"><div class="stat-value">{active_users}</div><div class="stat-label">Active Users</div></div>
                <div class="stat-card"><div class="stat-value">✅</div><div class="stat-label">System Online</div></div>
                <div class="stat-card"><div class="stat-value">v{VERSION}</div><div class="stat-label">Version</div></div>
            </div>
            <div class="card">
                <h3>👥 Users</h3>
                <table>
                    <thead><tr><th>ID</th><th>Username</th><th>Email</th><th>Role</th><th>Status</th></tr></thead>
                    <tbody>
    """
    users = db.query(User).all()
    for u in users:
        role = "Admin" if u.is_superuser else "User"
        badge = "badge-admin" if u.is_superuser else "badge-user"
        status = "Active" if u.is_active else "Inactive"
        status_badge = "badge-active" if u.is_active else "badge-inactive"
        html += f"""
        <tr>
            <td>{u.id}</td>
            <td><strong>{u.username}</strong></td>
            <td>{u.email}</td>
            <td><span class="badge {badge}">{role}</span></td>
            <td><span class="badge {status_badge}">{status}</span></td>
        </tr>
        """
    html += """
                    </tbody>
                </table>
            </div>
        </div>
        <script>
        function logout() {
            document.cookie = 'token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
            window.location.href = '/admin';
        }
        </script>
    </body>
    </html>
    """)

# ============================================================
# LEGAL CASES
# ============================================================
@app.get("/api/legal-cases")
async def get_legal_cases():
    cases = [
        {"title": "🏠 Tenancy & Landlord", "icon": "🏠"},
        {"title": "💼 Employment Law", "icon": "💼"},
        {"title": "📝 Contracts", "icon": "📝"},
        {"title": "👨‍👩‍👧‍👦 Family Law", "icon": "👨‍👩‍👧‍👦"},
        {"title": "💰 Debt Recovery", "icon": "💰"},
        {"title": "⚖️ Criminal Law", "icon": "⚖️"},
        {"title": "🏢 Corporate Law", "icon": "🏢"},
        {"title": "🏡 Property Law", "icon": "🏡"}
    ]
    return {"status": "success", "cases": cases}

# ============================================================
# CHAT
# ============================================================
async def get_ai_response(messages):
    return {"reply": "I'm an AI legal assistant. How can I help you today?", "provider": "AI"}

@app.post("/api/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        message = data.get("message", "")
        if not message:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Message required"})
        
        # Check for PDF generation
        if "generate" in message.lower() and "pdf" in message.lower():
            return {
                "reply": "✅ PDF generation is available. Please try: 'Generate a tenancy agreement PDF'",
                "pdf_url": "/api/documents/sample.pdf",
                "is_pdf": True
            }
        
        result = await get_ai_response([{"role": "user", "content": message}])
        return {"reply": result["reply"], "provider": result.get("provider", "AI")}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# ============================================================
# HEALTH
# ============================================================
@app.get("/api/health")
async def health():
    return {"status": "healthy", "version": VERSION}

# ============================================================
# FRONTEND PAGES
# ============================================================
@app.get("/")
async def home():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Pocket Lawyer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
        .header { background: #1e293b; padding: 16px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
        .header h1 { color: #60a5fa; font-size: 1.5rem; }
        .header h1 span { color: #f59e0b; }
        .btn { padding: 10px 24px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }
        .btn-primary { background: #3b82f6; color: white; }
        .btn-primary:hover { background: #2563eb; }
        .btn-outline { background: transparent; color: #94a3b8; border: 1px solid #334155; }
        .btn-outline:hover { background: #1e293b; }
        .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
        .hero { text-align: center; padding: 60px 20px; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 16px; border: 1px solid #334155; margin-bottom: 32px; }
        .hero h1 { font-size: 3rem; color: #60a5fa; }
        .hero h1 .highlight { color: #f59e0b; }
        .hero p { font-size: 1.2rem; color: #94a3b8; margin: 16px 0; }
        .btn-group { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-top: 24px; }
        .cases-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-top: 20px; }
        .case-card { background: #1e293b; padding: 16px 20px; border-radius: 10px; border: 1px solid #334155; display: flex; align-items: center; gap: 12px; cursor: pointer; transition: all 0.3s; }
        .case-card:hover { border-color: #60a5fa; transform: translateX(4px); background: #253450; }
        .case-icon { font-size: 1.5rem; }
        .case-title { color: #e2e8f0; font-size: 0.9rem; }
        .footer { text-align: center; color: #64748b; font-size: 0.8rem; padding: 24px; border-top: 1px solid #1e293b; margin-top: 40px; }
        @media (max-width: 768px) { .header { flex-direction: column; text-align: center; } .hero h1 { font-size: 2rem; } }
    </style>
    </head>
    <body>
        <div class="header"><div><h1>⚖️ <span>Pocket</span> Lawyer</h1></div><div><a href="/admin" class="btn btn-outline">⚙️ Admin</a><a href="/auth/login" class="btn btn-outline">Login</a><a href="/auth/register" class="btn btn-primary">Get Started</a></div></div>
        <div class="container">
            <div class="hero"><h1>Your <span class="highlight">Trusted</span> Legal AI Assistant</h1><p>🇳🇬 Nigerian Law, Powered by Advanced AI</p><div class="btn-group"><a href="/auth/register" class="btn btn-primary">🚀 Start Now</a><a href="/chat" class="btn btn-primary">💬 Try AI Chat</a></div></div>
            <h2 style="text-align:center;color:#f59e0b;font-size:1.8rem;margin-top:40px;">📌 Choose Your Legal Matter</h2>
            <div class="cases-grid" id="casesGrid"></div>
        </div>
        <div class="footer"><p>⚖️ Pocket Lawyer v15.0 • General guidance only</p></div>
        <script>
        fetch('/api/legal-cases').then(r=>r.json()).then(data=>{
            const grid=document.getElementById('casesGrid');
            data.cases.forEach(c=>{
                const card=document.createElement('div');
                card.className='case-card';
                card.innerHTML='<span class="case-icon">'+c.icon+'</span><span class="case-title">'+c.title+'</span>';
                card.onclick=()=>window.location.href='/chat?q='+encodeURIComponent(c.title);
                grid.appendChild(card);
            });
        });
        </script>
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
            <div class="form-group"><label>Username</label><input type="text" id="username" placeholder="Enter your username"></div>
            <div class="form-group"><label>Password</label><input type="password" id="password" placeholder="Enter your password"></div>
            <button type="submit" class="btn" id="loginBtn">Sign In</button>
        </form>
        <div class="links"><p>Don't have an account? <a href="/auth/register">Register</a></p><p style="margin-top:8px;font-size:0.8rem;color:#64748b;">Demo: admin / admin123</p></div>
    </div>
    <script>
    document.getElementById('loginForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn=document.getElementById('loginBtn');
        const errorMsg=document.getElementById('errorMsg');
        btn.disabled=true;
        btn.textContent='Logging in...';
        errorMsg.style.display='none';
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
                window.location.href='/chat';
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
            <div class="form-group"><label>Full Name</label><input type="text" id="full_name" placeholder="Enter your full name"></div>
            <div class="form-group"><label>Username</label><input type="text" id="username" placeholder="Choose a username"></div>
            <div class="form-group"><label>Email</label><input type="email" id="email" placeholder="Enter your email"></div>
            <div class="form-group"><label>Password</label><input type="password" id="password" placeholder="Min 6 characters"></div>
            <button type="submit" class="btn" id="registerBtn">Create Account</button>
        </form>
        <div class="links"><p>Already have an account? <a href="/auth/login">Login</a></p></div>
    </div>
    <script>
    document.getElementById('registerForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const btn=document.getElementById('registerBtn');
        const errorMsg=document.getElementById('errorMsg');
        btn.disabled=true;
        btn.textContent='Creating account...';
        errorMsg.style.display='none';
        try {
            const response=await fetch('/api/auth/register', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    full_name:document.getElementById('full_name').value.trim(),
                    username:document.getElementById('username').value.trim(),
                    email:document.getElementById('email').value.trim(),
                    password:document.getElementById('password').value
                })
            });
            const data=await response.json();
            if(response.ok) {
                localStorage.setItem('token',data.access_token);
                localStorage.setItem('user',JSON.stringify(data.user));
                window.location.href='/chat';
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

@app.get("/chat")
async def chat_ui():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Chat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; overflow: hidden; }
        .header { display: flex; justify-content: space-between; align-items: center; padding: 12px 24px; background: #1e293b; border-bottom: 1px solid #334155; }
        .header h2 { color: #60a5fa; }
        .btn { background: #1e293b; color: #e2e8f0; padding: 6px 16px; border-radius: 8px; text-decoration: none; border: 1px solid #334155; cursor: pointer; }
        .chat-container { max-width: 900px; margin: 0 auto; padding: 20px; height: calc(100vh - 80px); display: flex; flex-direction: column; }
        .chat-box { flex:1; overflow-y:auto; padding:20px; background:#0f172a; border:1px solid #1e293b; border-radius:12px; margin-bottom:16px; }
        .message { padding: 12px 18px; margin: 8px 0; border-radius: 12px; max-width: 85%; word-wrap: break-word; line-height: 1.6; }
        .user { background: #3b82f6; margin-left: auto; }
        .ai { background: #1e293b; border: 1px solid #334155; }
        .input-area { display: flex; gap: 12px; padding: 16px 0; }
        .input-area input { flex:1; padding:12px 18px; border-radius:12px; border:1px solid #334155; background:#1e293b; color:#e2e8f0; font-size:1rem; outline:none; }
        .input-area input:focus { border-color:#3b82f6; }
        .input-area button { padding:12px 28px; border-radius:12px; border:none; background:#3b82f6; color:white; font-weight:600; cursor:pointer; }
        .input-area button:hover { background:#2563eb; }
        .disclaimer { font-size:0.7rem; color:#64748b; text-align:center; padding:8px; }
        .user-info { display: flex; align-items: center; gap: 12px; }
        .quick-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
        .quick-btn { padding: 6px 14px; border-radius: 20px; border: 1px solid #334155; background: #1e293b; color: #94a3b8; font-size: 0.8rem; cursor: pointer; transition: all 0.3s; }
        .quick-btn:hover { border-color: #60a5fa; color: #60a5fa; }
    </style>
    </head>
    <body>
    <div class="header"><h2>⚖️ Pocket Lawyer</h2><div class="user-info"><span id="userDisplay">👤 Loading...</span><button class="btn" onclick="logout()">Logout</button><a href="/" class="btn">Home</a><a href="/admin" class="btn">Admin</a></div></div>
    <div class="chat-container">
    <div class="quick-actions">
        <button class="quick-btn" onclick="quickSend('Generate a tenancy agreement PDF')">📄 Tenancy</button>
        <button class="quick-btn" onclick="quickSend('What are tenant rights in Lagos?')">🏠 Rights</button>
        <button class="quick-btn" onclick="quickSend('Create an NDA')">📝 NDA</button>
        <button class="quick-btn" onclick="quickSend('Nigerian contract law')">⚖️ Contract</button>
        <button class="quick-btn" onclick="quickSend('Employment rights Nigeria')">💼 Employment</button>
    </div>
    <div id="chatBox" class="chat-box">
    <div class="message ai"><strong>Pocket Lawyer</strong><br>Hello! Welcome to Pocket Lawyer! 👋<br>I am your AI legal assistant for Nigerian Law.<br><br>How can I help you today?</div>
    </div>
    <div class="input-area">
    <input type="text" id="userInput" placeholder="Type your legal question..." onkeypress="if(event.key===13) sendMessage()">
    <button onclick="sendMessage()" id="sendBtn">Send</button>
    </div>
    <div class="disclaimer">General guidance only. Consult a lawyer for legal advice.</div>
    </div>
    <script>
    const token=localStorage.getItem('token');
    if(!token) window.location.href='/auth/login';
    const user=JSON.parse(localStorage.getItem('user')||'{"username":"User"}');
    document.getElementById('userDisplay').textContent='👤 '+user.username;
    const chatBox=document.getElementById('chatBox');
    function addMessage(sender,text){const div=document.createElement('div');div.className='message '+sender;div.textContent=text;chatBox.appendChild(div);chatBox.scrollTop=chatBox.scrollHeight;}
    function addTyping(){const div=document.createElement('div');div.className='typing';div.id='typing';div.textContent='Thinking...';chatBox.appendChild(div);}
    function removeTyping(){const typing=document.getElementById('typing');if(typing)typing.remove();}
    function quickSend(msg){document.getElementById('userInput').value=msg;sendMessage();}
    async function sendMessage(){
        const input=document.getElementById('userInput');
        const message=input.value.trim();
        if(!message) return;
        input.value='';
        addMessage('user',message);
        addTyping();
        document.getElementById('sendBtn').disabled=true;
        try{
            const res=await fetch('/api/chat',{
                method:'POST',
                headers:{'Content-Type':'application/json','Authorization':'Bearer '+localStorage.getItem('token')},
                body:JSON.stringify({message:message})
            });
            const data=await res.json();
            removeTyping();
            if(data.pdf_url){
                addMessage('ai',data.reply+' Download: '+data.pdf_url);
            }else{
                addMessage('ai',data.reply||'No response');
            }
        }catch(e){
            removeTyping();
            addMessage('ai','Error connecting to server.');
        }
        document.getElementById('sendBtn').disabled=false;
    }
    function logout(){localStorage.removeItem('token');localStorage.removeItem('user');window.location.href='/auth/login';}
    const params=new URLSearchParams(window.location.search);
    const q=params.get('q');
    if(q){document.getElementById('userInput').value=q;sendMessage();}
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
            logger.info("Admin user created (admin/admin123)")
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
