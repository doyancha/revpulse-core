"""
Production Server Entrypoint for RevPulse Autonomous AR Recovery Engine.
Launches Uvicorn server hosting the FastAPI communications gateway and background aging scheduler.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
