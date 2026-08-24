import hashlib, hmac, os, secrets
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from .models import User

def hash_password(password: str) -> str:
    salt=secrets.token_hex(16); rounds=310_000
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),rounds).hex()
    return f"pbkdf2_sha256${rounds}${salt}${digest}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        _,rounds,salt,digest=encoded.split("$")
        check=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),int(rounds)).hex()
        return hmac.compare_digest(check,digest)
    except ValueError:return False

def current_user(request:Request,db:Session)->User|None:
    user_id=request.session.get("user_id")
    user=db.get(User,user_id) if user_id else None
    if user and not user.active:
        request.session.clear()
        return None
    return user

def require_admin(request:Request,db:Session)->User:
    user=current_user(request,db)
    if not user or user.role!="admin":raise HTTPException(403,"Требуются права администратора")
    return user
