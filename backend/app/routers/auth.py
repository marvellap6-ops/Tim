# routers/auth.py
# Endpoint autentikasi untuk Karyawan & Manajer

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from passlib.context import CryptContext
from jose import jwt

from app.database import get_db
from app.models import LoginStafRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["Autentikasi"])

# ── Setup bcrypt ─────────────────────────────────────────
# CryptContext mengurus hashing & verifikasi password dengan bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Helper: buat JWT token ───────────────────────────────
def buat_access_token(data: dict) -> str:
    """Buat JWT token dengan masa berlaku dari .env"""
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=int(os.getenv("JWT_EXPIRE_MINUTES", 480))
    )
    payload.update({"exp": expire})
    return jwt.encode(
        payload,
        os.getenv("JWT_SECRET_KEY"),
        algorithm=os.getenv("JWT_ALGORITHM", "HS256")
    )

# ── Endpoint: POST /api/auth/login/staf ─────────────────
@router.post(
    "/login/staf",
    response_model=LoginResponse,
    summary="Login untuk Karyawan dan Manajer"
)
def login_staf(request: LoginStafRequest, db: Session = Depends(get_db)):
    """
    Menerima username & password.
    - Cek user di tabel pengguna_staf
    - Verifikasi password dengan bcrypt
    - Kembalikan JWT token + info role
    """

    # 1. Cari user berdasarkan username di database
    hasil = db.execute(
        text("SELECT * FROM pengguna_staf WHERE username = :username AND is_aktif = 1"),
        {"username": request.username}
    ).fetchone()

    # 2. Jika user tidak ditemukan → tolak (pesan sengaja dibuat umum agar tidak bocor info)
    if not hasil:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah"
        )

    # 3. Verifikasi password yang dikirim dengan hash di database
    if not pwd_context.verify(request.password, hasil.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah"
        )

    # 4. Buat JWT token yang berisi info user
    token_data = {
        "sub": str(hasil.id),      # subject = user ID
        "username": hasil.username,
        "role": hasil.role,
        "nama": hasil.nama,
    }
    token = buat_access_token(token_data)

    # 5. Kembalikan response sukses
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        role=hasil.role,
        nama=hasil.nama,
        user_id=hasil.id
    )