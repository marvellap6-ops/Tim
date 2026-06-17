# routers/jadwal.py
# Endpoint CRUD untuk Kelola Jadwal Tayang

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from datetime import date

from app.database import get_db
from app.dependencies import verify_token

router = APIRouter(prefix="/api/jadwal", tags=["Jadwal"])


# ── Pydantic Schema ───────────────────────────────────────

class JadwalCreate(BaseModel):
    film_id: int
    studio_id: int
    tanggal: date
    jam_tayang: str       # format "HH:MM"
    harga_tiket: float

class JadwalUpdate(BaseModel):
    film_id: Optional[int]    = None
    studio_id: Optional[int]  = None
    tanggal: Optional[date]   = None
    jam_tayang: Optional[str] = None
    harga_tiket: Optional[float] = None


# ── GET: Semua jadwal berdasarkan tanggal (+ filter opsional) ──
@router.get("/", summary="Ambil jadwal berdasarkan tanggal")
def get_jadwal(
    tanggal: date,
    film_id:   Optional[int] = None,
    studio_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_token)
):
    # Query dasar
    query = """
        SELECT
            jt.id,
            jt.film_id,
            f.judul           AS judul_film,
            jt.studio_id,
            s.nama_studio,
            jt.tanggal,
            jt.jam_tayang,
            jt.harga_tiket,
            -- Hitung durasi selesai (jam tayang + durasi film)
            ADDTIME(jt.jam_tayang,
                SEC_TO_TIME(f.durasi_menit * 60)
            ) AS jam_selesai
        FROM jadwal_tayang jt
        JOIN film   f ON f.id = jt.film_id
        JOIN studio s ON s.id = jt.studio_id
        WHERE jt.tanggal = :tanggal
    """
    params = {"tanggal": tanggal}

    if film_id:
        query += " AND jt.film_id = :film_id"
        params["film_id"] = film_id

    if studio_id:
        query += " AND jt.studio_id = :studio_id"
        params["studio_id"] = studio_id

    query += " ORDER BY s.nama_studio, jt.jam_tayang"

    hasil = db.execute(text(query), params).fetchall()

    return [
        {
            "id":           row.id,
            "film_id":      row.film_id,
            "judul_film":   row.judul_film,
            "studio_id":    row.studio_id,
            "nama_studio":  row.nama_studio,
            "tanggal":      str(row.tanggal),
            "jam_tayang":   str(row.jam_tayang),
            "jam_selesai":  str(row.jam_selesai) if row.jam_selesai else None,
            "harga_tiket":  float(row.harga_tiket),
        }
        for row in hasil
    ]


# ── GET: Semua film (untuk dropdown Pilih Film) ───────────
@router.get("/film-list", summary="Daftar film untuk dropdown")
def get_film_list(
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_token)
):
    hasil = db.execute(text(
        "SELECT id, judul, durasi_menit FROM film ORDER BY judul"
    )).fetchall()
    return [{"id": r.id, "judul": r.judul, "durasi_menit": r.durasi_menit} for r in hasil]


# ── GET: Semua studio (untuk dropdown Semua Studio) ───────
@router.get("/studio-list", summary="Daftar studio untuk dropdown")
def get_studio_list(
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_token)
):
    hasil = db.execute(text(
        "SELECT id, nama_studio, kapasitas FROM studio ORDER BY nama_studio"
    )).fetchall()
    return [{"id": r.id, "nama_studio": r.nama_studio, "kapasitas": r.kapasitas} for r in hasil]


# ── POST: Tambah jadwal baru ──────────────────────────────
@router.post("/", status_code=status.HTTP_201_CREATED, summary="Tambah jadwal baru")
def tambah_jadwal(
    body: JadwalCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_token)
):
    # Cek apakah studio sudah ada jadwal yang bentrok waktu tayang
    cek = db.execute(text("""
        SELECT jt.id FROM jadwal_tayang jt
        JOIN film f ON f.id = jt.film_id
        WHERE jt.studio_id = :studio_id
          AND jt.tanggal   = :tanggal
          AND (
            -- Jadwal baru mulai di tengah jadwal yang ada
            :jam_tayang BETWEEN jt.jam_tayang
                AND ADDTIME(jt.jam_tayang, SEC_TO_TIME(f.durasi_menit * 60))
          )
    """), {
        "studio_id":  body.studio_id,
        "tanggal":    body.tanggal,
        "jam_tayang": body.jam_tayang,
    }).fetchone()

    if cek:
        raise HTTPException(
            status_code=400,
            detail="Jadwal bentrok dengan jadwal lain di studio ini!"
        )

    db.execute(text("""
        INSERT INTO jadwal_tayang (film_id, studio_id, tanggal, jam_tayang, harga_tiket)
        VALUES (:film_id, :studio_id, :tanggal, :jam_tayang, :harga_tiket)
    """), body.model_dump())
    db.commit()

    return {"message": "Jadwal berhasil ditambahkan"}


# ── DELETE: Hapus jadwal ──────────────────────────────────
@router.delete("/{jadwal_id}", summary="Hapus jadwal")
def hapus_jadwal(
    jadwal_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_token)
):
    # Cek ada tidak
    ada = db.execute(
        text("SELECT id FROM jadwal_tayang WHERE id = :id"),
        {"id": jadwal_id}
    ).fetchone()

    if not ada:
        raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")

    # Cek apakah sudah ada pemesanan untuk jadwal ini
    punya_booking = db.execute(
        text("SELECT id FROM pemesanan WHERE jadwal_id = :id LIMIT 1"),
        {"id": jadwal_id}
    ).fetchone()

    if punya_booking:
        raise HTTPException(
            status_code=400,
            detail="Jadwal tidak bisa dihapus karena sudah ada pemesanan!"
        )

    db.execute(text("DELETE FROM jadwal_tayang WHERE id = :id"), {"id": jadwal_id})
    db.commit()

    return {"message": "Jadwal berhasil dihapus"}