from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from statin_logic import get_statin_recommendation

load_dotenv()  # Load environment variables from .env file for local development

# Define app constants for easy updates
APP_VERSION = "v2.0.0"

logger = logging.getLogger("statin_app")

app = FastAPI(title="Statin Recommendation Service", version=APP_VERSION)


class EvaluationPayload(BaseModel):
    ck_value: float
    transaminase: float
    bilirubin: float
    muscle_symptoms: bool


@app.get("/")
async def root():
    """Provides basic information about the API."""
    return {
        "service": "Statin Recommendation API",
        "version": APP_VERSION,
        "documentation_url": "/docs",
    }


@app.post("/evaluate")
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
