import os
from google.cloud import firestore
from google.api_core.exceptions import NotFound
from datetime import datetime

# Initialize Firestore Client
# Automatically uses GOOGLE_APPLICATION_CREDENTIALS or Cloud Run identity
db = firestore.AsyncClient()

# Collection Names
USERS = "users"
ALARMS = "alarms"
TIMERS = "timers"
MEMORIES = "memories"

# --- USER PROFILE ---
async def get_user_profile(user_id: str = "user_1"):
    """Fetch user profile + memories"""
    user_ref = db.collection(USERS).document(user_id)
    doc = await user_ref.get()
    
    if not doc.exists:
        # Create default user if not exists
        default_data = {
            "id": user_id,
            "name": "User", 
            "city": "Unknown", 
            "timezone": "UTC",
            "gender": "Unknown"
        }
        await user_ref.set(default_data)
        return {**default_data, "memories": []}
    
    user_data = doc.to_dict()
    
    # Fetch memories (Sub-collection)
    memories = []
    async for mem in user_ref.collection(MEMORIES).stream():
        mem_data = mem.to_dict()
        mem_data["key"] = mem.id # Use document ID as key
        memories.append(mem_data)
        
    user_data["memories"] = memories
    return user_data

async def update_user_profile(user_id: str, data: dict):
    user_ref = db.collection(USERS).document(user_id)
    # merge=True updates only the fields provided
    await user_ref.set(data, merge=True)

# --- ALARMS ---
async def create_alarm(data: dict):
    # Data should include 'time' (datetime), 'label', 'status'
    # Firestore usage: .add() returns (update_time, doc_ref)
    await db.collection(ALARMS).add(data)

async def get_active_alarms():
    # Filter for ACTIVE or RINGING
    alarms_ref = db.collection(ALARMS).where("status", "in", ["ACTIVE", "RINGING"])
    
    results = []
    async for doc in alarms_ref.stream():
        data = doc.to_dict()
        data["id"] = doc.id 
        # Firestore datetimes are timezone-aware (UTC usually).
        # We ensure they come back as python datetime objects.
        results.append(data)
    
    # Sort in Python
    results.sort(key=lambda x: x["time"])
    return results

async def update_alarm(alarm_id: str, data: dict):
    ref = db.collection(ALARMS).document(alarm_id)
    await ref.update(data)

async def delete_alarm(alarm_id: str):
    await db.collection(ALARMS).document(alarm_id).delete()

# --- TIMERS ---
async def create_timer(data: dict):
    await db.collection(TIMERS).add(data)

async def get_active_timers():
    ref = db.collection(TIMERS).where("status", "in", ["ACTIVE", "RINGING"])
    results = []
    async for doc in ref.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)
    results.sort(key=lambda x: x["end_time"])
    return results

async def update_timer(timer_id: str, data: dict):
    await db.collection(TIMERS).document(timer_id).update(data)

async def delete_timer(timer_id: str):
    await db.collection(TIMERS).document(timer_id).delete()

# --- MEMORIES ---
async def add_memory(user_id: str, key: str, value: str):
    # Use 'key' as the document ID to prevent duplicates easily
    # Lowercase key for consistency
    safe_key = key.lower().strip().replace(" ", "_")
    ref = db.collection(USERS).document(user_id).collection(MEMORIES).document(safe_key)
    await ref.set({"key": key, "value": value})

async def delete_memory(user_id: str, key: str):
    safe_key = key.lower().strip().replace(" ", "_")
    await db.collection(USERS).document(user_id).collection(MEMORIES).document(safe_key).delete()
