import asyncio
import db

async def main():
    print("Updating User Profile to Defaults...")
    await db.update_user_profile("user_1", {
        "name": "Mukesh",
        "city": "San Jose",
        "timezone": "America/Los_Angeles",
        "gender": "Male"
    })
    print("Profile Updated!")
    
    profile = await db.get_user_profile()
    print(f"Verified Profile: {profile}")

if __name__ == "__main__":
    asyncio.run(main())
