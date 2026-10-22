# System inventory

Audit date: 2026-10-15. Status: source inspection complete for major services; runtime verification pending. This inventory records inspected implementation, not README claims.

| Component | Inspected implementation | Verification and gaps |
|---|---|---|
| crawler_service | FastAPI `/api/v1/crawl`, authenticated router; Crawl4AI discovery/detail pipeline; Traveloka schema extraction and HTML-to-Markdown preprocessing | `app/main.py`; `app/pipelines/crawling/crawling.py:91,191` explicitly lack database persistence. Other preprocessors are stubs. No verified acquisition-to-POI bridge. |
| POI_service REST | Pydantic graph entities, management services, canary batch ingestion, background chunks and SSE | `app/core/domain/graph_entities.py:154`; `app/core/services/ingestion.py`; `app/api/rest/v1/endpoint_ingestion.py`. Domain accepts unrestricted coordinates and mutates supplied IDs. Background completion does not distinguish failed chunks. |
| POI_service graph | Neo4j driver, transaction unit of work, Cypher repositories, spatial updater | `app/core/infrastructure/db/uow.py`; `repositories/memgraph.py:181`. Longitude filter is invalid as a necessary spherical-distance condition. Graph data not read or modified. |
| POI_service MCP | Five tools: details, route, explore, categories, location resolution | `app/api/mcp/tools.py:37–260`. Vector document repository is explicitly unimplemented. Route silently omits missing POIs; advertised foot/bike profiles absent from active GraphHopper configuration. |
| ai_service | FastAPI `/chat`, `/generate_itinerary`; Gemini intent classification and MCP ReAct loop; candidate retrieval, enrichment, LLM JSON synthesis | `main.py`; `domains/payloads.py`. In-memory dictionary exists, but compression and connected long-term profile influence are not established. No deterministic final itinerary validator observed. Empty candidate path leaves `enriched_pois` undefined. |
| backend_service | Domain models, abstract repositories, Firebase itinerary/stop persistence | `app/core/infrastructure/repository/firebase.py`. `app/api/rest/v1/endpoint_itinerary.py` is empty; no operational application persistence API demonstrated. |
| shared_lib | Shared Pydantic schemas, exceptions and logging | `travel_shared/schemas.py`, `exceptions.py`, `utils/logging_setup.py`. Imports mix `travel_shared` and `shared_lib.travel_shared`; packaging needs tests. |
| graphhopper | Dockerfile and HCMC OSM PBF; only car profile active | `Dockerfile`, `data/config.yml:34`. Image uses latest. No running routing engine verified. |
| Compose | Memgraph, Lab, GraphHopper, POI REST/MCP, AI and ngrok | Crawler/backend absent. Hard-coded tunnel credential; optional Ollama service commented out while AI references its hostname. Docker engine unavailable. |

Existing test files `POI_service/test_pipeline.py` and `graphhopper/test.py` are live scripts, not safe comprehensive isolated suites. Do not run ingestion against historical data without a snapshot. Existing virtualenv references a missing interpreter. Baseline tests are being prepared in a separate environment.

Proposal source is `C:/Users/duyan/Downloads/12.docx`, extracted under `docs/project/THESIS_PROPOSAL_EXTRACT.txt`. Existing crawling findings are historical observations dated 2026-10-04/05, not current authorization or acquisition evidence.

## Repaired implementation snapshot — 2026-10-16

The inventory table above is the initial audit baseline. For current architecture use ARCHITECTURE_AS_IS.md and EVIDENCE_REGISTER E013–E039: stablePOIIDs/coordinatevalidation, corrected spatial/ingestion/MCP/grounding contracts, authenticated bounded memory and endpoint-integrated deterministic planner now have independent mocked tests. Offline evaluator reporting and immutable experimental collector local contracts are accepted; actualliveprovider/graph/routes/humans remainunverified. OC026acquisitionstatecorrection,OC025figureR1 andOC027backendworkflow are active/unaccepted. No table baseline defect should be presented as still present without checking current source.
