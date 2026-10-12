"""Mock OpenAI-compatible inference server for development."""

from fastapi import FastAPI

from src.handlers import router

app = FastAPI(title="Mise Mock Inference", version="0.1.0")
app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8080, reload=True)
