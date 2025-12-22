from datetime import datetime, timedelta, time
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import re
import db  # New In-Memory DB

# --- Helper Functions (Time Parsing) ---

def parse_time_string(time_str: str, user_timezone: str = None) -> datetime:
    """Parses natural language time string into a future datetime object."""
    # For Demo/In-Memory mode, simplify timezone handling or ignore if causing issues
    # But let's try to keep it logic-compatible.
    tz = None
    if user_timezone and user_timezone != "UTC":
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

# --- Logic Handlers (Updated for In-Memory DB) ---

async def handle_alarm_logic(action: str, args: dict):
    if action == "create":
        time_str = args.get("time")
        if not time_str: return "Error: Time required."
        try:
            profile = await db.get_user_profile()
            tz = profile.get("timezone")
            alarm_time = parse_time_string(time_str, tz)
            
            await db.create_alarm({
                "time": alarm_time,
                "label": args.get("label", "Alarm"),
                "status": "ACTIVE"
            })
            return f"Alarm set for {alarm_time.strftime('%H:%M')}."
        except ValueError as e: return f"Error: {e}"

    elif action == "read":
        alarms = await db.get_active_alarms()
        # Sort
        alarms.sort(key=lambda x: x["time"])
        
        if not alarms: return "No active alarms."
        report = "Alarms:\n"
        for a in alarms:
            status = " (RINGING!)" if a["status"] == "RINGING" else ""
            report += f"- {a['time'].strftime('%H:%M')} {a['label']}{status}\n"
        return report

    elif action == "delete":
        # Simple Logic for Demo: If Stop -> Remove Ringing. If specific -> Remove specific.
        has_specs = bool(args.get("time") or args.get("label") or args.get("alarm_id"))
        
        if not has_specs:
            # Stop Ringing
            alarms = await db.get_active_alarms()
            stopped = 0
            for a in alarms:
                if a["status"] == "RINGING":
                    await db.delete_alarm(a["id"])
                    stopped += 1
            if stopped: return f"Stopped {stopped} ringing alarm(s)."
            else: return "No ringing alarms found."
            
        # Find specific (Iterate over all active alarms)
        alarms = await db.get_active_alarms()
        target = None
        # Simplified Match Logic
        target_time = None
        if args.get("time"):
             try: target_time = parse_time_string(args.get("time"))
             except: pass

        for a in alarms:
            if args.get("alarm_id") and str(a["id"]) == str(args["alarm_id"]):
                 target = a; break
            if target_time and a["time"] == target_time:
                 target = a; break
            if args.get("label") and args["label"].lower() in a["label"].lower():
                 target = a; break
        
        if target:
            await db.delete_alarm(target["id"])
            return f"Alarm for {target['time'].strftime('%H:%M')} cancelled."
        return "Alarm not found."
            
    elif action == "update":
         # Simplified Update - Find first match
         alarms = await db.get_active_alarms()
         target = None
         for a in alarms:
             if args.get("label") and args["label"].lower() in a["label"].lower():
                 target = a; break
         
         if target and args.get("new_time"):
             try:
                 new_time = parse_time_string(args.get("new_time"))
                 await db.update_alarm(target["id"], {"time": new_time})
                 return "Alarm updated."
             except Exception as e: return f"Error: {e}"
         return "Alarm not found or invalid updates."

    return "Unknown action."

async def handle_timer_logic(action: str, args: dict):
    if action == "create":
        if not args.get("duration"): return "Duration required."
        try:
            sec = parse_duration_string(args.get("duration"))
            end = datetime.now() + timedelta(seconds=sec)
            await db.create_timer({
                "duration_seconds": sec,
                "end_time": end,
                "label": args.get("label", "Timer"),
                "status": "ACTIVE"
            })
            return f"Timer set for {sec}s."
        except ValueError as e: return f"Error: {e}"

    elif action == "read":
        timers = await db.get_active_timers()
        timers.sort(key=lambda x: x["end_time"])
        if not timers: return "No active timers."
        now = datetime.now()
        report = "Timers:\n"
        for t in timers:
            remaining = max(0, int((t["end_time"] - now).total_seconds()))
            if t["status"] == "RINGING": report += f"- {t['label']}: RINGING!\n"
            else: report += f"- {t['label']}: {remaining}s remaining\n"
        return report

    elif action == "delete":
        has_specs = bool(args.get("label") or args.get("timer_id"))
        if not has_specs:
            timers = await db.get_active_timers()
            stopped = 0
            for t in timers:
                if t["status"] == "RINGING":
                    await db.delete_timer(t["id"])
                    stopped += 1
            if stopped: return f"Stopped {stopped} ringing timer(s)."
            else: return "No ringing timers found."
            
        timers = await db.get_active_timers()
        for t in timers:
             if args.get("label") and args["label"].lower() in t["label"].lower():
                  await db.delete_timer(t["id"])
                  return f"Timer '{t['label']}' stopped."
        return "Timer not found."

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
        updates = {}
        if "name" in args: updates["name"] = args["name"]
        if "city" in args: updates["city"] = args["city"]
        if "timezone" in args: updates["timezone"] = args["timezone"]
        if "gender" in args: updates["gender"] = args["gender"]
        await db.update_user_profile("user_1", updates)
        return "Profile updated."
    elif name == "remember_fact":
        key, value = args.get("key", "").lower().strip(), args.get("value")
        if not key or not value: return "Error: Key/Value required."
        await db.add_memory("user_1", key, value)
        return f"Remembered {key}."
    elif name == "forget_fact":
        key = args.get("key", "").lower().strip()
        await db.delete_memory("user_1", key)
        return f"Forgot {key}."
    return "Unknown tool"