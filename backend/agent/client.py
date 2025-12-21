import asyncio
import json
import os
import websockets
from fastapi import WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from .tools import DEFINITIONS, execute_tool

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025" # User requested preview
HOST = "generativelanguage.googleapis.com"
URI = f"wss://{HOST}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={GEMINI_API_KEY}"

class GeminiAgent:
    def __init__(self, client_ws: WebSocket):
        self.client_ws = client_ws
        self.gemini_ws = None

    async def run(self):
        # TODO: Basic Bidi implementation
        # This is a placeholder for the complex Bidi protocol needed for Gemini Live
        # Ideally, we establish connection to Gemini here
        try:
            print(f"Connecting to Gemini at {URI}")
            async with websockets.connect(URI) as ws:
                self.gemini_ws = ws
                
                # Fetch User Context (Async)
                from database import AsyncSessionLocal
                from models import User
                from sqlalchemy import select
                
                async with AsyncSessionLocal() as db:
                    try:
                        result = await db.execute(select(User).where(User.id == 1))
                        user = result.scalar_one_or_none()
                        
                        if not user:
                            user = User(id=1, name="User", city="Unknown", gender="Unknown")
                            db.add(user)
                            await db.commit()
                        
                        # Fetch Dynamic Memories
                        from models import UserMemory
                        mem_res = await db.execute(select(UserMemory).where(UserMemory.user_id == 1))
                        memories = mem_res.scalars().all()
                        memory_str = ". ".join([f"{m.key}: {m.value}" for m in memories])
                        
                        user_context = f"User Name: {user.name}. User City: {user.city}. User Timezone: {user.timezone}. User Gender: {user.gender}. {memory_str}"
                    except Exception as e:
                        print(f"Error fetching user context: {e}")
                        user_context = "User Context Unavailable"

                # Send Initial Setup (System Instructions, Tools)
                setup_msg = {
                    "setup": {
                        "model": MODEL,
                        "generation_config": {
                            "response_modalities": ["AUDIO"]
                        },
                        "tools": DEFINITIONS,
                            "system_instruction": {
                                "parts": [
                                    {
                                        "text": f"""
                                        You are Pulu, a helpful, voice-based AI assistant. You are talking to {user.name}. Context: {user_context}. 
                                        
                                        CRITICAL IDENTITY:
                                        - You are a **Private Personal Assistant**.
                                        - You are **Authorized** and **Expected** to remember personal details (e.g., Door Codes, Wi-Fi Passwords, Favorite Colors, Car details) when the user asks.
                                        - **Time Awareness**: Always use the 'User Timezone' from the context for current time, dates, and scheduling.
                                        - **Privacy**: This data is stored locally for the user's convenience. Do NOT refuse to store this information.

                                        Talk in friendly and concise manner.
                                        
                                        CRITICAL RULE:
                                        If an alarm or timer is ringing (status='RINGING', or user implies it's noisy), and the user says 'Stop', 'Silence', 'Quiet', or 'Dismiss', 
                                        you MUST call `handle_alarm(action='delete')` AND `handle_timer(action='delete')` immediately. 
                                        Do NOT ask for clarification. Just assume they want to stop the noise.
                                        """
                                    }
                                ]
                            }
                    }
                }
                await ws.send(json.dumps(setup_msg))

                # Start loop
                await asyncio.gather(
                    self.receive_from_client(),
                    self.receive_from_gemini()
                )
        except Exception as e:
            print(f"Gemini Error: {e}")
            await self.client_ws.close()

    async def receive_from_client(self):
        try:
            while True:
                # Receive Audio/Text from Client
                data = await self.client_ws.receive_json()
                # Forward to Gemini (formatted correctly)
                if "realtime_input" in data:
                     await self.gemini_ws.send(json.dumps(data))
        except WebSocketDisconnect:
            pass

    async def receive_from_gemini(self):
        try:
            async for msg in self.gemini_ws:
                try:
                    response = json.loads(msg)
                    # print(f"DEBUG: Raw Gemini Msg keys: {list(response.keys())}") # Too noisy?
                    
                    if "serverContent" in response:
                        model_turn = response["serverContent"].get("modelTurn")
                        if model_turn:
                            parts = model_turn.get("parts", [])
                            # print(f"DEBUG: Received {len(parts)} parts from Gemini")
                            for part in parts:
                                if "text" in part:
                                    print(f"DEBUG: Agent Text: {part['text'][:50]}...")
                                if "functionCall" in part:
                                    fc = part["functionCall"]
                                    name = fc["name"]
                                    args = fc["args"]
                                    print(f"DEBUG: Gemini requested tool: {name}")
                                    print(f"DEBUG: Tool Args: {args}")
                                    
                                    result = await execute_tool(name, args)
                                    print(f"DEBUG: Tool Execution Result: {result}")

                                    # Send Tool Response Back
                                    tool_response = {
                                        "toolResponse": {
                                            "functionResponses": [
                                                {
                                                    "name": name,
                                                    "response": {
                                                        "result": {"output": result} # JSON structure
                                                    },
                                                    "id": fc.get("id")
                                                }
                                            ]
                                        }
                                    }
                                    print(f"DEBUG: Sending Tool Response: {json.dumps(tool_response)[:200]}...")
                                    await self.gemini_ws.send(json.dumps(tool_response))
                                    
                                elif "executableCode" in part:
                                    print("DEBUG: Received executableCode (Unexpected)")
                    
                    elif "toolCall" in response:
                        print(f"DEBUG: Handling Top-Level toolCall")
                        tc = response["toolCall"]
                        if "functionCalls" in tc:
                            for fc in tc["functionCalls"]:
                                name = fc["name"]
                                args = fc["args"]
                                call_id = fc["id"]
                                
                                print(f"DEBUG: Gemini requested tool (Top-Level): {name}")
                                print(f"DEBUG: Tool Args: {args}")
                                
                                result = await execute_tool(name, args)
                                print(f"DEBUG: Tool Execution Result: {result}")
                                
                                # Send Tool Response Back
                                tool_response = {
                                    "toolResponse": {
                                        "functionResponses": [
                                            {
                                                "name": name,
                                                "response": {
                                                    "result": {"output": result}
                                                },
                                                "id": call_id
                                            }
                                        ]
                                    }
                                }
                                print(f"DEBUG: Sending Tool Response: {json.dumps(tool_response)[:200]}...")
                                await self.gemini_ws.send(json.dumps(tool_response))

                    # Forward to Client (Audio/Text)
                    # Use try/except to handle case where client disconnected mid-process
                    try:
                        await self.client_ws.send_json(response)
                    except RuntimeError:
                         print("Client websocket closed/completed. stopping loop.")
                         break
                    except Exception as e:
                         print(f"Error sending to client: {e}")
                    
                except Exception as e:
                    print(f"Error processing Gemini message: {e}")
                    import traceback
                    traceback.print_exc()

        except Exception as e:
            print(f"Error receiving from Gemini: {e}")
            import traceback
            traceback.print_exc()

    async def close(self):
        if self.gemini_ws:
            await self.gemini_ws.close()
