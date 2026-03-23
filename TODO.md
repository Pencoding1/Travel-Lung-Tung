# NOTE
<font size="5">Since the todo list only has been created at March 20 2026 so all previous tasks will be set as completed and only provide the result report.</font>
# TODO LIST:
<div>
<font size="4">

- [x] Crawler module:
- [ ] Data Ingestion Module
    - [x] POI Ingestion
    - [ ] Location (district, city) Ingestion
    - [ ] Category (Tag, Category) Ingestion
    - [ ] Product (menu's product) Ingestion
    - [ ] Data from the Traveloka Ingestion
- [ ] Graph Database:
    - [ ] Design Relationship between nodes.
- [ ] Routing Module:
    - [x] Host Graphhopper server
    - [ ] Wire the Graphhopper to the backend and plays as a serivce.
- [ ] Itinerary Generation Agent Module 
- [ ] The Agentic Response Module 
- [ ] Agentic External Knowledge Gathering Module:
    - [ ] Weather
    - [ ] Destination Information
    - [ ] Real-time update
- [ ] The Auto Booking Module
    - [ ] Define bussiness skills set.
    - [ ] Constraints evaluation.
- [ ] The Core Bussiness Module
    - [ ] Booking&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
    - [ ] User&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;| CORE MVP
    - [ ] Product&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
</font> 
</div>

# March 20 2026
<font size="4">

- [ ] Graph Relationship: First implement the NEAR_BY (POI, City, District) and LIKE (USER_BEHAVIOR $\rightarrow$ TAG | CATEGORY)
    - [x] ~~Location (district, city) Ingestion:~~
        - ~~[x] Reconstruct the Address information:~~
            - ~~[x] **SELF-POINTED OF POI**~~
        - ~~[x] Hierachical address aggretion for geometry POI clustering.~~
        ~~- [x] As the Routing ready add NEAR_BY path with distance propetry using Haversine formula.~~
    - [ ] Product (menu's product) Ingestion
        - [ ] Add a dummy product with id marked as fake to create a based schema with OFFER
        - [ ] Handle duplicate product.
    - [ ] USER_BEHAVIOR Relationships: 
        - [ ] LIKE for POI and PRODUCT with weighting property
        - [ ] VISITED for POI with rating property
    - [ ] SIMILAR relationship using Jaccard Similarity.
    - [ ] OFTEN_VISITED_AFTER with probility property
    - [ ] Data from the Traveloka Ingestion (Actually can skip for now).
- [ ] Routing Service: Implement the service that connect to Graphhopper server to get the route.
- [ ] **BUG: GET POI still has Neo4j BUG with the log contain the ORDER thing.**
</font>