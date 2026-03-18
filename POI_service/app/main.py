from fastapi import FastAPI

# This is the "app" variable uvicorn is looking for
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "online", "message": "Travel Lung Tung POI API is live"}