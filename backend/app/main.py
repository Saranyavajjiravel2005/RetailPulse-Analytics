from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from app.config import settings
from app.routers import api_router
from app.middleware.error_handler import (
    retailpulse_exception_handler,
    validation_exception_handler,
    sqlalchemy_exception_handler,
    value_error_handler,
    generic_exception_handler,
    RetailPulseException,
)
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
import asyncio
import subprocess
from contextlib import asynccontextmanager

from app.services.scheduler import scheduler

def run_migrations():
    alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    try:
        subprocess.run(["alembic", "-c", str(alembic_ini), "upgrade", "head"], check=True, capture_output=True)
    except Exception:
        pass

async def init_db():
    from app.database import engine, Base
    import app.models  # noqa: F401
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        print(f"init_db error: {e}")

async def seed_default_admin():
    """Ensure a default admin user always exists so login never breaks."""
    from app.database import SessionLocal
    from app.models.user import User, UserRole, UserStatus
    from app.models.company import Company
    from app.utils.security import hash_password
    from sqlalchemy import select

    DEFAULT_EMAIL = "Abisaran@gmail.com"
    DEFAULT_PASSWORD = "12345678"
    DEFAULT_NAME = "Abisaran"

    try:
        async with SessionLocal() as session:
            # Check if user already exists
            result = await session.execute(select(User).where(User.email == DEFAULT_EMAIL))
            existing_user = result.scalar_one_or_none()

            if existing_user:
                # User exists — reset password to make sure it always works
                existing_user.password = hash_password(DEFAULT_PASSWORD)
                existing_user.status = UserStatus.ACTIVE
                session.add(existing_user)
                await session.commit()
                print(f"Default admin user '{DEFAULT_EMAIL}' password reset successfully.")
                return

            # Check if any company exists, if not create one
            company_result = await session.execute(select(Company).limit(1))
            company = company_result.scalar_one_or_none()

            if not company:
                company = Company(
                    name="RetailPulse Demo",
                    industry="Retail",
                    email="admin@retailpulse.com",
                    address="123 Main Street",
                    phone="000-000-0000",
                )
                session.add(company)
                await session.commit()
                await session.refresh(company)
                print("Created default company: RetailPulse Demo")

            # Create admin user
            user = User(
                company_id=company.id,
                name=DEFAULT_NAME,
                email=DEFAULT_EMAIL,
                password=hash_password(DEFAULT_PASSWORD),
                role=UserRole.COMPANY_ADMIN,
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            await session.commit()
            print(f"Created default admin user: {DEFAULT_EMAIL} / {DEFAULT_PASSWORD}")
    except Exception as e:
        print(f"seed_default_admin error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(run_migrations)
    await init_db()
    await seed_default_admin()
    if not scheduler.running:
        scheduler.start()
    try:
        yield
    finally:
        if scheduler.running:
            try:
                scheduler.shutdown(wait=False)
            except Exception:
                pass

def create_app() -> FastAPI:
    application = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan)

    application.add_exception_handler(RetailPulseException, retailpulse_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    application.add_exception_handler(ValueError, value_error_handler)
    application.add_exception_handler(Exception, generic_exception_handler)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    application.include_router(api_router)

    @application.get("/health")
    async def health():
        return {"status": "ok"}

    return application

app = create_app()

