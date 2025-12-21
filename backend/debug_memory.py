import asyncio
from database import AsyncSessionLocal, init_db
from models import User, UserMemory
from sqlalchemy import select

async def test_memory():
    # 1. Initialize DB (ensure tables exist)
    await init_db()
    
    async with AsyncSessionLocal() as db:
        # 2. Check User
        res = await db.execute(select(User).where(User.id == 1))
        user = res.scalar_one_or_none()
        if not user:
            print("Creating Test User...")
            user = User(id=1, name="TestUser", city="TestCity", timezone="UTC", gender="TestGender")
            db.add(user)
            await db.commit()
        else:
            print(f"Found User: {user.name}")

        # 3. Create Memory
        key = "debug_fact"
        val = "works!"
        
        # Check if exists
        res = await db.execute(select(UserMemory).where(UserMemory.key == key))
        existing = res.scalar_one_or_none()
        if existing:
            print("Updating existing memory...")
            existing.value = val
        else:
             print("Creating new memory...")
             mem = UserMemory(user_id=1, key=key, value=val)
             db.add(mem)
        
        await db.commit()
        print("Commit complete.")

        # 4. Read Verification
        res = await db.execute(select(UserMemory).where(UserMemory.user_id == 1))
        mems = res.scalars().all()
        print("--- Current Memories ---")
        for m in mems:
            print(f"{m.key}: {m.value}")

if __name__ == "__main__":
    asyncio.run(test_memory())
