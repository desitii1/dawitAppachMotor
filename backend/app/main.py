from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.lotteries import router as lotteries_router
from app.api.reservations import router as reservations_router
from app.api.payments import router as payments_router
from app.api.auth import router as auth_router
from app.api.payment_review import router as payment_review_router
from app.api.activities import router as activities_router
from app.api.broadcasts import router as broadcasts_router
from app.api.customers import router as customers_router
from app.api.reports import router as reports_router
from app.security.middleware import AdminSessionMiddleware


app = FastAPI(
    title="DawitAppachMotor Lottery API",
    version="0.1.0",
    description="Shared API for the Telegram bot and private admin dashboard.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AdminSessionMiddleware)

app.include_router(lotteries_router)
app.include_router(reservations_router)
app.include_router(payments_router)
app.include_router(auth_router)
app.include_router(payment_review_router)
app.include_router(activities_router)
app.include_router(broadcasts_router)
app.include_router(customers_router)
app.include_router(reports_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
