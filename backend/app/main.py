from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.expenses import router as expenses_router
from app.api.routes.groups import router as groups_router
from app.api.routes.payments import router as payments_router
from app.api.routes.settlements import router as settlements_router
from app.api.routes.webhooks import router as webhooks_router
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(groups_router)
app.include_router(expenses_router)
app.include_router(settlements_router)
app.include_router(payments_router)
app.include_router(webhooks_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
