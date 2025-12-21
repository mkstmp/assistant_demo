from pydantic import BaseModel
from typing import Optional
from database import AsyncSessionLocal
from models import Alarm, Timer, User, UserMemory
from sqlalchemy import select, delete
from datetime import datetime, timedelta, time
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import re

# --- Helper Functions (Time Parsing) ---

def parse_time_string(time_str: str, user_timezone: str = None) -> datetime:
    """Parses natural language time string into a future datetime object."""
    tz = None
    if user_timezone:
        try:
            tz = ZoneInfo(user_timezone)
        except Exception as e:
            print(f"Warning: Could not load timezone {user_timezone}: {e}")
    
    now = datetime.now(tz) if tz else datetime.now()
    target_date = now.date()
    target_time = None
    time_str = time_str.lower().strip()

    if "tomorrow" in time_str:
        target_date += timedelta(days=1)
        time_str = time_str.replace("tomorrow", "").strip()

    if time_str in ["noon", "midday"]:
        target_time = time(12, 0)
    elif time_str in ["midnight"]:
        target_time = time(0, 0)
        if target_date == now.date(): target_date += timedelta(days=1)
    
    elif not target_time:
        match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?', time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            meridiem = match.group(3)
            if meridiem:
                if "p" in meridiem and hour < 12: hour += 12
                elif "a" in meridiem and hour == 12: hour = 0
            try:
                target_time = time(hour, minute)
            except ValueError:
                raise ValueError(f"Invalid time format: {time_str}")

    if target_time:
        final_dt_naive = datetime.combine(target_date, target_time)
        if tz:
             final_dt = final_dt_naive.replace(tzinfo=tz)
             if final_dt < now and "tomorrow" not in time_str:
                 final_dt += timedelta(days=1)
             return final_dt.astimezone(None).replace(tzinfo=None)
        else:
             final_dt = final_dt_naive
             if final_dt < now and "tomorrow" not in time_str:
                 final_dt += timedelta(days=1)
             return final_dt
    
    raise ValueError(f"Could not parse time: {time_str}")

def parse_duration_string(duration_str: str) -> int:
    """Parses natural language duration string into seconds."""
    duration_str = duration_str.lower().strip()
    total_seconds = 0
    parts = re.findall(r'(\d+)\s*([a-z]+)', duration_str)
    
    for value, unit in parts:
        val = int(value)
        if 'hour' in unit or unit == 'h': total_seconds += val * 3600
        elif 'minute' in unit or 'min' in unit or unit == 'm': total_seconds += val * 60
        elif 'second' in unit or 'sec' in unit or unit == 's': total_seconds += val
            
    if total_seconds == 0:
        try:
            return int(duration_str)
        except ValueError:
            pass
        raise ValueError(f"Could not parse duration: {duration_str}")
    return total_seconds

# --- Logic Handlers ---

async def _find_alarm(db, args):
    """Helper to find an alarm by ID, or fuzzy match by Time/Label."""
    if args.get("alarm_id"):
        result = await db.execute(select(Alarm).where(Alarm.id == args["alarm_id"]))
        return result.scalar_one_or_none()

    if args.get("time"):
        try:
            target_time = parse_time_string(args["time"])
            query = select(Alarm).where(Alarm.status.in_(["ACTIVE", "RINGING"]), Alarm.time == target_time)
            result = await db.execute(query)
            if match := result.scalars().first(): return match
        except: pass

    if args.get("label"):
        query = select(Alarm).where(Alarm.status.in_(["ACTIVE", "RINGING"]), Alarm.label.ilike(f"%{args['label']}%"))
        result = await db.execute(query)
        return result.scalars().first()
    
    # Fallback: Return single active alarm IF it exists.
    # Note: We handled the "Stop" safety check in the handle_logic function, 
    # so this fallback is safe for 'read' or 'update' actions.
    res = await db.execute(select(Alarm).where(Alarm.status.in_(["ACTIVE", "RINGING"])))
    all_alarms = res.scalars().all()
    if len(all_alarms) == 1:
        return all_alarms[0]

    return None

async def _find_timer(db, args):
    if args.get("timer_id"):
        result = await db.execute(select(Timer).where(Timer.id == args["timer_id"]))
        return result.scalar_one_or_none()
    
    if args.get("label"):
        query = select(Timer).where(Timer.status.in_(["ACTIVE", "RINGING"]), Timer.label.ilike(f"%{args['label']}%"))
        result = await db.execute(query)
        return result.scalars().first()
        
    res = await db.execute(select(Timer).where(Timer.status.in_(["ACTIVE", "RINGING"])))
    all_timers = res.scalars().all()
    if len(all_timers) == 1:
        return all_timers[0]
    return None

async def handle_alarm_logic(action: str, args: dict):
    async with AsyncSessionLocal() as db:
        if action == "create":
            time_str = args.get("time")
            if not time_str: return "Error: Time required."
            try:
                result = await db.execute(select(User).where(User.id == 1))
                user = result.scalar_one_or_none()
                tz = user.timezone if user else None
                alarm_time = parse_time_string(time_str, tz)
                new_alarm = Alarm(time=alarm_time, label=args.get("label", "Alarm"), status="ACTIVE")
                db.add(new_alarm)
                await db.commit()
                return f"Alarm set for {alarm_time.strftime('%H:%M')}."
            except ValueError as e: return f"Error: {e}"

        elif action == "read":
            query = select(Alarm).where(Alarm.status.in_(["ACTIVE", "RINGING"])).order_by(Alarm.time)
            result = await db.execute(query)
            alarms = result.scalars().all()
            if not alarms: return "No active alarms."
            report = "Alarms:\n"
            for a in alarms:
                status = " (RINGING!)" if a.status == "RINGING" else ""
                report += f"- {a.time.strftime('%H:%M')} {a.label}{status}\n"
            return report

        elif action == "delete":
            # SAFE DELETE LOGIC:
            # 1. If NO specific criteria (time/label/id) is provided (Generic "Stop"):
            #    We ONLY target RINGING alarms. We do NOT touch silent active ones.
            has_specs = bool(args.get("time") or args.get("label") or args.get("alarm_id"))
            
            if not has_specs:
                # Look for RINGING alarms only
                res = await db.execute(select(Alarm).where(Alarm.status == "RINGING"))
                ringing = res.scalars().all()
                if ringing:
                    for a in ringing: await db.delete(a)
                    await db.commit()
                    return f"Stopped {len(ringing)} ringing alarm(s)."
                else:
                    # If nothing is ringing and no specs, DO NOT delete silent alarms.
                    return "No ringing alarms found. To cancel a future alarm, please specify the time."

            # 2. If specs provided, find specific alarm
            target_alarm = await _find_alarm(db, args)
            if not target_alarm: return "Could not find that alarm."
            
            await db.delete(target_alarm)
            await db.commit()
            return f"Alarm for {target_alarm.time.strftime('%H:%M')} cancelled."
            
        elif action == "update":
            target_alarm = await _find_alarm(db, args)
            if not target_alarm: return "Alarm not found."
            if args.get("new_time"):
                try:
                    target_alarm.time = parse_time_string(args.get("new_time"))
                except ValueError as e: return f"Invalid time: {e}"
            if args.get("label"): target_alarm.label = args.get("label")
            await db.commit()
            return "Alarm updated."

    return "Unknown action."

async def handle_timer_logic(action: str, args: dict):
    async with AsyncSessionLocal() as db:
        if action == "create":
            if not args.get("duration"): return "Duration required."
            try:
                sec = parse_duration_string(args.get("duration"))
                end = datetime.now() + timedelta(seconds=sec)
                db.add(Timer(duration_seconds=sec, end_time=end, label=args.get("label", "Timer"), status="ACTIVE"))
                await db.commit()
                return f"Timer set for {sec}s."
            except ValueError as e: return f"Error: {e}"

        elif action == "read":
            now = datetime.now()
            query = select(Timer).where(Timer.status.in_(["ACTIVE", "RINGING"])).order_by(Timer.end_time)
            result = await db.execute(query)
            timers = result.scalars().all()
            if not timers: return "No active timers."
            report = "Timers:\n"
            for t in timers:
                if t.status == "RINGING": report += f"- {t.label}: RINGING!\n"
                else: report += f"- {t.label}: {max(0, int((t.end_time - now).total_seconds()))}s remaining\n"
            return report

        elif action == "delete":
            # SAFE DELETE LOGIC (Same as Alarm)
            has_specs = bool(args.get("label") or args.get("timer_id"))
            
            if not has_specs:
                res = await db.execute(select(Timer).where(Timer.status == "RINGING"))
                ringing = res.scalars().all()
                if ringing:
                    for t in ringing: await db.delete(t)
                    await db.commit()
                    return f"Stopped {len(ringing)} ringing timer(s)."
                else:
                    return "No ringing timers found."

            target_timer = await _find_timer(db, args)
            if not target_timer: return "Timer not found."
            
            await db.delete(target_timer)
            await db.commit()
            return f"Timer '{target_timer.label}' stopped."
            
        elif action == "update":
            target_timer = await _find_timer(db, args)
            if not target_timer: return "Timer not found."
            if args.get("add_time"):
                try:
                    target_timer.end_time += timedelta(seconds=parse_duration_string(args.get("add_time")))
                    await db.commit()
                    return "Timer updated."
                except ValueError: return "Invalid duration."

    return "Unknown action."

# --- Tool Definitions ---

DEFINITIONS = [
    {"google_search": {}},
    {
        "function_declarations": [
            {
                "name": "handle_alarm",
                "description": "Manage alarms. To DELETE/STOP: If 'stop' is said without time, it stops RINGING alarms. To cancel a future alarm, provide time/label.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "action": {"type": "STRING", "enum": ["create", "read", "update", "delete"]},
                        "time": {"type": "STRING", "description": "Time (e.g. '5pm')."},
                        "label": {"type": "STRING"},
                        "new_time": {"type": "STRING"},
                        "alarm_id": {"type": "INTEGER"}
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "handle_timer",
                "description": "Manage timers.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "action": {"type": "STRING", "enum": ["create", "read", "update", "delete"]},
                        "duration": {"type": "STRING"},
                        "label": {"type": "STRING"},
                        "add_time": {"type": "STRING"},
                        "timer_id": {"type": "INTEGER"}
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "update_profile",
                "description": "Update user profile.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {"type": "STRING"},
                        "city": {"type": "STRING"},
                        "timezone": {"type": "STRING"},
                        "gender": {"type": "STRING"}
                    }
                }
            },
            {
                "name": "remember_fact",
                "description": "Store a fact.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"key": {"type": "STRING"}, "value": {"type": "STRING"}},
                    "required": ["key", "value"]
                }
            },
            {
                "name": "forget_fact",
                "description": "Forget a fact.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"key": {"type": "STRING"}},
                    "required": ["key"]
                }
            }
        ]
    }
]

async def execute_tool(name: str, args: dict):
    print(f"DEBUG: execute_tool {name} with {args}")
    if name == "handle_alarm": return await handle_alarm_logic(args.get("action"), args)
    elif name == "handle_timer": return await handle_timer_logic(args.get("action"), args)
    elif name == "update_profile":
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == 1))
            user = result.scalar_one_or_none()
            if not user: user = User(id=1)
            if "name" in args: user.name = args["name"]
            if "city" in args: user.city = args["city"]
            if "timezone" in args: user.timezone = args["timezone"]
            if "gender" in args: user.gender = args["gender"]
            db.add(user)
            await db.commit()
            return "Profile updated."
    elif name == "remember_fact":
        key, value = args.get("key", "").lower().strip(), args.get("value")
        if not key or not value: return "Error: Key/Value required."
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(UserMemory).where(UserMemory.key == key))
            if existing := result.scalar_one_or_none(): existing.value = value
            else: db.add(UserMemory(user_id=1, key=key, value=value))
            await db.commit()
            return f"Remembered {key}."
    elif name == "forget_fact":
        key = args.get("key", "").lower().strip()
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(UserMemory).where(UserMemory.key == key))
            if existing := result.scalar_one_or_none():
                await db.delete(existing)
                await db.commit()
                return f"Forgot {key}."
            return "Fact not found."
    return "Unknown tool"