import asyncio
import os
from core.db import init_db

async def main():
    print("Worker starting...")
    init_db()
    # In a real system, this would listen to a message queue (RabbitMQ/Redis)
    # For now, it's a heartbeat stub to keep the container alive and demonstrate the service
    while True:
        await asyncio.sleep(60)
        print("Worker heartbeat...")

if __name__ == "__main__":
    asyncio.run(main())
