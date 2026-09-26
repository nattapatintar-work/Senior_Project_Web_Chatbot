"""
api/schemas.py
==============
Request/response models for the six endpoints in api/app.py. FastAPI validates
requests against these and serialises responses through them, so this file is
the single written-down contract the frontend builds against.

"Ingredient ID" everywhere means the CANONICAL KEY ("chicken", "fish_sauce"),
the same string nlp/extract.py and recommender/recommend.py already use.
"""

from typing import Literal

from pydantic import BaseModel, Field

SESSION_ID_REGEX = r"^[0-9a-f]{32}$"

Stage = Literal["new", "awaiting_confirm", "awaiting_correction", "confirmed"]
Intent = Literal["confirm", "reject", "confirm+correction", "unclear"]


# --- shared ------------------------------------------------------------------

class DetectedItem(BaseModel):
    ingredient: str
    confidence: float
    name_th: str | None = None


# --- POST /detect (request is multipart form, so no request model) -------------

class SkippedImage(BaseModel):
    filename: str
    reason: str


class DetectResponse(BaseModel):
    session_id: str
    detected: list[DetectedItem]
    ingredients: list[str]
    images_processed: int
    images_skipped: list[SkippedImage]
    stage: Stage


# --- POST /extract -------------------------------------------------------------

class ExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, pattern=SESSION_ID_REGEX)


class ExtractResponse(BaseModel):
    session_id: str
    include: list[str]
    exclude: list[str]
    health_tags: list[str]
    ingredients: list[str]
    stage: Stage


# --- POST /confirm -------------------------------------------------------------

class ConfirmRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_REGEX)
    reply: str = Field(min_length=1, max_length=1000)


class Corrections(BaseModel):
    add: list[str] = []
    remove: list[str] = []


class ConfirmResponse(BaseModel):
    session_id: str
    intent: Intent
    corrections: Corrections
    ingredients: list[str]
    stage: Stage


# --- POST /correct ---------------------------------------------------------------

class CorrectRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_REGEX)
    exclude: list[str] = Field(default_factory=list, max_length=100)
    add_text: str | None = Field(default=None, max_length=1000)


class CorrectResponse(BaseModel):
    session_id: str
    removed: list[str]
    added: list[str]
    ingredients: list[str]
    health_tags: list[str]
    stage: Stage


# --- POST /seasoning ---------------------------------------------------------------

class SeasoningRequest(BaseModel):
    session_id: str | None = Field(default=None, pattern=SESSION_ID_REGEX)
    # None (field omitted) = read-only: report the current list and lock state
    # without writing. [] = write an empty list (clears any earlier ticks).
    seasonings: list[str] | None = Field(default=None, max_length=100)


class SeasoningResponse(BaseModel):
    session_id: str
    seasonings: list[str]
    locked: bool


# --- POST /recommend -----------------------------------------------------------------

class RecommendRequest(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_REGEX)
    top_n: int = Field(default=3, ge=1, le=10)


class RecommendedRecipe(BaseModel):
    id: str
    name_th: str
    score: float
    have: list[str]
    missing: list[str]
    seasonings_matched: list[str]
    nutrition: dict[str, float | None]   # passed through as stored in recipes.json
    health_tags: list[str]
    # Display data for the web recipe cards, straight from recipes.json.
    cook_time_min: float | None = None
    recipe_source_url: str | None = None
    main_ingredients: list[str] = []
    seasonings: list[str] = []            # the RECIPE's seasonings (seasonings_matched = the user's ticked subset)


class UsedInputs(BaseModel):
    ingredients: list[str]
    exclude: list[str]
    health_tags: list[str]
    seasonings: list[str]


class RecommendResponse(BaseModel):
    session_id: str
    used: UsedInputs
    recipes: list[RecommendedRecipe]
    count: int
