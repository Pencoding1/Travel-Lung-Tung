# ai_service/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

app = FastAPI(title="Agent Hub AI Service")

class ChatRequest(BaseModel):
    session_id: str
    message: str

@app.post("/chat")
async def chat_with_agent(request: ChatRequest):
    """
    1. Receives user message.
    2. (Optional) Calls Gemini Embedding 2 for RAG context retrieval here.
    3. Passes message to OpenClawd/Ollama for intent analysis and tool execution.
    """
    # Define your Ollama + OpenClawd payload
    openclawd_payload = {
        "model": "qwen3.5:9b",
        "messages": [
            {"role": "user", "content": request.message}
        ],
        "stream": False,
        # Point OpenClawd to the MCP config we built in Step 2
        "mcp_config": "/path/to/mcp_config.json" 
    }

    try:
        # Send the execution command to your local Ollama instance
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "http://host.docker.internal:11434/api/chat",
                json=openclawd_payload
            )
            response.raise_for_status()
            
            # OpenClawd automatically handles the loop, calls Port 8000/8001/8989 
            # if needed, and returns the final synthesized string.
            return {"reply": response.json()["message"]["content"]}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent loop failed: {str(e)}")

# Run with: uvicorn main:app --host 0.0.0.0 --port 8002