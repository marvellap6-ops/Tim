# database.py
# Bertanggung jawab membuat koneksi ke MySQL menggunakan SQLAlchemy

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()  # Baca variabel dari file .env

# Susun URL koneksi database
DATABASE_URL = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    f"?charset=utf8mb4"
)

# Buat engine SQLAlchemy
engine = create_engine(DATABASE_URL, echo=False)

# Session factory — dipakai di setiap endpoint sebagai "koneksi sementara"
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class untuk model ORM (akan dipakai di tahap berikutnya)
class Base(DeclarativeBase):
    pass

# Dependency FastAPI — otomatis buka & tutup sesi database
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()