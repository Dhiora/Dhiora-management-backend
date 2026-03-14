import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        ws="websockets",
        ws_ping_interval=20,
        ws_ping_timeout=300,
    )
