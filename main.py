import os
import sys
import uvicorn

from loguru import logger

from fastapi import FastAPI
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from db.database.Neo4jConnector import Neo4jConnector
from db.database.FirebaseConnector import FireStoreConnector

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("THE APPLICATION IS LAUNCHING....")
    graph_db = Neo4jConnector()
    firebase_db = FireStoreConnector()
    

    yield
    logger.info("THE APPLICATION IS CLOSING....")


app = FastAPI(
    title=os.getenv("APP_NAME", "Travel Lung Tung"), 
    lifespan=lifespan
)

@app.get("/")
def read_root():
    logger.info("Root endpoint called")
    return {
        "message": "Success",
        "status": 200
    }

@app.post("/write")
def write_to_database():
    pass

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)