from datetime import datetime, time, timedelta, timezone
import re
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import db 

# --- Helper Functions ---

def parse_time_string(time_str: str, user_timezone: str = "UTC") -> datetime:
    """
    Parses natural language time string into a future datetime object.
    Returns a Timezone-Aware Datetime (converted to UTC for storage).
    """
    try:
        tz = ZoneInfo(user_timezone)
    except:
        tz = ZoneInfo("UTC")
    
    # 1. Get 'Now' in User's Timezone
    now_local = datetime.now(tz)
    target_date = now_local.date()
    target_time = None
    
    time_str = time_str.lower().strip()

    if "tomorrow" in time_str:
        target_date += timedelta(days=1)
        time_str = time_str.replace("tomorrow", "").strip()

    if time_str in ["noon", "midday"]:
        target_time = time(12, 0)
    elif time_str in ["midnight"]:
        target_time = time(0, 0)
        if target_date == now_local.date(): 
            target_date += timedelta(days=1)
    
    elif not target_time:
        # Regex to match 7, 7:30, 7pm, 7:30pm
        match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?', time_str)
        if match:
            hour_str, minute_str, meridiem = match.groups()
            hour = int(hour_str)
            minute = int(minute_str) if minute_str else 0
            
            if meridiem:
                if "p" in meridiem and hour < 12: hour += 12
                if "a" in meridiem and hour == 12: hour = 0
            
            target_time = time(hour, minute)

    if not target_time:
        raise ValueError("Could not parse time")

    # 2. Combine Date + Time in User TZ
    local_dt = datetime.combine(target_date, target_time).replace(tzinfo=tz)
    
    # 3. Handle "Past" times (Assume tomorrow)
    # e.g. User says "7am" at 8am -> They mean tomorrow 7am
    if local_dt <= now_local:
        local_dt += timedelta(days=1)

    # 4. Convert to UTC for Storage
    return local_dt.astimezone(ZoneInfo("UTC"))

# --- Tool Definitions ---

DEFINITIONS = [
    {"google_search": {}},
    {
        "function_declarations": [
            {
                "name": "handle_alarm",
                "description": "Create, read, or delete alarms. To DELETE cancellation of a specific alarm, provide 'time' or 'alarm_id'.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "action": {"type": "STRING", "enum": ["create", "read", "delete"]},
                        "time": {"type": "STRING", "description": "Natural language time (e.g. '7am', 'tomorrow noon')"},
                        "label": {"type": "STRING", "description": "Name of the alarm"},
                        "alarm_id": {"type": "STRING", "description": "ID of alarm to delete"}
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "handle_timer",
                "description": "Set a timer for a duration.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "action": {"type": "STRING", "enum": ["create", "read", "delete"]},
                        "duration": {"type": "INTEGER", "description": "Duration in seconds"},
                        "label": {"type": "STRING"},
                        "timer_id": {"type": "STRING"}
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "update_profile",
                "description": "Update user profile details.",
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
                "name": "manage_memory",
                "description": "Remember or forget facts.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "action": {"type": "STRING", "enum": ["add", "delete"]},
                        "key": {"type": "STRING"},
                        "value": {"type": "STRING"}
                    },
                    "required": ["action", "key"]
                }
            }
        ]
    }
]

# --- Execution Logic ---

async def handle_alarm_logic(action: str, args: dict):
    # 1. Fetch Profile for Timezone Context
    profile = await db.get_user_profile("user_1")
    user_tz_str = profile.get("timezone", "UTC")
    try:
        user_tz = ZoneInfo(user_tz_str)
    except:
        user_tz = ZoneInfo("UTC")

    if action == "create":
        time_str = args.get("time")
        if not time_str: return "Error: Time required."
        try:
            # Parse logic handles the conversion to UTC
            alarm_dt_utc = parse_time_string(time_str, user_tz_str)
            
            await db.create_alarm({
                "time": alarm_dt_utc, 
                "label": args.get("label", "Alarm"),
                "status": "ACTIVE",
                "created_at": datetime.now(ZoneInfo("UTC"))
            })
            
            # Confirm back to user in THEIR time
            local_display = alarm_dt_utc.astimezone(user_tz).strftime("%I:%M %p")
            return f"Alarm set for {local_display}."
        except ValueError:
            return "Could not understand the time."

    elif action == "read":
        alarms = await db.get_active_alarms()
        if not alarms: return "No active alarms."
        
        # Convert UTC -> User Timezone for display
        output = []
        for a in alarms:
            # Ensure awareness
            utc_time = a['time']
            if utc_time.tzinfo is None:
                utc_time = utc_time.replace(tzinfo=ZoneInfo("UTC"))
            
            # Convert
            local_time = utc_time.astimezone(user_tz)
            time_str = local_time.strftime("%I:%M %p") # e.g. "07:00 AM"
            
            output.append(f"[{a['id']}] {a.get('label','Alarm')} at {time_str}")
            
        return "Current Alarms:\n" + "\n".join(output)

    elif action == "delete":
        alarm_id = args.get("alarm_id")
        
        # If no ID provided, check if TIME is provided to find the alarm
        if not alarm_id and args.get("time"):
            try:
                target_dt_utc = parse_time_string(args.get("time"), user_tz_str)
                alarms = await db.get_active_alarms()
                for a in alarms:
                    # Match within 60s
                    utc_time = a['time']
                    if utc_time.tzinfo is None: utc_time = utc_time.replace(tzinfo=ZoneInfo("UTC"))
                    
                    diff = abs((utc_time - target_dt_utc).total_seconds())
                    if diff < 60:
                        alarm_id = a["id"]
                        break
            except Exception as e:
                print(f"Error finding alarm by time: {e}")

        if not alarm_id:
             # Convenience: If no ID AND no specific time found/given, check if "delete all" intended?
             # For safety, let's ONLY delete all if user specifically asked or if we want that behavior.
             # The user code had this 'delete all' behavior on empty ID.
             # I will keep it BUT only if time wasn't passed (handled above)
             # Wait, if time WAS passed but not found, we shouldn't delete all.
             if args.get("time"):
                 return f"No alarm found at {args.get('time')}."

             alarms = await db.get_active_alarms()
             count = 0
             for a in alarms:
                 if a.get("status") == "RINGING":
                     await db.delete_alarm(a["id"])
                     count += 1
             
             if count > 0:
                 return f"Stopped {count} ringing alarm(s)."
             return "No ringing alarms found."
        
        await db.delete_alarm(alarm_id)
        return "Alarm deleted."

async def handle_timer_logic(action: str, args: dict):
    # Timers are relative, so timezone matters less, but end_time is absolute
    profile = await db.get_user_profile("user_1")
    user_tz_str = profile.get("timezone", "UTC")
    try:
        user_tz = ZoneInfo(user_tz_str)
    except:
        user_tz = ZoneInfo("UTC")

    if action == "create":
        duration = args.get("duration")
        if not duration: return "Error: Duration required."
        
        end_time_utc = datetime.now(ZoneInfo("UTC")) + timedelta(seconds=duration)
        
        await db.create_timer({
            "duration": duration,
            "end_time": end_time_utc,
            "label": args.get("label", "Timer"),
            "status": "ACTIVE",
            "created_at": datetime.now(ZoneInfo("UTC"))
        })
        return f"Timer set for {duration} seconds."

    elif action == "read":
        timers = await db.get_active_timers()
        if not timers: return "No active timers."
        
        output = []
        for t in timers:
            utc_time = t['end_time']
            if utc_time.tzinfo is None:
                utc_time = utc_time.replace(tzinfo=ZoneInfo("UTC"))
            
            local_time = utc_time.astimezone(user_tz)
            remaining = (utc_time - datetime.now(ZoneInfo("UTC"))).total_seconds()
            
            if remaining > 0:
                output.append(f"[{t['id']}] {t.get('label','Timer')}: Ends at {local_time.strftime('%I:%M %p')} ({int(remaining)}s left)")
        
        return "Current Timers:\n" + "\n".join(output)

    elif action == "delete":
        timer_id = args.get("timer_id")
        if not timer_id:
             timers = await db.get_active_timers()
             count = 0
             for t in timers:
                 if t.get("status") == "RINGING":
                     await db.delete_timer(t["id"])
                     count += 1
             
             if count > 0:
                 return f"Stopped {count} ringing timer(s)."
             return "No ringing timers found."
        await db.delete_timer(timer_id)
        return "Timer deleted."

# --- Main Executor ---
async def execute_tool(name, args):
    if name == "handle_alarm":
        return await handle_alarm_logic(args.get("action"), args)
    elif name == "handle_timer":
        return await handle_timer_logic(args.get("action"), args)
    elif name == "update_profile":
        await db.update_user_profile("user_1", args)
        return "Profile updated."
    elif name == "manage_memory":
        action = args.get("action")
        if action == "add":
            await db.add_memory("user_1", args.get("key"), args.get("value"))
            return "Fact stored."
        elif action == "delete":
            await db.delete_memory("user_1", args.get("key"))
            return "Fact forgotten."
    return "Tool not found"