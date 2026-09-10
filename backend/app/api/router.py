from fastapi import APIRouter

from backend.app.api.routes import accounting, auth, expenses, health, ml, reporting, users

api_router = APIRouter()
api_router.include_router(expenses.router, tags=["expenses"])
api_router.include_router(health.router, tags=["system"])
api_router.include_router(auth.router, tags=["authentication"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(accounting.router, tags=["accounting"])
api_router.include_router(reporting.router, tags=["reports"])
api_router.include_router(ml.router, tags=["machine-learning"])
