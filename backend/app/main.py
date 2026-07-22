import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import chat, dashboard, files, health, lessons, me, quiz

load_dotenv()

app = FastAPI(title="Personal LMS API")

_origins = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(me.router)
app.include_router(files.router)
app.include_router(lessons.router)
app.include_router(quiz.router)
app.include_router(chat.router)
app.include_router(dashboard.router)
