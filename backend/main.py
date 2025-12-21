import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import init_db, get_db
from models import Alarm, Timer, User
from agent.client import GeminiAgent
from agent.scheduler import check_alarms

# Track active websockets for notifications
active_sockets = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    print("Database Initialized")
    
    # Start the background scheduler
    task = asyncio.create_task(check_alarms(active_sockets))
    print("Background Scheduler Started")
    
    yield
    
    # Shutdown
    task.cancel()
    print("Scheduler Stopped")

app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# --- API Endpoints (Updated for new Schema) ---

@app.get("/alarms")
async def get_alarms(db: AsyncSession = Depends(get_db)):
    # FIX: Query based on 'status' instead of 'is_active'
    result = await db.execute(
        select(Alarm)
        .where(Alarm.status.in_(["ACTIVE", "RINGING"]))
        .order_by(Alarm.time)
    )
    return result.scalars().all()

@app.get("/timers")
async def get_timers(db: AsyncSession = Depends(get_db)):
    # FIX: Query based on 'status' instead of 'is_active'
    result = await db.execute(
        select(Timer)
        .where(Timer.status.in_(["ACTIVE", "RINGING"]))
        .order_by(Timer.end_time)
    )
    return result.scalars().all()

@app.get("/profile")
async def get_profile(db: AsyncSession = Depends(get_db)):
    # The relationship with lazy="selectin" will auto-fetch memories
    result = await db.execute(select(User).where(User.id == 1))
    user = result.scalar_one_or_none()
    return user # User object now includes .memories automatically

# --- WebSocket ---

@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_sockets.append(websocket)
    
    agent = GeminiAgent(websocket)
    try:
        await agent.run()
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        if websocket in active_sockets:
            active_sockets.remove(websocket)
        await agent.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)