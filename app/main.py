import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db
from app.routes.accounts import router as accounts_router
from app.routes.ws import router as ws_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from bot.main import start
    asyncio.create_task(start())
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(accounts_router)
app.include_router(ws_router)