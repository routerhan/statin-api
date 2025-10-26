from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from statin_logic import get_statin_recommendation

load_dotenv()  # Load environment variables from .env file for local development

# Define app constants for easy updates
APP_VERSION = "v2.0.0"

logger = logging.getLogger("statin_app")

app = FastAPI(title="Statin Recommendation Service", version=APP_VERSION)

# --- Add CORS Middleware ---
# This allows the frontend (e.g., your index.html) to make requests
# to the backend from a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)


class EvaluationPayload(BaseModel):
    ck_value: float = Field(..., example=250.5, description="Creatine Kinase (肌酸激酶) 數值, 單位 U/L")
    transaminase: float = Field(..., example=35.0, description="Transaminase (轉氨酶) 數值, 單位 U/L")
    bilirubin: float = Field(..., example=1.2, description="Bilirubin (膽紅素) 數值, 單位 mg/dL")
    muscle_symptoms: bool = Field(..., example=False, description="是否有肌肉相關症狀 (如疼痛、無力)")


class SuccessResponse(BaseModel):
    success: bool = Field(True, description="操作是否成功")
    recommendation: str = Field(
        ...,
        example="CK: Continue statin. Follow up CK in 2–4 weeks...\nLiver: Start statin. Follow-up liver function test in 12 weeks.",
        description="根據輸入數據生成的醫療建議文本",
    )


class ErrorResponse(BaseModel):
    success: bool = Field(False, description="操作是否成功")
    error: str = Field(..., example="Invalid input format.", description="錯誤訊息")


# --- API Endpoints ---
# We define explicit responses for documentation and contract purposes.
# This makes it very clear for the frontend team what to expect.

@app.get("/")
async def root():
    """Provides basic information about the API."""
    return {
        "service": "Statin Recommendation API",
        "version": APP_VERSION,
        "documentation_url": "/docs",
    }


@app.post(
    "/evaluate",
    summary="獲取 Statin 治療建議",
    description="傳入臨床數據，此端點將根據內建醫療邏輯回傳對應的 Statin 藥物使用建議。",
    response_model=SuccessResponse,
    responses={
        status.HTTP_200_OK: {"model": SuccessResponse, "description": "成功取得建議"},
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "輸入資料格式錯誤"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse, "description": "伺服器內部未知錯誤"},
    },
)
async def evaluate(payload: EvaluationPayload):
    try:
        recommendation = get_statin_recommendation(
            payload.ck_value,
            payload.transaminase,
            payload.bilirubin,
            payload.muscle_symptoms,
        )
        return {"success": True, "recommendation": recommendation}
    except (ValueError, TypeError):
        return JSONResponse(
            {"success": False, "error": "Invalid input format. Please ensure all values are numbers."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("An unexpected error occurred: %s", exc)
        return JSONResponse(
            {"success": False, "error": "An unexpected error occurred."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
