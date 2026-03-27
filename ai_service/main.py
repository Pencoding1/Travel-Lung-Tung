import re
import os
import json
import httpx
import asyncio
import logging

from pathlib import Path
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException

# MCP Client Imports
from mcp import ClientSession
from mcp.types import TextContent
from mcp.client.sse import sse_client

from domains.payloads import ChatRequest, chat_history, ItineraryRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Travel_Lung_Tung_Agent")

PARENT_PATH = Path.cwd()

# --- GEMINI CONFIGURATION ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY is not set. API calls will fail.")

# Using Gemini's OpenAI-compatible endpoint makes migration seamless
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
# gemini-2.5-flash is extremely fast, cheap, and excellent at tool calling
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro") 
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://poi_mcp:8001/sse")

app = FastAPI(title="Travel Lung Tung AI Hub")

# 1. Load the Persona from prompt.json
try:
    with open("prompt.json", "r", encoding="utf-8") as f:
        prompt_data = json.load(f)
        SYSTEM_PROMPT = prompt_data.get("system_prompt", "") + "\n\n" + "\n".join(prompt_data.get("instruction", []))
except FileNotFoundError:
    logger.warning("prompt.json not found. Using default persona.")
    SYSTEM_PROMPT = "You are Travel Lung Tung, an elite AI travel assistant for Vietnam."

def get_gemini_headers():
    return {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json"
    }
    
async def analyze_intent(user_message: str) -> str:
    router_prompt = f"""
    You are an intent classification router for the "Travel Lung Tung" app.
    Analyze the following user message. 
    If the user is saying hello, goodbye, thanking you, or making general small talk, classify it as "CHITCHAT".
    If the user is asking about places, travel, routing, coffee shops, hotels, or any location data, classify it as "TRAVEL".
    
    You MUST respond with ONLY a valid JSON object containing a single key "intent".
    Example: {{"intent": "CHITCHAT"}}
    
    User Message: "{user_message}"
    """
    
    payload = {
        "model": GEMINI_MODEL,
        "messages": [{"role": "system", "content": router_prompt}],
        "response_format": {"type": "json_object"}, # Force strict JSON output
        "temperature": 0.0,
        "max_completion_tokens": 20
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            response = await http_client.post(GEMINI_URL, headers=get_gemini_headers(), json=payload)
            response.raise_for_status()
            
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            
            clean_content = re.sub(r'```json\s*', '', content)
            clean_content = re.sub(r'```', '', clean_content).strip()
            
            parsed_intent = json.loads(clean_content)
            return parsed_intent.get("intent", "TRAVEL").upper()
            
    except Exception as e:
        logger.warning(f"Router failed or timed out, defaulting to TRAVEL: {e}")
        return "TRAVEL"


async def execute_agent_loop(session_id: str, user_message: str) -> str:
    if session_id not in chat_history:
        chat_history[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    chat_history[session_id].append({"role": "user", "content": user_message})
    
    try:
        async with sse_client(MCP_SERVER_URL) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as mcp_session:
                await mcp_session.initialize()
                
                mcp_tools = await mcp_session.list_tools()
                gemini_tools = []
                for tool in mcp_tools.tools:
                    gemini_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema
                        }
                    })
                
                MAX_TURNS = 5
                current_turn = 0
                
                async with httpx.AsyncClient(timeout=60.0) as http_client:
                    while current_turn < MAX_TURNS:
                        current_turn += 1
                        payload = {
                            "model": GEMINI_MODEL,
                            "messages": chat_history[session_id],
                            "tools": gemini_tools,
                            "temperature": 0.3
                        }
                        
                        logger.info("🧠 Passing context to Gemini...")
                        response = await http_client.post(GEMINI_URL, headers=get_gemini_headers(), json=payload)
                        response.raise_for_status()
                        response_data = response.json()
                        
                        assistant_msg = response_data.get("choices", [{}])[0].get("message", {})
                        
                        # Strip out None values that might confuse the chat history
                        assistant_msg = {k: v for k, v in assistant_msg.items() if v is not None}
                        
                        chat_history[session_id].append(assistant_msg)
                        
                        tool_calls = assistant_msg.get("tool_calls", [])
                        
                        if not tool_calls:
                            logger.info("✅ Agent loop complete. Returning synthesis.")
                            return assistant_msg.get("content", "")
                        
                        for tool_call in tool_calls:
                            tool_name = tool_call["function"]["name"]
                            raw_args = tool_call["function"]["arguments"]
                            
                            # Safety check: Cloud APIs return JSON strings, Ollama returned dicts
                            tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                            
                            logger.info(f"🛠️ Executing Tool: {tool_name} | Args: {tool_args}")
                            
                            try:
                                result = await mcp_session.call_tool(tool_name, arguments=tool_args)
                                
                                content_item = result.content[0]
                                tool_result_str = content_item.text if isinstance(content_item, TextContent) else str(content_item)
                                    
                            except Exception as e:
                                logger.error(f"Tool failure: {e}")
                                tool_result_str = json.dumps({"error": str(e)})
                            
                            logger.info(f"TOOL: {tool_name}; RESULT length: {len(tool_result_str)}")
                            chat_history[session_id].append({
                                "role": "tool",
                                "content": tool_result_str,
                                "tool_call_id": tool_call.get("id", "call_123"),
                                "name": tool_name
                            })
                            
                    return "I've searched extensively, but I'm hitting a limit. Based on what I've found so far..."
                            
    except Exception as e:
        logger.error(f"Critical Agent Hub Failure: {e}")
        raise HTTPException(status_code=500, detail=f"Internal AI Engine Failure: {str(e)}")


import asyncio

@app.post("/generate_itinerary")
async def generate_itinerary_endpoint(request: ItineraryRequest):
    logger.info(f"Generating {request.duration_days}-day itinerary for {request.target_district}")
    tool_chain = []
    current_step = 1
    
    try:
        async with sse_client(MCP_SERVER_URL) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as mcp_session:
                await mcp_session.initialize()
                
                # --- STEP 1: RESOLVE GEOGRAPHIC ID ---
                resolve_args = {"keyword": request.target_district}
                tool_chain.append({"step": current_step, "tool": "resolve_geographic_id", "args": resolve_args})
                
                resolve_result = await mcp_session.call_tool("resolve_geographic_id", arguments=resolve_args)
                resolve_data = json.loads(resolve_result.content[0].text)
                
                if not resolve_data.get("success") or not resolve_data.get("matches"):
                    tool_chain[-1]["status"] = "failed"
                    return {"reply": "Location not found.", "tool_chain": tool_chain}
                    
                strict_district_id = resolve_data["matches"][0]["id"]
                tool_chain[-1]["status"] = "success"
                tool_chain[-1]["summary"] = f"Resolved to: {strict_district_id}"
                current_step += 1

                # --- STEP 2: SCATTERGATHER CANDIDATES ---
                categories = [
                    {"id": "cat_coffee", "label": "Cafes"},
                    {"id": "cat_restaurant", "label": "Restaurants"},
                    {"id": "cat_attractions", "label": "Attractions"}
                ]
                
                raw_poi_list = []
                for cat in categories:
                    args = {"district_id": strict_district_id, "category_id": cat["id"], "limit": 6}
                    tool_chain.append({"step": current_step, "tool": f"explore_pois ({cat['label']})", "args": args})
                    
                    res = await mcp_session.call_tool("explore_pois", arguments=args)
                    found = json.loads(res.content[0].text).get("results", [])
                    raw_poi_list.extend(found)
                    
                    tool_chain[-1]["status"] = "success"
                    tool_chain[-1]["summary"] = f"Found {len(found)} candidates"
                    current_step += 1

                # --- STEP 3: ENRICHMENT (WITH X-RAY LOGGING) ---
                
                # 1. Check what the raw list actually contains
                logger.info(f"👉 X-RAY: Found {len(raw_poi_list)} raw POIs.")
                if raw_poi_list:
                    logger.info(f"👉 X-RAY: First raw POI keys: {raw_poi_list[0].keys()}")

                # 2. Extract IDs aggressively
                unique_ids = []
                for poi in raw_poi_list:
                    poi_id = poi.get("POI_ID") or poi.get("id")
                    if poi_id:
                        unique_ids.append(poi_id)
                unique_ids = list(set(unique_ids)) # Remove duplicates
                
                logger.info(f"👉 X-RAY: Extracted {len(unique_ids)} unique IDs.")

                tool_chain.append({
                    "step": current_step, 
                    "tool": "get_poi_details (Bulk Enrichment)", 
                    "summary": f"Attempting to enrich {len(unique_ids)} POIs..."
                })

                if not unique_ids:
                    logger.error("❌ X-RAY FATAL: No IDs extracted! The pipeline stops here.")
                    tool_chain[-1]["status"] = "failed"
                    tool_chain[-1]["summary"] = "Failed: No POI IDs found to enrich."
                else:
                    logger.info(f"👉 X-RAY: Firing tool 'get_poi_details' for IDs: {unique_ids[:3]}...")
                    # Fire parallel requests
                    tasks = [mcp_session.call_tool("get_poi_details", arguments={"poi_id": pid}) for pid in unique_ids]
                    
                    # return_exceptions=True prevents one bad tool call from crashing the whole batch
                    detail_responses = await asyncio.gather(*tasks, return_exceptions=True)

                    enriched_pois = []
                    for i, resp in enumerate(detail_responses):
                        
                        # 🆕 THE FIX: Use BaseException to satisfy the strict type checker
                        if isinstance(resp, BaseException):
                            logger.error(f"❌ X-RAY: Tool call failed for ID {unique_ids[i]}: {resp}")
                            continue
                            
                        try:
                            # Now the linter knows 'resp' is definitely a successful tool result
                            if i == 0:
                                logger.info(f"👉 X-RAY: Raw Tool Response [0]: {resp.content[0].text[:200]}...")
                                
                            data = json.loads(resp.content[0].text)
                            
                            if data.get("success") and data.get("result"):
                                enriched_pois.append(data["result"])
                            else:
                                logger.warning(f"⚠️ X-RAY: Tool succeeded, but missing 'success' or 'result' key: {data.keys()}")
                                
                        except Exception as e:
                            logger.error(f"❌ X-RAY: JSON Parse Error on enrichment: {e}")

                    tool_chain[-1]["status"] = "success"
                    tool_chain[-1]["summary"] = f"Successfully enriched {len(enriched_pois)} POIs with full metadata."
                    logger.info(f"👉 X-RAY: Finished enriching {len(enriched_pois)} POIs.")
                    
                current_step += 1

        # --- STEP 4: GEMINI SYNTHESIS ---
        poi_context = json.dumps(enriched_pois, indent=2)

        # (Your mega_prompt remains exactly the same here...)
        mega_prompt = f"""

        You are the 'Travel Lung Tung' backend routing engine.

        Your task is to generate a personalized {request.duration_days}-day itinerary based on the user's requirements and the provided database POIs.

        

        # USER PROFILE & REQUIREMENTS

        - City: {request.current_city}

        - Target Area: {request.target_district}

        - Travel Style: {request.travel_type}

        - Group Size: {request.num_travelers} pax

        - Budget: {request.budget_range}

        - Start Date: {request.start_date}

        - Special Requests: "{request.user_description}"



        # AVAILABLE PLACES DATABASE

        You MUST ONLY select places from the JSON array below. 

        ```json

        {poi_context}

        ```



        # OUTPUT INSTRUCTIONS

        You MUST output ONLY a valid JSON object. Do not include markdown formatting like ```json.

        Map the selected POIs into the exact schema shown below.

        

        Rules:

        1. "id" and "uid": Generate random unique string identifiers.

        2. "start_poi_id" and "end_poi_id": Use the IDs of the first and last stops.

        3. "total_estimated_budget": Calculate a realistic total budget (in VND) based on the user's budget range.

        4. "visit_time" and "end_time": Must be strictly formatted as ISO 8601 strings (e.g., "YYYY-MM-DDTHH:MM:SS+07:00"). Ensure logical travel times between stops.

        5. "budget": Estimate a realistic cost in VND for each specific stop.

        6. POI Mapping: Map the data from the AVAILABLE PLACES into the "poi" object. If data like "longitude", "latitude", "contact_info", or "menu" is missing from the provided POI data, set the value to `null` or `[]`.

        

        # REQUIRED JSON SCHEMA

        {{

          "id": "string",

          "uid": "string",

          "start_poi_id": "string",

          "end_poi_id": "string",

          "total_estimated_budget": float,

          "stops": [

            {{

              "date": "YYYY-MM-DD",

              "visit_time": "ISO 8601",

              "end_time": "ISO 8601",

              "description": "1-sentence explanation of why this fits the user's vibe.",

              "budget": float,

              "poi": {{

                "id": "string",

                "name": "string",

                "poi_categories": [{{ "id": "string", "name": "string", "context": "string" }}],

                "tag": {{ "id": "string", "name": "string" }},

                "longitude": float or null,

                "latitude": float or null,

                "address": {{

                  "street_name": "string or null",

                  "ward": "string or null",

                  "district": "string or null",

                  "city": "string or null",

                  "nation": "string or null"

                }},

                "contact_info": {{ "phone_number": "string", "fanpage": "string", "website": "string" }} or null,

                "operation_time": "string or null",

                "rating": {{ "google_maps": float, "tripadvisor": float }} or null,

                "menu": [{{ "id": "string", "price": float, "product_name": "string" }}]

              }}

            }}

          ]

        }}

        """

        payload = {
            "model": "gemini-2.5-pro",
            "messages": [{"role": "user", "content": mega_prompt}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"} 
        }
        
        tool_chain.append({"step": current_step, "tool": "Gemini Synthesis", "status": "processing", "summary": "Generating JSON Schema..."})
        
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            response = await http_client.post(GEMINI_URL, headers=get_gemini_headers(), json=payload)
            response.raise_for_status()
            
            raw_response = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            
            try:
                clean_json = re.sub(r'```json\s*', '', raw_response)
                clean_json = re.sub(r'```', '', clean_json).strip()
                final_itinerary_json = json.loads(clean_json)
            except json.JSONDecodeError:
                return {"reply": {"error": "AI failed to generate valid JSON."}, "tool_chain": tool_chain}
            
            tool_chain[-1]["status"] = "success"
            
            # Context Handoff Note
            if request.session_id not in chat_history:
                chat_history[request.session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
            chat_history[request.session_id].append({
                "role": "assistant", 
                "content": f"[System: Automatically generated a {request.duration_days}-day itinerary with {len(final_itinerary_json.get('stops', []))} stops.]"
            })

            return {
                "reply": final_itinerary_json,
                "tool_chain": tool_chain
            }

    except Exception as e:
        import traceback
        logger.error(f"General Loop Error: {type(e).__name__} - {repr(e)}")
        logger.error(traceback.format_exc()) 
        return {"reply": "Something went wrong. Check logs.", "tool_chain": tool_chain}


async def execute_chitchat(session_id: str, user_message: str) -> str:
    if session_id not in chat_history:
        chat_history[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
    chat_history[session_id].append({"role": "user", "content": user_message})
    
    payload = {
        "model": GEMINI_MODEL,
        "messages": chat_history[session_id],
        "temperature": 0.7,
        "max_completion_tokens": 500
    }
    
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        try:
            response = await http_client.post(GEMINI_URL, headers=get_gemini_headers(), json=payload)
            response.raise_for_status()
            
            assistant_msg = response.json().get("choices", [{}])[0].get("message", {})
            assistant_msg = {k: v for k, v in assistant_msg.items() if v is not None}
            chat_history[session_id].append(assistant_msg)
            
            return assistant_msg.get("content", "")
        except httpx.ReadTimeout:
            logger.error(f"Gemini timed out during chitchat for session {session_id}")
            return "I'm thinking a bit slowly today! Could you say that again?"


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    logger.info(f"User: {request.message}")
    
    intent = await analyze_intent(request.message)
    logger.info(f"Orchestrator classified intent as: {intent}")
    
    if intent == "CHITCHAT":
        logger.info("Bypassing Agent Loop. Using lightweight chitchat.")
        final_reply = await execute_chitchat(request.session_id, request.message)
    else:
        logger.info("Engaging full Agent Loop with FastMCP Tools.")
        final_reply = await execute_agent_loop(request.session_id, request.message)
        
    return {"reply": final_reply}