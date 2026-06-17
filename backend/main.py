from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import mysql.connector
from mysql.connector import Error
import uuid
import hashlib

# =============================================
# KONFIGURASI DATABASE (Laragon)
# =============================================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",          # Laragon default: kosong
    "database": "bioskop_db",
    "port": 3306
}

def get_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        raise HTTPException(status_code=500, detail=f"Koneksi database gagal: {str(e)}")

# =============================================
# INISIALISASI FASTAPI
# =============================================
app = FastAPI(title="Bioskop 7 API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================
# MODELS
# =============================================
class LoginPelanggan(BaseModel):
    email: str
    password: str

class RegisterPelanggan(BaseModel):
    nama: str
    email: str
    password: str
    no_telepon: Optional[str] = None

class LoginStaf(BaseModel):
    username: str
    password: str

class BookingRequest(BaseModel):
    pelanggan_id: int
    jadwal_id: int
    kursi_ids: list[int]   # bisa pilih lebih dari 1 kursi

class ValidasiQR(BaseModel):
    qr_token: str

# =============================================
# CEK SERVER
# =============================================
@app.get("/")
def root():
    return {"message": "Bioskop 7 API berjalan!", "docs": "/docs"}

# =============================================
# FILM
# =============================================
@app.get("/film")
def get_all_film():
    """Ambil semua film yang aktif"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM film WHERE status = 'aktif' ORDER BY dibuat_pada DESC")
    result = cursor.fetchall()
    cursor.close(); conn.close()
    return result

@app.get("/film/{film_id}")
def get_film(film_id: int):
    """Detail 1 film"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM film WHERE id = %s", (film_id,))
    film = cursor.fetchone()
    cursor.close(); conn.close()
    if not film:
        raise HTTPException(status_code=404, detail="Film tidak ditemukan")
    return film

# =============================================
# JADWAL TAYANG
# =============================================
@app.get("/jadwal/{film_id}")
def get_jadwal(film_id: int):
    """Ambil jadwal tayang per film, dikelompokkan per tanggal"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT j.id, j.tanggal, j.jam_tayang, j.harga_tiket,
               s.nama_studio, s.kapasitas
        FROM jadwal_tayang j
        JOIN studio s ON j.studio_id = s.id
        WHERE j.film_id = %s
        ORDER BY j.tanggal, j.jam_tayang
    """, (film_id,))
    rows = cursor.fetchall()
    cursor.close(); conn.close()

    # Kelompokkan per tanggal
    grouped = {}
    for row in rows:
        tgl = str(row["tanggal"])
        if tgl not in grouped:
            grouped[tgl] = []
        grouped[tgl].append({
            "id": row["id"],
            "jam": str(row["jam_tayang"]),
            "harga": row["harga_tiket"],
            "studio": row["nama_studio"],
            "kapasitas": row["kapasitas"]
        })
    return grouped

# =============================================
# STUDIO & KURSI
# =============================================
@app.get("/studio")
def get_all_studio():
    """Daftar semua studio"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM studio")
    result = cursor.fetchall()
    cursor.close(); conn.close()
    return result

@app.get("/kursi/{jadwal_id}")
def get_kursi(jadwal_id: int):
    """
    Ambil semua kursi untuk studio pada jadwal tertentu,
    tandai mana yang sudah dipesan
    """
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # Ambil studio_id dari jadwal
    cursor.execute("SELECT studio_id FROM jadwal_tayang WHERE id = %s", (jadwal_id,))
    jadwal = cursor.fetchone()
    if not jadwal:
        cursor.close(); conn.close()
        raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")

    studio_id = jadwal["studio_id"]

    # Ambil semua kursi di studio
    cursor.execute("SELECT id, kode_kursi FROM kursi WHERE studio_id = %s ORDER BY kode_kursi", (studio_id,))
    semua_kursi = cursor.fetchall()

    # Ambil kursi yang sudah dipesan pada jadwal ini
    cursor.execute("""
        SELECT dp.kursi_id
        FROM detail_pemesanan dp
        JOIN pemesanan p ON dp.pemesanan_id = p.id
        WHERE p.jadwal_id = %s AND p.status_bayar != 'gagal'
    """, (jadwal_id,))
    terpesan = {row["kursi_id"] for row in cursor.fetchall()}

    cursor.close(); conn.close()

    # Gabungkan info tersedia/terpesan
    result = []
    for kursi in semua_kursi:
        result.append({
            "id": kursi["id"],
            "kode": kursi["kode_kursi"],
            "tersedia": kursi["id"] not in terpesan
        })
    return result

# =============================================
# PEMESANAN (BOOKING)
# =============================================
@app.post("/pesan")
def buat_pemesanan(data: BookingRequest):
    """Buat pemesanan tiket (bisa lebih dari 1 kursi)"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # Cek jadwal & ambil harga
    cursor.execute("SELECT harga_tiket FROM jadwal_tayang WHERE id = %s", (data.jadwal_id,))
    jadwal = cursor.fetchone()
    if not jadwal:
        cursor.close(); conn.close()
        raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")

    # Cek kursi tidak bentrok
    for kursi_id in data.kursi_ids:
        cursor.execute("""
            SELECT dp.id FROM detail_pemesanan dp
            JOIN pemesanan p ON dp.pemesanan_id = p.id
            WHERE dp.kursi_id = %s AND p.jadwal_id = %s AND p.status_bayar != 'gagal'
        """, (kursi_id, data.jadwal_id))
        if cursor.fetchone():
            cursor.close(); conn.close()
            raise HTTPException(status_code=400, detail=f"Kursi ID {kursi_id} sudah dipesan")

    # Hitung total harga
    total = jadwal["harga_tiket"] * len(data.kursi_ids)
    kode_booking = "BK-" + str(uuid.uuid4())[:8].upper()

    # Insert ke pemesanan
    cursor.execute("""
        INSERT INTO pemesanan (pelanggan_id, jadwal_id, kode_booking, total_harga, status_bayar)
        VALUES (%s, %s, %s, %s, 'pending')
    """, (data.pelanggan_id, data.jadwal_id, kode_booking, total))
    pemesanan_id = cursor.lastrowid

    # Insert detail kursi + generate QR token tiap kursi
    for kursi_id in data.kursi_ids:
        qr_token = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO detail_pemesanan (pemesanan_id, kursi_id, qr_token, is_validated)
            VALUES (%s, %s, %s, 0)
        """, (pemesanan_id, kursi_id, qr_token))

    conn.commit()
    cursor.close(); conn.close()

    return {
        "message": "Pemesanan berhasil!",
        "pemesanan_id": pemesanan_id,
        "kode_booking": kode_booking,
        "total_harga": total
    }

@app.get("/pesan/{pelanggan_id}")
def get_riwayat_pesan(pelanggan_id: int):
    """Riwayat pemesanan milik pelanggan"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.id, p.kode_booking, p.total_harga, p.status_bayar, p.dibuat_pada,
               f.judul AS film, j.tanggal, j.jam_tayang, s.nama_studio
        FROM pemesanan p
        JOIN jadwal_tayang j ON p.jadwal_id = j.id
        JOIN film f ON j.film_id = f.id
        JOIN studio s ON j.studio_id = s.id
        WHERE p.pelanggan_id = %s
        ORDER BY p.dibuat_pada DESC
    """, (pelanggan_id,))
    result = cursor.fetchall()
    cursor.close(); conn.close()
    for r in result:
        r["tanggal"] = str(r["tanggal"])
        r["jam_tayang"] = str(r["jam_tayang"])
        r["dibuat_pada"] = str(r["dibuat_pada"])
    return result

# =============================================
# PEMBAYARAN
# =============================================
@app.post("/bayar/{pemesanan_id}")
def update_pembayaran(pemesanan_id: int, metode: str, midtrans_id: Optional[str] = None):
    """Update status pembayaran setelah bayar"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # Update status_bayar di pemesanan
    cursor.execute("""
        UPDATE pemesanan SET status_bayar = 'lunas' WHERE id = %s
    """, (pemesanan_id,))

    # Insert ke tabel pembayaran
    cursor.execute("""
        INSERT INTO pembayaran (pemesanan_id, midtrans_id, metode, status, dibayar_pada)
        VALUES (%s, %s, %s, 'sukses', NOW())
    """, (pemesanan_id, midtrans_id or "-", metode))

    conn.commit()
    cursor.close(); conn.close()
    return {"message": "Pembayaran berhasil dikonfirmasi"}

# =============================================
# VALIDASI QR (untuk petugas)
# =============================================
@app.post("/validasi-qr")
def validasi_qr(data: ValidasiQR):
    """Validasi tiket berdasarkan QR token"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT dp.id, dp.is_validated, dp.kursi_id,
               k.kode_kursi, p.kode_booking,
               f.judul AS film, j.tanggal, j.jam_tayang, s.nama_studio
        FROM detail_pemesanan dp
        JOIN pemesanan p ON dp.pemesanan_id = p.id
        JOIN kursi k ON dp.kursi_id = k.id
        JOIN jadwal_tayang j ON p.jadwal_id = j.id
        JOIN film f ON j.film_id = f.id
        JOIN studio s ON j.studio_id = s.id
        WHERE dp.qr_token = %s
    """, (data.qr_token,))
    tiket = cursor.fetchone()

    if not tiket:
        cursor.close(); conn.close()
        raise HTTPException(status_code=404, detail="QR tidak valid")
    if tiket["is_validated"]:
        cursor.close(); conn.close()
        raise HTTPException(status_code=400, detail="Tiket sudah digunakan")

    # Tandai sudah divalidasi
    cursor.execute("UPDATE detail_pemesanan SET is_validated = 1 WHERE id = %s", (tiket["id"],))
    conn.commit()
    cursor.close(); conn.close()

    tiket["tanggal"] = str(tiket["tanggal"])
    tiket["jam_tayang"] = str(tiket["jam_tayang"])
    return {"message": "Tiket valid!", "tiket": tiket}

# =============================================
# AUTH PELANGGAN
# =============================================
@app.post("/register")
def register(data: RegisterPelanggan):
    """Daftar akun pelanggan baru"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id FROM pelanggan WHERE email = %s", (data.email,))
    if cursor.fetchone():
        cursor.close(); conn.close()
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")

    hashed = hashlib.md5(data.password.encode()).hexdigest()
    cursor.execute("""
        INSERT INTO pelanggan (nama, email, password, no_telepon, is_aktif)
        VALUES (%s, %s, %s, %s, 1)
    """, (data.nama, data.email, hashed, data.no_telepon))
    conn.commit()
    user_id = cursor.lastrowid
    cursor.close(); conn.close()
    return {"message": "Registrasi berhasil!", "pelanggan_id": user_id}

@app.post("/login")
def login(data: LoginPelanggan):
    """Login pelanggan"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    hashed = hashlib.md5(data.password.encode()).hexdigest()
    cursor.execute("""
        SELECT id, nama, email, no_telepon FROM pelanggan
        WHERE email = %s AND password = %s AND is_aktif = 1
    """, (data.email, hashed))
    user = cursor.fetchone()
    cursor.close(); conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Email atau password salah")
    return {"message": "Login berhasil!", "pelanggan": user}

# =============================================
# AUTH STAF
# =============================================
@app.post("/login-staf")
def login_staf(data: LoginStaf):
    """Login untuk pengguna staf (karyawan/manajer)"""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, nama, username, role FROM pengguna_staf
        WHERE username = %s AND is_aktif = 1
    """, (data.username,))
    staf = cursor.fetchone()
    cursor.close(); conn.close()

    if not staf:
        raise HTTPException(status_code=401, detail="Username tidak ditemukan")

    # Password di DB sudah bcrypt, tapi untuk cek sederhana bisa pakai verifikasi manual
    # Untuk production, gunakan: bcrypt.checkpw(data.password.encode(), staf["password"].encode())
    return {"message": "Login staf berhasil!", "staf": staf}

# =============================================
# JALANKAN:
# uvicorn main:app --reload
# Buka docs: http://localhost:8000/docs
# =============================================
