import uvicorn
from fastapi import FastAPI
from routers import players, guilds

app = FastAPI()
app.include_router(players.router, prefix="/players")
app.include_router(guilds.router, prefix="/guilds")

@app.get("/")
async def root():
    return {"message": "Hello World"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)