# System Overview (Memgraph SoT Setup)

The POI Service is a strictly bounded context. It owns the location data (POIs, Categories, Tags) and nothing else. Because Memgraph is the sole SoT for this domain, the service acts as a direct validation and routing layer on top of your graph database.

Core Responsibilities:
- AI Routing Gateway: Serve constrained candidate pools to the AI Service via FastMCP.
- Domain Command Center: Handle all administrative creations, updates, and deletions of POIs directly into Memgraph, guaranteeing ACID compliance for the graph.
- High-Throughput Ingestion: Process bulk OTA data via chunked Cypher transactions without choking the read-heavy routing queries.
- Architectural Note on Firebase: With this setup, Firebase operations (saving Itineraries and Stops) strictly belong to the Core Backend / Itinerary Service. The POI Service does not need to talk to Firebase at all.
2. Refined Directory Structure

This reflects your actual workspace with the typos corrected and the missing routing.py service added to complete the CQRS pattern.
```
poi_service/
├── app/
│   ├── api/
│   │   ├── mcp/
│   │   │   ├── __init__.py
│   │   │   └── tools.py               # FastMCP tool definitions (@mcp.tool)
│   │   └── rest/
│   │       └── v1/
│   │           ├── endpoint_ingestion.py
│   │           ├── endpoint_management.py
│   │           └── endpoint_routing.py
│   ├── core/
│   │   ├── base/
│   │   ├── config/
│   │   │   └── settings.py
│   │   ├── domain/
│   │   │   ├── enum.py
│   │   │   └──  entities.py   
|   |   |    
│   │   ├── exceptions.py              
│   │   └── interfaces/                
│   │       └── repositories.py
│   ├── infrastructure/
│   │   └── db/
│   │       ├── database/
│   │       │   └── connector.py
│   │       └── repositories/
│   │           └── memgraph.py        # Sole source of truth for POIs
│   ├── services/
│   │   ├── ingestion.py               # Batch operations
│   │   ├── management.py              # Single-entity Commands (Writes)
│   │   └── routing.py                 # AI Queries (Reads) - Added to complete CQRS
│   └── main.py                        # FastAPI + FastMCP mount point
├── pyproject.toml
└── .env
```
## 3. Component Design & Service Logic

**With the dual-write requirement removed, your service layer becomes much cleaner.**
### A. services/management.py (The Command Logic)

This service ensures bad data never enters the graph. It sits between endpoint_management.py and MemgraphPOIRepository.

- Validation: Runs Pydantic .model_validate() on incoming JSON.
- Sanitization: Normalizes strings (e.g., standardizing "Ho Chi Minh" vs "HCMC" to ensure accurate Cypher matching).
- Execution: Calls repository.create() or repository.update(). If Memgraph throws a constraint error, this service catches it and raises a custom HTTP 400 error.

### B. services/routing.py (The Query Logic)

This is a dedicated read-only service optimized for the AI Agent.
- Execution: Calls repository.get_routing_candidates().
- Formatting: Strips out backend-only fields (like hidden admin tags or internal node IDs) and formats the data into a clean, token-efficient JSON dictionary payload for the LLM.

### C. services/ingestion.py (The Bulk Logic)

Handles the OTA datasets.

- Batching: Slices massive JSON/CSV arrays into chunks (e.g., 500 records per chunk).

- Execution: Passes chunks to a custom batch_create() method in your repository that uses Cypher UNWIND.