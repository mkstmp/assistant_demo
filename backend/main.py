import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Import new DB wrapper (In-Memory)
import db
from agent.client import GeminiAgent
from agent.scheduler import check_alarms

# Track active websockets for notifications
active_sockets = set() # Changed to set for O(1) removals

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Database Initialized (In-Memory)")
    
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

# --- API Endpoints ---

@app.get("/profile")
async def get_profile():
    # Fetch flat profile directly from DB
    raw_profile = await db.get_user_profile()
    
    # Flatten "memories" list into top-level keys for Frontend
    # Raw: {"name": "Mukesh", "memories": [{"key": "color", "value": "red"}]}
    # Flattened: {"name": "Mukesh", "color": "red"}
    
    flat_profile = {k: v for k, v in raw_profile.items() if k != "memories"}
    
    if "memories" in raw_profile:
        for mem in raw_profile["memories"]:
             if "key" in mem and "value" in mem:
                 flat_profile[mem["key"]] = mem["value"]
                 
    return flat_profile

@app.get("/alarms")
async def get_alarms():
    return await db.get_active_alarms()

@app.get("/timers")
async def get_timers():
    return await db.get_active_timers()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# --- WebSocket ---

@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    print("DEBUG: WebSocket /ws/audio hit!", flush=True)
    await websocket.accept()
    print("DEBUG: WebSocket accepted", flush=True)
    active_sockets.add(websocket)
    
    input_queue = asyncio.Queue()  
    output_queue = asyncio.Queue()
    
    client = GeminiAgent(websocket) # Adjusted: GeminiAgent takes websocket, runs internal loop
    # Wait... GeminiAgent in previous code was agent = GeminiAgent(websocket) and await agent.run()
    # But wait, my previous main.py had:
    # client = GeminiClient()
    # gemini_task = asyncio.create_task(client.connect(input_queue, output_queue))
    
    # Let me check my previous main.py again in the diff.
    # Ah, step 1863... wait, step 1966 view_file showed:
    # agent = GeminiAgent(websocket)
    # await agent.run()
    
    # NO! Step 1966 line 99: agent = GeminiAgent(websocket)
    # But before the revert (Step 1966 is the CURRENT file after revert?), I had separate GeminiClient.
    # Step 1853 showed GeminiAgent taking `websocket`? No, GeminiAgent took `client_ws`.
    # Let's stick to what was in Step 1966 which IS the current state.
    
    # Step 1966:
    # agent = GeminiAgent(websocket)
    # await agent.run()
    
    try:
        await client.run()
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        if websocket in active_sockets:
            active_sockets.remove(websocket)
        await client.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)