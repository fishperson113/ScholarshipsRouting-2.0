from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class RegisterRequest(BaseModel):
    # --- Thông tin bắt buộc để đăng nhập ---
    email: EmailStr
    password: str
    display_name: Optional[str] = None

    # --- Thông tin cá nhân (optional) ---
    name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[datetime] = None
    gpa_range_4: Optional[float] = None

    # --- Nguyện vọng về học bổng (optional) ---
    desired_scholarship_type: Optional[List[str]] = None
    desired_countries: Optional[List[str]] = None
    desired_funding_level: Optional[List[str]] = None
    desired_application_mode: Optional[List[str]] = None
    desired_application_month: Optional[int] = None
    desired_field_of_study: Optional[List[str]] = None

    # --- Khác ---
    notes: Optional[str] = None

    # --- Dữ liệu trích xuất từ CV ---
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    language_certificates: Optional[str] = None
    academic_certificates: Optional[str] = None
    academic_awards: Optional[str] = None
    publications: Optional[str] = None

    # --- Kinh nghiệm làm việc ---
    years_of_experience: Optional[float] = None
    total_working_hours: Optional[float] = None

    # --- Thông tin khác từ CV ---
    tags: Optional[List[str]] = None
    special_things: Optional[str] = None

class VerifyRequest(BaseModel):
    id_token: str

class ProfileResponse(BaseModel):
    uid: str
    email: EmailStr
    display_name: Optional[str]
    name: Optional[str]
    gender: Optional[str]
    birth_date: Optional[datetime]
    gpa_range_4: Optional[float]
    desired_scholarship_type: Optional[List[str]]
    desired_countries: Optional[List[str]]
    desired_funding_level: Optional[List[str]]
    desired_application_mode: Optional[List[str]]
    desired_application_month: Optional[int]
    desired_field_of_study: Optional[List[str]]
    notes: Optional[str]
    degree: Optional[str]
    field_of_study: Optional[str]
    language_certificates: Optional[str]
    academic_certificates: Optional[str]
    academic_awards: Optional[str]
    publications: Optional[str]
    years_of_experience: Optional[float]
    total_working_hours: Optional[float]
    tags: Optional[List[str]]
    special_things: Optional[str]

class UpdateProfileRequest(BaseModel):
    # --- Thông tin cá nhân (optional) ---
    name: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[datetime] = None
    gpa_range_4: Optional[float] = None

    # --- Nguyện vọng về học bổng ---
    desired_scholarship_type: Optional[List[str]] = None
    desired_countries: Optional[List[str]] = None
    desired_funding_level: Optional[List[str]] = None
    desired_application_mode: Optional[List[str]] = None
    desired_application_month: Optional[int] = None
    desired_field_of_study: Optional[List[str]] = None

    # --- Khác ---
    notes: Optional[str] = None

    # --- Dữ liệu trích xuất từ CV ---
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    language_certificates: Optional[str] = None
    academic_certificates: Optional[str] = None
    academic_awards: Optional[str] = None
    publications: Optional[str] = None

    # --- Kinh nghiệm làm việc ---
    years_of_experience: Optional[float] = None
    total_working_hours: Optional[float] = None

    # --- Thông tin khác từ CV ---
    tags: Optional[List[str]] = None
    special_things: Optional[str] = None
