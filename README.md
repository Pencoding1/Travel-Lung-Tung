# TRAVEL VO LO - SMART TRAVEL ASSISTANT AGENT SYSTEM
## KEY FEATURES
Describe the key features of the Travel Vo Lo system.
### 1. OTA FEATURES
NOTE: Will be filled later
### 2. AI-DRIVEN FEATURES
- [ ] Customer Service Agent: provide useful information about destinations and POI to user. Release the user with overhelming researching process.
- [ ] Vi vu feature: based on user's preference and leverage the LLM's cooperating with smart planning algorithm to generate a detail trip itinerary. The provided trip will maximize the user's utility, allow them enjoy the trip without considering which place to go and for how long.
- [ ] Risks management: Based on the trip user are going to, with information gathered on the real-time updated travel database. The agent could predict risk and suggest alternative plan that could lower the chance of broken point during the trip. This feature with the Vi Vu allow the system to take over all user concerns about trip planning process, release them from time consumming preparing for a trip.
## DEVELOPMENT PROGRESS
### COMPLETE:
- [ ] ...
### TODO:
- [ ] Multi-agent system: the back-bone of the AI features. The goal is a system could query from RAG database with travel data gathering during the crawling process to answer user's questions:
    - [x] Crawling module
    - [ ] **Relationship Modeling**:
        - [ ] USER_BEHAVIOR $\rightarrow$ VIBE (or category (amenity, tourism, shop)) or Tag (the feeling):
            - [ ] Weights function.
        - [ ] POI $\rightarrow$ POI: 
            + [ ] NEAR_BY
            + [ ] SEQUENTIAL_FLOW
            + [ ] SIMILAR_VIBE
    - [ ] **Ingestion Module**:
        + [x] Build the batch ingestion for POI data.
        + [ ] Verify logic of AI's code.
        + [x] Build ingestion pipeline for the geojson file.
        + [ ] Routing service.
    - [ ] RAG database module
    - [x] Agent system architecture (draft)
    - [ ] The system
- [ ] **Search Module.**
- [ ] **Dataset (both from Traveloka & Openstreetmap + Searchnx)**:
    + [x] OSM dataset: +6000 Local POI with high structure from OSM. However they lack of explicit description.
    + [ ] Traveloka: ... 
- [ ] Vi vu feature: the key difference of the system with others OTA services. The feature has three components: 
    - [ ] LLM's grading based on user preferences.
    - [ ] Smart Planning Algorithm.
    - [ ] Graph RAG for grounding truth.
## DEV's NOTE
### DEVELOPMENT TODO LIST
- [ ] UI's schema for Trip planning.
- [ ] Complete data models and interaction service to manipulating the data.
    - [x] Graph Entities Model Schema.
    - [x] Basic CRUD on Graph.
    - [ ] Relationships Schema.
    - [x] Repositories for each entity.
- [ ] After that build the data ingestion process to extract data from the crawled json file to knowledge graph using memgraph and vectorize `seo_article` using embedding model for the Vector RAG database. 
**DEADLINE: 15/3/2026**