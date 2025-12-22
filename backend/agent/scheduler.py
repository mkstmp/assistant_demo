import asyncio
from datetime import datetime, timezone
import db

async def check_alarms(active_sockets):
    print("Background Scheduler Started (Firestore Mode)", flush=True)
    
    while True:
        try:
            # Firestore returns timezone-aware datetimes (UTC usually).
            # We must compare against timezone-aware 'now'.
            now = datetime.now(timezone.utc)
            
            # 1. Check Alarms
            alarms = await db.get_active_alarms()
            for alarm in alarms:
                alarm_time = alarm["time"]
                
                # Normalize timezones: Ensure both are aware and UTC
                if alarm_time.tzinfo is None:
                    # Fallback if DB has naive time (shouldn't happen with Firestore)
                    alarm_time = alarm_time.replace(tzinfo=timezone.utc)
                else:
                    alarm_time = alarm_time.astimezone(timezone.utc)
                
                if alarm["status"] == "ACTIVE" and alarm_time <= now:
                    print(f"ALARM RINGING: {alarm['label']}", flush=True)
                    await db.update_alarm(alarm["id"], {"status": "RINGING"})
                    
                    for ws in active_sockets:
                        try:
                            await ws.send_json({"type": "notification", "text": f"ALARM: {alarm['label']}"})
                        except: pass

            # 2. Check Timers
            timers = await db.get_active_timers()
            for timer in timers:
                end_time = timer["end_time"]
                
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=timezone.utc)
                else:
                    end_time = end_time.astimezone(timezone.utc)

                if timer["status"] == "ACTIVE" and end_time <= now:
                    print(f"TIMER FINISHED: {timer['label']}", flush=True)
                    await db.update_timer(timer["id"], {"status": "RINGING"})
                    
                    for ws in active_sockets:
                        try:
                            await ws.send_json({"type": "notification", "text": f"TIMER: {timer['label']}"})
                        except: pass

        except Exception as e:
            print(f"Scheduler Error: {e}", flush=True)
            
        await asyncio.sleep(1)
