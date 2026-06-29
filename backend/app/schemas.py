from typing import Optional, List
from pydantic import BaseModel, EmailStr


# ---------- Gemini structured output (chat turn) ----------
# Mirrors the schema from the original CLI prototype. This is the contract
# Gemini fills in on every turn so the backend can drive milestones
# (when to render previews, when to lock in the build, etc.) deterministically
# instead of re-parsing free text.
class ChatTurnSchema(BaseModel):
    response_text: str
    detected_body_style: str        # "none" | "car" | "truck" | "suv"
    detected_make: str              # "none" or a brand from inventory
    detected_model: str             # "none" or a model from inventory
    detected_stock_color: str       # "none" or a color
    already_asked_condition: bool
    is_ready_for_finance: bool
    requested_unavailable_vehicle: str  # "none", or the make/model they asked for that we don't carry


# ---------- Auth ----------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    dealer_name: Optional[str] = None  # only used when role == "dealer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    dealer_name: Optional[str] = None
    is_vicimus_client: bool = False
    is_trial_active: bool = False

    class Config:
        from_attributes = True


# ---------- Vehicle options (the actual selectable inventory list) ----------
class VehicleOption(BaseModel):
    option_id: str
    year: int
    make: str
    model: str
    trim: str
    color: str
    price: int
    mileage: int
    condition: str
    image_url: Optional[str] = None


class SelectOptionRequest(BaseModel):
    session_id: str
    option_id: str


# ---------- Chat ----------
class StartSessionRequest(BaseModel):
    location: Optional[str] = None


class SendMessageRequest(BaseModel):
    session_id: str
    message: str


class BuildImage(BaseModel):
    label: str
    url: str


class ChatTurnResponse(BaseModel):
    session_id: Optional[str] = None
    response_text: str
    state: dict
    is_ready_for_finance: bool
    build_images: List[BuildImage] = []
    vehicle_options: List[VehicleOption] = []
    unavailable_vehicle: Optional[str] = None
    geo_blocked: bool = False


# ---------- Notify-me-when-available ----------
class NotifyRequestIn(BaseModel):
    session_id: str
    email: EmailStr
    requested_vehicle: str


class NotifyRequestOut(BaseModel):
    id: str
    requested_vehicle: str

    class Config:
        from_attributes = True


# ---------- Leads ----------
class CreateLeadRequest(BaseModel):
    session_id: str
    is_home_delivery: bool
    funding_strategy: str
    dealer_cross_sell_allowed: bool


class LeadOut(BaseModel):
    id: str
    vehicle_specs: Optional[str]
    dealer_name: Optional[str]
    status: str

    class Config:
        from_attributes = True
