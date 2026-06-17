# dependencies.py
# Fungsi-fungsi dependency yang dipakai di banyak endpoint
# Termasuk: verifikasi JWT token dari header Authorization

import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()

# Skema Bearer Token — FastAPI akan otomatis baca header "Authorization: Bearer <token>"
bearer_scheme = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> dict:
    """
    Dependency: validasi JWT token dari header Authorization.
    Kalau token tidak valid / expired → lempar 401.
    Kalau valid → kembalikan payload (berisi user_id, role, nama, dll).
    """
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            os.getenv("JWT_SECRET_KEY"),
            algorithms=[os.getenv("JWT_ALGORITHM", "HS256")]
        )
        return payload

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak valid atau sudah kadaluarsa. Silakan login ulang.",
            headers={"WWW-Authenticate": "Bearer"},
        )