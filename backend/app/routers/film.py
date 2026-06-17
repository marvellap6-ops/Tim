# routers/film.py
# CRUD Film — tambah, edit, hapus, list, upload poster

import os
import uuid
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.dependencies import verify_token

router = APIRouter(prefix="/api/film", tags=["Film"])

# Folder penyimpanan poster (buat otomatis kalau belum ada)
UPLOAD_DIR = "uploads/poster"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Ekstensi yang diizinkan
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}


# ── Helper: simpan file poster ────────────────────────────
def simpan_poster(file: UploadFile) -> str:
    """Simpan file poster ke disk, return URL relatif"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Format file tidak didukung. Gunakan JPG/PNG.")

    # Nama file unik
    nama_file = f"{uuid.uuid4().hex}{ext}"
    path_file  = os.path.join(UPLOAD_DIR, nama_file)

    with open(path_file, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return f"/uploads/poster/{nama_file}"


# ── GET: Daftar semua film ────────────────────────────────
@router.get("/", summary="Daftar semua film")
def get_film_list(
    q: Optional[str] = None,    # search by judul / genre
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token)
):
    query  = "SELECT * FROM film"
    params = {}

    if q:
        query += " WHERE judul LIKE :q OR genre LIKE :q"
        params["q"] = f"%{q}%"

    query += " ORDER BY dibuat_pada DESC"

    hasil = db.execute(text(query), params).fetchall()

    return [
        {
            "id":           r.id,
            "judul":        r.judul,
            "genre":        r.genre,
            "durasi_menit": r.durasi_menit,
            "rating":       r.rating,
            "sinopsis":     r.sinopsis,
            "poster_url":   r.poster_url,
            "status":       r.status,
            # Kode ID display misal MV-1001
            "kode_id":      f"MV-{1000 + r.id}",
        }
        for r in hasil
    ]


# ── POST: Tambah film baru (dengan upload poster) ─────────
@router.post("/", status_code=status.HTTP_201_CREATED, summary="Tambah film baru")
async def tambah_film(
    judul:        str  = Form(...),
    sinopsis:     str  = Form(""),
    durasi_menit: int  = Form(120),
    rating:       str  = Form("SU"),
    genre:        str  = Form(""),
    bahasa:       str  = Form("Indonesia"),
    aktor:        str  = Form(""),
    poster:       Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token)
):
    # Upload poster jika ada
    poster_url = None
    if poster and poster.filename:
        poster_url = simpan_poster(poster)

    db.execute(text("""
        INSERT INTO film (judul, genre, durasi_menit, rating, sinopsis, poster_url, status)
        VALUES (:judul, :genre, :durasi_menit, :rating, :sinopsis, :poster_url, 'segera')
    """), {
        "judul":        judul,
        "genre":        genre,
        "durasi_menit": durasi_menit,
        "rating":       rating,
        "sinopsis":     sinopsis,
        "poster_url":   poster_url,
    })
    db.commit()

    return {"message": "Film berhasil ditambahkan"}


# ── PUT: Update data film ─────────────────────────────────
@router.put("/{film_id}", summary="Update data film")
async def update_film(
    film_id:      int,
    judul:        str  = Form(...),
    sinopsis:     str  = Form(""),
    durasi_menit: int  = Form(120),
    rating:       str  = Form("SU"),
    genre:        str  = Form(""),
    bahasa:       str  = Form("Indonesia"),
    aktor:        str  = Form(""),
    status_film:  str  = Form("segera"),
    poster:       Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token)
):
    # Cek film ada
    film = db.execute(
        text("SELECT * FROM film WHERE id = :id"), {"id": film_id}
    ).fetchone()
    if not film:
        raise HTTPException(status_code=404, detail="Film tidak ditemukan")

    # Poster baru jika diunggah, kalau tidak pakai yang lama
    poster_url = film.poster_url
    if poster and poster.filename:
        # Hapus poster lama dari disk
        if film.poster_url:
            path_lama = film.poster_url.lstrip("/")
            if os.path.exists(path_lama):
                os.remove(path_lama)
        poster_url = simpan_poster(poster)

    db.execute(text("""
        UPDATE film
        SET judul        = :judul,
            genre        = :genre,
            durasi_menit = :durasi_menit,
            rating       = :rating,
            sinopsis     = :sinopsis,
            poster_url   = :poster_url,
            status       = :status
        WHERE id = :id
    """), {
        "id":           film_id,
        "judul":        judul,
        "genre":        genre,
        "durasi_menit": durasi_menit,
        "rating":       rating,
        "sinopsis":     sinopsis,
        "poster_url":   poster_url,
        "status":       status_film,
    })
    db.commit()

    return {"message": "Film berhasil diperbarui"}


# ── DELETE: Hapus film ────────────────────────────────────
@router.delete("/{film_id}", summary="Hapus film")
def hapus_film(
    film_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token)
):
    film = db.execute(
        text("SELECT * FROM film WHERE id = :id"), {"id": film_id}
    ).fetchone()
    if not film:
        raise HTTPException(status_code=404, detail="Film tidak ditemukan")

    # Cek apakah film sedang punya jadwal aktif
    punya_jadwal = db.execute(
        text("SELECT id FROM jadwal_tayang WHERE film_id = :id LIMIT 1"),
        {"id": film_id}
    ).fetchone()
    if punya_jadwal:
        raise HTTPException(
            status_code=400,
            detail="Film tidak bisa dihapus karena masih punya jadwal tayang!"
        )

    # Hapus poster dari disk
    if film.poster_url:
        path_file = film.poster_url.lstrip("/")
        if os.path.exists(path_file):
            os.remove(path_file)

    db.execute(text("DELETE FROM film WHERE id = :id"), {"id": film_id})
    db.commit()

    return {"message": "Film berhasil dihapus"}