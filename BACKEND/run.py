"""
Entry point for Windows: sets WindowsSelectorEventLoopPolicy before uvicorn
starts, so oracledb async connections work correctly on Windows.
"""
import sys

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:socket_app",
        host="0.0.0.0",
        port=8000,
        reload=False,   # reload=True spawns subprocess that loses the policy fix
    )
