# routers/dashboard.py
# Endpoint data untuk Dashboard Karyawan

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.dependencies import verify_token  # akan kita buat

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/karyawan", summary="Data dashboard untuk karyawan")
def get_dashboard_karyawan(
    db: Session = Depends(get_db),
    current_user: dict = Depends(verify_token)
):
    # Pastikan hanya karyawan/manajer yang bisa akses
    if current_user["role"] not in ("karyawan", "manajer"):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    # ── 1. Film yang sedang tayang hari ini ──────────────────
    # Ambil film unik yang punya jadwal tayang = hari ini
    # Sekaligus kumpulkan studio mana saja yang memutar film itu
    film_tayang = db.execute(text("""
        SELECT
            f.id,
            f.judul,
            f.poster_url,
            f.genre,
            f.durasi_menit,
            GROUP_CONCAT(s.nama_studio ORDER BY s.nama_studio SEPARATOR ', ') AS studio_list
        FROM film f
        JOIN jadwal_tayang jt ON jt.film_id = f.id
        JOIN studio s         ON s.id = jt.studio_id
        WHERE jt.tanggal = CURDATE()
        GROUP BY f.id, f.judul, f.poster_url, f.genre, f.durasi_menit
        ORDER BY f.judul
    """)).fetchall()

    # ── 2. Status kapasitas semua studio ─────────────────────
    # Hitung berapa kursi sudah dipesan vs kapasitas studio hari ini
    studio_status = db.execute(text("""
        SELECT
            s.id,
            s.nama_studio,
            s.kapasitas,
            COUNT(dp.id) AS kursi_terpesan
        FROM studio s
        -- Ambil jadwal hari ini untuk studio ini
        LEFT JOIN jadwal_tayang jt ON jt.studio_id = s.id
            AND jt.tanggal = CURDATE()
        -- Hitung tiket yang sudah lunas
        LEFT JOIN pemesanan p ON p.jadwal_id = jt.id
            AND p.status_bayar = 'lunas'
        LEFT JOIN detail_pemesanan dp ON dp.pemesanan_id = p.id
        GROUP BY s.id, s.nama_studio, s.kapasitas
        ORDER BY s.nama_studio
    """)).fetchall()

    # ── 3. Format response ────────────────────────────────────
    return {
        "film_tayang": [
            {
                "id": f.id,
                "judul": f.judul,
                "poster_url": f.poster_url,
                "genre": f.genre,
                "durasi_menit": f.durasi_menit,
                "studio_list": f.studio_list or "-"
            }
            for f in film_tayang
        ],
        "studio_status": [
            {
                "id": s.id,
                "nama_studio": s.nama_studio,
                "kapasitas": s.kapasitas,
                "kursi_terpesan": s.kursi_terpesan or 0,
                # Hitung persentase kepenuhan
                "persentase": round(
                    (s.kursi_terpesan or 0) / s.kapasitas * 100
                ) if s.kapasitas > 0 else 0,
                "sold_out": (s.kursi_terpesan or 0) >= s.kapasitas
            }
            for s in studio_status
        ]
    }