from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Generator, Optional

import click
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from google.cloud import secretmanager
from pydantic import BaseModel
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.sessions import SessionMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from models import Base, Evaluation, User
from statin_logic import get_statin_recommendation

load_dotenv()  # Load environment variables from .env file for local development

# Define app constants for easy updates
APP_VERSION = "v2.0.0"
COPYRIGHT_HOLDER = "National Cheng Kung University Department of Engineering Science"
DASHBOARD_ITEMS_PER_PAGE = 10
TOOL_RECENT_EVALS_COUNT = 5
SESSION_MAX_AGE_SECONDS = 30 * 60  # 30 minutes


logger = logging.getLogger("statin_app")


def get_secret(secret_id: str, project_id: str, version_id: str = "latest") -> str:
    """Fetches a secret from Google Cloud Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


# --- Environment-based Configuration ---
FLASK_ENV = os.environ.get("FLASK_ENV", "development")

if FLASK_ENV == "production":
    # --- Production (GCP) Configuration ---
    project_id = os.environ.get("GCP_PROJECT")
    if not project_id:
        raise ValueError("GCP_PROJECT environment variable is not set for production.")

    db_user = get_secret("DB_USER", project_id)
    db_pass = get_secret("DB_PASS", project_id)
    db_name = get_secret("DB_NAME", project_id)
    SECRET_KEY = get_secret("FLASK_SECRET_KEY", project_id)

    instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")
    if not instance_connection_name:
        raise ValueError("INSTANCE_CONNECTION_NAME environment variable is not set for production.")
    DATABASE_URI = (
        f"postgresql+psycopg2://{db_user}:{db_pass}@/{db_name}?host=/cloudsql/{instance_connection_name}"
    )
else:
    # --- Development/Local Configuration ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "a-strong-dev-secret-key")
    DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///statin_local.db")


def create_engine_from_uri(uri: str):
    connect_args = {"check_same_thread": False} if uri.startswith("sqlite") else {}
    return create_engine(uri, connect_args=connect_args, pool_pre_ping=True, future=True)


engine = create_engine_from_uri(DATABASE_URI)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

# Ensure tables exist for development setups without migrations.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Statin Recommendation Service", version=APP_VERSION)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=FLASK_ENV == "production",
    max_age=SESSION_MAX_AGE_SECONDS,
)

# --- Rate Limiter Setup ---
limiter = Limiter(key_func=get_remote_address, default_limits=["200/day", "50/hour"])
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

templates = Jinja2Templates(directory=os.environ.get("TEMPLATE_DIR", "templates"))


class EvaluationPayload(BaseModel):
    ck_value: float
    transaminase: float
    bilirubin: float
    muscle_symptoms: bool


@dataclass
class GuestUser:
    id: int = 0
    username: str = "guest"
    full_name: str = "Guest User"
    is_guest: bool = True


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session) -> Optional[User | GuestUser]:
    if request.session.get("is_guest"):
        return GuestUser()

    user_id = request.session.get("user_id")
    if not user_id:
        return None

    return db.get(User, user_id)


def require_user(request: Request, db: Session) -> User | GuestUser:
    user = get_current_user(request, db)
    if not user:
        request.session["login_error"] = "請先登入以存取系統。"
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


class Pagination:
    """Lightweight pagination helper compatible with Flask-SQLAlchemy templates."""

    def __init__(self, items, page: int, per_page: int, total: int):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total

    @property
    def pages(self) -> int:
        if self.per_page == 0:
            return 0
        return max(1, math.ceil(self.total / self.per_page))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def prev_num(self) -> int:
        return max(1, self.page - 1)

    @property
    def next_num(self) -> int:
        return min(self.pages, self.page + 1)

    def iter_pages(self, left_edge=2, left_current=2, right_current=2, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if (
                num <= left_edge
                or (self.page - left_current - 1 < num < self.page + right_current)
                or num > self.pages - right_edge
            ):
                if last + 1 != num:
                    yield None
                yield num
                last = num


def extract_login_error(request: Request) -> Optional[str]:
    return request.session.pop("login_error", None)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    if request.headers.get("accept", "").startswith("text/html"):
        return HTMLResponse(
            "<h1>Too Many Requests</h1><p>Please try again later.</p>",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    return JSONResponse(
        {"success": False, "error": "Too many requests. Please try again later."},
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    )


@app.get("/", include_in_schema=False)
async def home():
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": extract_login_error(request)},
    )


@app.post("/login", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user_stmt = select(User).where(User.username == username)
    user = db.execute(user_stmt).scalar_one_or_none()
    if not user or not user.check_password(password):
        context = {
            "request": request,
            "error": "帳號或密碼錯誤，請再試一次。",
            "username": username,
        }
        return templates.TemplateResponse("login.html", context, status_code=status.HTTP_401_UNAUTHORIZED)

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["is_guest"] = False

    return RedirectResponse(url="/tool", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/guest_login")
async def guest_login(request: Request):
    request.session.clear()
    request.session["is_guest"] = True
    return RedirectResponse(url="/tool", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/tool", response_class=HTMLResponse)
async def tool(request: Request, db: Session = Depends(get_db)):
    try:
        user = require_user(request, db)
    except HTTPException as exc:
        # FastAPI raises HTTPException to trigger redirect.
        if exc.status_code == status.HTTP_303_SEE_OTHER:
            return RedirectResponse(url=exc.headers["Location"], status_code=exc.status_code)
        raise

    recent_evaluations = []
    if not getattr(user, "is_guest", False):
        stmt = (
            select(Evaluation)
            .where(Evaluation.user_id == user.id)
            .order_by(Evaluation.timestamp.desc())
            .limit(TOOL_RECENT_EVALS_COUNT)
        )
        recent_evaluations = list(db.execute(stmt).scalars().all())

    context = {
        "request": request,
        "version": APP_VERSION,
        "copyright": COPYRIGHT_HOLDER,
        "recent_evaluations": recent_evaluations,
        "user": user,
    }
    return templates.TemplateResponse("tool.html", context)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        user = require_user(request, db)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_303_SEE_OTHER:
            return RedirectResponse(url=exc.headers["Location"], status_code=exc.status_code)
        raise

    if getattr(user, "is_guest", False):
        return RedirectResponse(url="/tool", status_code=status.HTTP_303_SEE_OTHER)

    search_query = request.query_params.get("q", "")
    try:
        page = int(request.query_params.get("page", "1"))
    except ValueError:
        page = 1
    page = max(page, 1)

    base_query = db.query(Evaluation).filter(Evaluation.user_id == user.id)
    if search_query:
        base_query = base_query.filter(Evaluation.recommendation.ilike(f"%{search_query}%"))

    total = base_query.count()
    items = (
        base_query.order_by(Evaluation.timestamp.desc())
        .offset((page - 1) * DASHBOARD_ITEMS_PER_PAGE)
        .limit(DASHBOARD_ITEMS_PER_PAGE)
        .all()
    )

    pagination = Pagination(
        items=items,
        page=page,
        per_page=DASHBOARD_ITEMS_PER_PAGE,
        total=total,
    )

    context = {
        "request": request,
        "pagination": pagination,
        "search_query": search_query,
        "user": user,
    }
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/evaluate")
async def evaluate(
    request: Request,
    payload: EvaluationPayload,
    db: Session = Depends(get_db),
):
    try:
        user = require_user(request, db)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_303_SEE_OTHER:
            return JSONResponse(
                {"success": False, "error": "Authentication required."},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        raise

    try:
        recommendation = get_statin_recommendation(
            payload.ck_value,
            payload.transaminase,
            payload.bilirubin,
            payload.muscle_symptoms,
        )

        if not getattr(user, "is_guest", False):
            evaluation = Evaluation(
                user_id=user.id,
                ck_value=payload.ck_value,
                transaminase=payload.transaminase,
                bilirubin=payload.bilirubin,
                muscle_symptoms=payload.muscle_symptoms,
                recommendation=recommendation,
            )
            db.add(evaluation)
            db.commit()
        return {"success": True, "recommendation": recommendation}
    except (ValueError, TypeError):
        return JSONResponse(
            {"success": False, "error": "Invalid input format. Please ensure all values are numbers."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error while saving evaluation: %s", exc)
        return JSONResponse(
            {"success": False, "error": "A database error occurred."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("An unexpected error occurred: %s", exc)
        return JSONResponse(
            {"success": False, "error": "An unexpected error occurred."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# --- CLI Commands ---
@click.group()
def cli():
    """Management commands for the Statin Recommendation service."""


@cli.command("create-user")
@click.argument("username", type=str)
@click.argument("full_name", type=str)
@click.argument("password", type=str)
def create_user(username: str, full_name: str, password: str):
    """Creates a new user account for a physician."""
    with SessionLocal() as db:
        stmt = select(User).where(User.username == username)
        existing_user = db.execute(stmt).scalar_one_or_none()
        if existing_user:
            click.echo(click.style(f"Error: User '{username}' already exists.", fg="red"))
            return
        new_user = User(username=username, full_name=full_name)
        new_user.set_password(password)
        db.add(new_user)
        db.commit()
        click.echo(click.style(f"User '{username}' created successfully.", fg="green"))


@cli.command("list-users")
def list_users():
    """Lists all registered users in the database."""
    with SessionLocal() as db:
        users = db.execute(select(User).order_by(User.id)).scalars().all()
        if not users:
            click.echo("No users found in the database.")
            return

        click.echo(click.style(f"{'ID':<5}{'Username':<20}{'Full Name':<30}", bold=True))
        click.echo("-" * 55)
        for user in users:
            click.echo(f"{user.id:<5}{user.username:<20}{user.full_name:<30}")


@cli.command("update-user")
@click.argument("username")
@click.option("--full-name", help="New full name for the user.")
@click.option("--new-password", help="New password for the user.")
def update_user(username: str, full_name: Optional[str], new_password: Optional[str]):
    """Updates a user's full name or password."""
    if not full_name and not new_password:
        click.echo("Nothing to update. Please provide --full-name or --new-password.")
        return

    with SessionLocal() as db:
        stmt = select(User).where(User.username == username)
        user = db.execute(stmt).scalar_one_or_none()
        if not user:
            click.echo(click.style(f"Error: User '{username}' not found.", fg="red"))
            return

        if full_name:
            user.full_name = full_name
            click.echo(f"Updated full name for '{username}'.")
        if new_password:
            user.set_password(new_password)
            click.echo(f"Updated password for '{username}'.")

        db.commit()
        click.echo(click.style("User updated successfully.", fg="green"))


@cli.command("delete-user")
@click.argument("username")
def delete_user(username: str):
    """Deletes a user and all their associated evaluations."""
    with SessionLocal() as db:
        stmt = select(User).where(User.username == username)
        user = db.execute(stmt).scalar_one_or_none()
        if not user:
            click.echo(click.style(f"Error: User '{username}' not found.", fg="red"))
            return

        if click.confirm(
            click.style(
                f"Are you sure you want to delete user '{username}'? This will also delete all their evaluations.",
                fg="yellow",
            ),
            abort=True,
        ):
            db.delete(user)
            db.commit()
            click.echo(click.style(f"User '{username}' and all their data have been deleted.", fg="green"))


@cli.command("list-evaluations")
@click.option("--username", help="Filter evaluations by a specific username.")
def list_evaluations(username: Optional[str]):
    """Lists all evaluations, optionally filtered by a user."""
    with SessionLocal() as db:
        query = db.query(Evaluation)
        if username:
            stmt = select(User).where(User.username == username)
            user = db.execute(stmt).scalar_one_or_none()
            if not user:
                click.echo(click.style(f"Error: User '{username}' not found.", fg="red"))
                return
            query = query.filter(Evaluation.user_id == user.id)

        evaluations = query.order_by(Evaluation.timestamp.desc()).all()
        if not evaluations:
            click.echo("No evaluations found.")
            return

        click.echo(click.style(f"{'ID':<5}{'User':<15}{'Timestamp':<25}{'Recommendation Snippet'}", bold=True))
        click.echo("-" * 80)
        for evaluation in evaluations:
            snippet = evaluation.recommendation.replace("\n", " ").strip()
            if len(snippet) > 30:
                snippet = snippet[:30] + "..."
            click.echo(
                f"{evaluation.id:<5}"
                f"{evaluation.user.username if evaluation.user else 'N/A':<15}"
                f"{evaluation.timestamp.strftime('%Y-%m-%d %H:%M:%S'):<25}"
                f"{snippet}"
            )


if __name__ == "__main__":
    cli()
