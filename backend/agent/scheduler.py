import asyncio
import datetime
from sqlalchemy import select
from models import Alarm, Timer
from database import AsyncSessionLocal

async def check_alarms(active_websockets):
    """
    Background task to check for expired alarms/timers.
    If an alarm triggers, it sends a message to all connected WebSockets.
    """
    print("Background Scheduler Started")
    while True:
        try:
            now = datetime.datetime.now()
            async with AsyncSessionLocal() as db:
                # Check Alarms
                result = await db.execute(
                    select(Alarm).where(Alarm.status == "ACTIVE", Alarm.time <= now)
                )
                alarms = result.scalars().all()

                for alarm in alarms:
                    print(f"ALARM TRIGGERED: {alarm.label}")
                    alarm.status = "RINGING"
                    alarm.triggered = True
                    # alarm.is_active = False # Keep it technically active so we can Query it? Or rely on status
                    
                    # Notify all connected clients
                    print(f"Notifying {len(active_websockets)} clients")
                    for ws in list(active_websockets): # Send to copy to act safely
                        try:
                            await ws.send_json({
                                "type": "notification",
                                "text": f"ALARM RINGING: {alarm.label}"
                            })
                        except Exception as e:
                            print(f"Warning: Failed to notify client: {e}")

                # Check Timers (similar logic)
                result = await db.execute(
                    select(Timer).where(Timer.status == "ACTIVE", Timer.end_time <= now)
                )
                timers = result.scalars().all()
                for timer in timers:
                    print(f"TIMER FINISHED: {timer.label}")
                    timer.status = "RINGING"
                    timer.triggered = True
                    # timer.is_active = False 
                    for ws in list(active_websockets):
                        try:
                            await ws.send_json({"type": "notification", "text": "TIMER FINISHED!"})
                        except Exception as e:
                            print(f"Warning: Failed to notify client: {e}")
                
                if alarms or timers:
                    await db.commit()

        except Exception as e:
            print(f"Scheduler Error: {e}")
            
        await asyncio.sleep(1) # Poll every second
