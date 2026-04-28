"""
Точка входа FastAPI-приложения.

Запуск из папки backend:
    uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api import config as config_api, fs, tasks, transcribe
from app.services.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="Transcriber",
    description="Локальная транскрибация аудио через WhisperX",
    version="0.3.0",
)

@app.on_event("startup")
def on_startup() -> None:
    init_db()
    
app.include_router(transcribe.router)
app.include_router(tasks.router)
app.include_router(fs.router)
app.include_router(config_api.router)

@app.get("/")
def root() -> dict:
    return {"app": "transcriber", "status": "ok", "docs": "/docs"}


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}
