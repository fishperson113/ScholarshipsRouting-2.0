from typing import Optional, Dict, Any
from firebase_admin import auth as firebase_auth, firestore
from services.firestore_svc import save_with_id, get_one_raw
from fastapi import HTTPException, status, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
import os
import jwt
import secrets
from datetime import datetime, timedelta

# Security scheme for Bearer token
security_scheme = HTTPBearer()


# ============================================================================
# Authentication User Model
# ============================================================================

class AuthenticatedUser:
    """Represents an authenticated Firebase user"""
    def __init__(self, uid: str, email: Optional[str], provider: str):
        self.uid = uid
        self.email = email
        self.provider = provider
        self.is_anonymous = provider == "anonymous"


# ============================================================================
# Security Dependencies
# ============================================================================

async def verify_firebase_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme)
) -> AuthenticatedUser:
    """
    Verify Firebase ID token or guest JWT token and return authenticated user.
    Supports both Firebase authentication and temporary guest sessions.
    Raises 401 if token is invalid, expired, or revoked.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # Try to decode as guest JWT token first
    jwt_secret = os.getenv("JWT_SECRET", "change-this-secret-in-production")
    try:
        decoded = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        # Check if it's a guest token
        if decoded.get("provider") == "guest" and decoded.get("uid", "").startswith("guest_"):
            return AuthenticatedUser(
                uid=decoded["uid"],
                email=decoded.get("email"),
                provider="guest"
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Guest session has expired. Please continue as guest again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        # Not a guest token, try Firebase
        pass
    
    # Try Firebase token verification
    try:
        # Verify token with revocation check
        decoded = firebase_auth.verify_id_token(token, check_revoked=True)
        
        uid = decoded.get("uid")
        email = decoded.get("email")
        provider = decoded.get("firebase", {}).get("sign_in_provider", "")
        
        return AuthenticatedUser(uid=uid, email=email, provider=provider)
        
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except firebase_auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        print(f"Token verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_user_ownership(current_user: AuthenticatedUser, target_uid: str) -> None:
    """
    Verify that the authenticated user can only access their own data.
    Raises 403 if user tries to access another user's data.
    """
    if current_user.uid != target_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own data"
        )


async def verify_bot_token(
    turnstile_token: Optional[str] = Header(None, alias="X-Turnstile-Token")
) -> bool:
    """
    Verify Cloudflare Turnstile token to prevent bot access.
    Returns True if valid, raises 403 if missing/invalid.
    """
    turnstile_secret = os.getenv("CLOUDFLARE_TURNSTILE_SECRET")
    
    # Skip check if not configured (dev environment)
    if not turnstile_secret:
        return True
    
    if not turnstile_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bot verification required"
        )
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                json={
                    "secret": turnstile_secret,
                    "response": turnstile_token,
                }
            )
            
            if response.status_code != 200 or not response.json().get("success"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bot verification failed"
                )
            
            return True
            
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot verification service unavailable"
        )
    except Exception as e:
        print(f"Turnstile error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bot verification failed"
        )


# ============================================================================
# User Management Functions
# ============================================================================


def _ensure_user_in_firestore(uid: str, user_doc: Dict[str, Any]) -> None:
    """
    Đảm bảo user tồn tại trong Firestore collection 'users'.
    Nếu chưa có thì tạo mới.
    """
    profile = get_one_raw("users", uid)
    if profile:
        return
    save_with_id("users", uid, user_doc)


def create_guest_session() -> Dict:
    """
    Create a temporary guest session with JWT token.
    Session expires in 24 hours. No database storage.
    """
    # Generate unique guest ID
    guest_id = f"guest_{secrets.token_urlsafe(16)}"
    
    # Get JWT secret from environment or use default (change in production!)
    jwt_secret = os.getenv("JWT_SECRET", "change-this-secret-in-production")
    
    # Create expiration time (24 hours)
    expiration = datetime.utcnow() + timedelta(hours=24)
    
    # Create JWT token
    payload = {
        "uid": guest_id,
        "email": None,
        "display_name": "Guest User",
        "provider": "guest",
        "is_anonymous": True,
        "exp": expiration,
        "iat": datetime.utcnow()
    }
    
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")
    
    return {
        "guest_token": token,
        "uid": guest_id,
        "expires_at": expiration.isoformat(),
        "is_anonymous": True,
        "display_name": "Guest User",
    }


def register_user(
    email: str,
    password: str,
    display_name: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None
) -> Dict:
    """
    Tạo user mới trong Firebase Authentication + lưu vào Firestore collection 'users'.
    extra_fields: chứa các field bổ sung (thông tin cá nhân, học bổng, CV...).
    """
    user = firebase_auth.create_user(
        email=email,
        password=password,
        display_name=display_name,
    )

    user_doc: Dict[str, Any] = {
        "email": email,
        "display_name": display_name,
        "provider": "password",
    }
    if extra_fields:
        user_doc.update(extra_fields)

    save_with_id("users", user.uid, user_doc)

    return {
        "uid": user.uid,
        "email": email,
        "display_name": display_name,
    }


def verify_token(id_token: str) -> Optional[Dict]:
    """
    Xác thực Firebase ID token (FE gửi lên sau khi login).
    Nếu user mới login lần đầu (Google/Email) thì đồng bộ vào Firestore.
    Enhanced with revocation check for better security.
    """
    try:
        # Verify token with revocation check for hardened security
        decoded = firebase_auth.verify_id_token(id_token, check_revoked=True)
    except firebase_auth.InvalidIdTokenError:
        print("Invalid ID token")
        return None
    except firebase_auth.ExpiredIdTokenError:
        print("Expired ID token")
        return None
    except firebase_auth.RevokedIdTokenError:
        print("Revoked ID token")
        return None
    except Exception as e:
        print(f"Token verification error: {str(e)}")
        return None

    uid = decoded["uid"]
    email = decoded.get("email")
    display_name = decoded.get("name") or decoded.get("displayName")
    provider = decoded.get("firebase", {}).get("sign_in_provider")

    user_doc = {
        "email": email,
        "display_name": display_name,
        "provider": provider,
    }

    _ensure_user_in_firestore(uid, user_doc)

    return decoded


# ======================
# Profile Management
# ======================

def get_profile(uid: str) -> Optional[Dict[str, Any]]:
    """
    Lấy profile user từ Firestore.
    """
    return get_one_raw("users", uid)


def update_profile(uid: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cập nhật profile user trong Firestore (merge fields mới vào).
    """
    db = firestore.client()
    ref = db.collection("users").document(uid)

    # chỉ update những field được gửi lên
    ref.set(fields, merge=True)

    return ref.get().to_dict()
