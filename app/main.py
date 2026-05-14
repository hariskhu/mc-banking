from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db
from app.routes.account import router as account_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(account_router)