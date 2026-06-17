# models.py
# Berisi Pydantic schema (validasi request & response), BUKAN tabel ORM

from pydantic import BaseModel
from typing import Optional

# ── REQUEST ──────────────────────────────────────────────
class LoginStafRequest(BaseModel):
    """Body yang dikirim saat karyawan/manajer login"""
    username: str
    password: str

# ── RESPONSE ─────────────────────────────────────────────
class LoginResponse(BaseModel):
    """Data yang dikembalikan setelah login sukses"""
    access_token: str
    token_type: str = "bearer"
    role: str
    nama: str
    user_id: int