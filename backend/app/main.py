# main.py
# Entry point aplikasi FastAPI

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
# Baris di bawah ini diperbaiki agar meng-import auth DAN dashboard sekaligus
from app.routers import auth, dashboard, jadwal, tiket, film, laporan
import os

app = FastAPI(
    title="API Pemesanan Tiket Bioskop",
    description="Backend sistem pemesanan tiket bioskop",
    version="1.0.0"
)

# ── CORS Pengaturan Gerbang Akses Frontend ──────────────────
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Mengizinkan semua perintah (GET, POST, dll)
    allow_headers=["*"],  # Mengizinkan semua headers info
)

# Serve folder uploads sebagai file statis
# Poster bisa diakses via: http://localhost:8000/uploads/poster/namafile.jpg
os.makedirs("uploads/poster", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ── Daftarkan semua router ────────────────────────────────
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(jadwal.router)
app.include_router(tiket.router)
app.include_router(film.router)
app.include_router(laporan.router)

# ── Health check ─────────────────────────────────────────
@app.get("/", tags=["Root"])
def root():
    return {"message": "API Bioskop berjalan ✅"}