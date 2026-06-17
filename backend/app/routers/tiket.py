# routers/tiket.py
# Endpoint tiket on-site — tanpa perlu pelanggan (walk-in langsung bayar)

import hmac
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.dependencies import verify_token

router = APIRouter(prefix="/api/tiket", tags=["Tiket"])


# ── Schema ────────────────────────────────────────────────

class PesananCreate(BaseModel):
    jadwal_id:    int
    kursi_ids:    List[int]
    metode_bayar: str          # 'cash' atau 'qris'
    uang_diterima: Optional[float] = None   # hanya untuk cash


# ── GET: Jadwal hari ini ──────────────────────────────────
@router.get("/jadwal-hari-ini")
def get_jadwal_hari_ini(
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token)
):
    hasil = db.execute(text("""
        SELECT jt.id, f.judul AS judul_film, f.poster_url,
               s.nama_studio, jt.jam_tayang, jt.harga_tiket,
               jt.tanggal
        FROM jadwal_tayang jt
        JOIN film f   ON f.id = jt.film_id
        JOIN studio s ON s.id = jt.studio_id
        WHERE jt.tanggal = CURDATE()
        ORDER BY jt.jam_tayang, s.nama_studio
    """)).fetchall()

    return [
        {
            "id":          r.id,
            "judul_film":  r.judul_film,
            "poster_url":  r.poster_url,
            "nama_studio": r.nama_studio,
            "jam_tayang":  str(r.jam_tayang)[:5],
            "harga_tiket": float(r.harga_tiket),
            "tanggal":     str(r.tanggal),
        }
        for r in hasil
    ]


# ── GET: Denah kursi jadwal tertentu ─────────────────────
@router.get("/kursi/{jadwal_id}")
def get_kursi(
    jadwal_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token)
):
    jadwal = db.execute(
        text("SELECT studio_id FROM jadwal_tayang WHERE id = :id"),
        {"id": jadwal_id}
    ).fetchone()

    if not jadwal:
        raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")

    hasil = db.execute(text("""
        SELECT
            k.id,
            k.kode_kursi,
            CASE WHEN dp.id IS NOT NULL THEN 'penuh' ELSE 'tersedia' END AS status
        FROM kursi k
        LEFT JOIN detail_pemesanan dp ON dp.kursi_id = k.id
        LEFT JOIN pemesanan p ON p.id = dp.pemesanan_id
            AND p.jadwal_id    = :jadwal_id
            AND p.status_bayar = 'lunas'
        WHERE k.studio_id = :studio_id
        ORDER BY k.kode_kursi
    """), {"jadwal_id": jadwal_id, "studio_id": jadwal.studio_id}).fetchall()

    return [{"id": r.id, "kode_kursi": r.kode_kursi, "status": r.status} for r in hasil]


# ── POST: Buat pesanan + langsung lunas ──────────────────
@router.post("/pesan", status_code=201)
def buat_pesanan(
    body: PesananCreate,
    db: Session = Depends(get_db),
    _: dict = Depends(verify_token)
):
    # 1. Info jadwal
    jadwal = db.execute(text("""
        SELECT jt.harga_tiket, jt.studio_id, jt.tanggal, jt.jam_tayang,
               f.judul, f.poster_url, s.nama_studio
        FROM jadwal_tayang jt
        JOIN film f   ON f.id = jt.film_id
        JOIN studio s ON s.id = jt.studio_id
        WHERE jt.id = :id
    """), {"id": body.jadwal_id}).fetchone()

    if not jadwal:
        raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")

    # 2. Validasi kursi
    for kursi_id in body.kursi_ids:
        kursi_ok = db.execute(text(
            "SELECT id FROM kursi WHERE id = :id AND studio_id = :sid"
        ), {"id": kursi_id, "sid": jadwal.studio_id}).fetchone()
        if not kursi_ok:
            raise HTTPException(status_code=400, detail=f"Kursi tidak valid")

        sudah_dipesan = db.execute(text("""
            SELECT dp.id FROM detail_pemesanan dp
            JOIN pemesanan p ON p.id = dp.pemesanan_id
            WHERE dp.kursi_id = :kid AND p.jadwal_id = :jid AND p.status_bayar = 'lunas'
        """), {"kid": kursi_id, "jid": body.jadwal_id}).fetchone()
        if sudah_dipesan:
            raise HTTPException(status_code=400, detail="Salah satu kursi sudah dipesan!")

    # 3. Hitung total & kembalian
    total         = float(jadwal.harga_tiket) * len(body.kursi_ids)
    uang_diterima = body.uang_diterima or total
    kembalian     = uang_diterima - total if body.metode_bayar == 'cash' else 0

    if body.metode_bayar == 'cash' and uang_diterima < total:
        raise HTTPException(status_code=400, detail="Uang yang diterima kurang dari total tagihan!")

    # 4. Kode booking unik — format OFS-XXXXXXXX
    kode_booking = f"OFS-{uuid.uuid4().hex[:8].upper()}"

    # 5. Gunakan pelanggan_id = 1 sebagai "walk-in" (buat dulu 1 row walk-in di tabel pelanggan)
    # Atau skip FK dengan nilai 0 jika kolom nullable — sesuaikan dengan kebutuhan
    # Di sini kita pakai pelanggan_id nullable (ubah skema jika perlu)
    result = db.execute(text("""
        INSERT INTO pemesanan (pelanggan_id, jadwal_id, kode_booking, total_harga, status_bayar)
        VALUES (:pid, :jid, :kb, :total, 'lunas')
    """), {
        "pid":   None,           # walk-in, tidak perlu akun
        "jid":   body.jadwal_id,
        "kb":    kode_booking,
        "total": total,
    })
    db.flush()
    pemesanan_id = result.lastrowid

    # 6. Insert pembayaran
    db.execute(text("""
        INSERT INTO pembayaran (pemesanan_id, metode, status, dibayar_pada)
        VALUES (:pid, :metode, 'settlement', NOW())
    """), {"pid": pemesanan_id, "metode": body.metode_bayar})

    # 7. Detail tiket per kursi + QR token
    tiket_list = []
    for kursi_id in body.kursi_ids:
        kode_kursi = db.execute(
            text("SELECT kode_kursi FROM kursi WHERE id = :id"), {"id": kursi_id}
        ).fetchone().kode_kursi

        # Generate QR payload
        payload = json.dumps({
            "pemesanan_id": pemesanan_id,
            "kursi_id":     kursi_id,
            "jadwal_id":    body.jadwal_id,
            "kode_booking": kode_booking,
            "ts":           int(datetime.now(timezone.utc).timestamp()),
        }, separators=(',', ':'))

        secret    = os.getenv("JWT_SECRET_KEY", "secret").encode()
        signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
        qr_data   = f"{payload}.{signature}"

        db.execute(text("""
            INSERT INTO detail_pemesanan (pemesanan_id, kursi_id, qr_token)
            VALUES (:pid, :kid, :qr)
        """), {"pid": pemesanan_id, "kid": kursi_id, "qr": qr_data})

        tiket_list.append({"kursi": kode_kursi, "qr_token": qr_data})

    db.commit()

    return {
        "kode_booking":  kode_booking,
        "judul_film":    jadwal.judul,
        "poster_url":    jadwal.poster_url,
        "nama_studio":   jadwal.nama_studio,
        "jam_tayang":    str(jadwal.jam_tayang)[:5],
        "tanggal":       str(jadwal.tanggal),
        "total_harga":   total,
        "uang_diterima": uang_diterima,
        "kembalian":     kembalian,
        "metode_bayar":  body.metode_bayar,
        "tiket":         tiket_list,
    }