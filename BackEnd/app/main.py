from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import rag, converter
from app.core.database import Base, engine
import os

os.makedirs("data", exist_ok=True)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="IA Cargas API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag.router)
app.include_router(converter.router)

@app.get("/")
def read_root():
    return {"status": "ok", "service": "IA Cargas"}
