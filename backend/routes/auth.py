from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from backend.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.db import repo as db
from backend.models.schemas import TokenResponse, UserRegisterRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
def register_user(payload: UserRegisterRequest):
    if db.get_user_by_username(payload.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    role = "admin" if payload.username == "admin" else "user"
    user_id = db.create_user(payload.username, hash_password(payload.password), role=role)
    db.add_audit_log(
        user_id, "user_register", "user", str(user_id), {"username": payload.username}
    )
    return {"success": True, "user_id": user_id, "role": role}


@router.post("/login", response_model=TokenResponse)
def login_user(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    user = db.get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user["username"])
    db.add_audit_log(
        user["id"],
        "user_login",
        "user",
        str(user["id"]),
        {"username": user["username"]},
    )
    return TokenResponse(access_token=token)


@router.get("/me")
def get_me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "daily_quota": user["daily_quota"],
    }

