# ✈️ TRAVEL VO LO - Smart Travel Assistant Agent System

> **Engineering handover, 29/10/2026:** Start with [the intern knowledge-transfer package](docs/handover/2026-10-29/README.md) and [agent onboarding](START_HERE_FOR_AGENTS.md). The historical overview below is not an acceptance report; current implementation gaps, approved scope and runtime evidence are documented in the handover.

**Travel Vo Lo** is an advanced, AI-driven Smart Travel Assistant and Online Travel Agency (OTA) platform. Designed to eliminate the overwhelming and time-consuming process of trip planning, Travel Vo Lo leverages Multi-Agent Systems, Large Language Models (LLMs), and Graph RAG technologies to craft highly personalized, risk-free, and optimized travel experiences.

---

## ✨ Key Features

### 1. OTA Features (Online Travel Agency)

A fully functional booking and travel management engine that allows users to securely book flights, accommodations, and local experiences directly through the platform.

### 2. AI-Driven Capabilities

Our AI ecosystem successfully handles all user concerns regarding the trip planning process:

* 🤖 **Smart Customer Service Agent**
An intelligent conversational agent that provides precise, contextual information about destinations and Points of Interest (POIs). It does the heavy lifting of travel research so users don't have to.
* 🗺️ **"Vi Vu" - Intelligent Itinerary Planner**
The flagship feature that differentiates Travel Vo Lo from traditional OTA services. By combining user preferences, LLM reasoning, and a smart planning algorithm, "Vi Vu" generates highly detailed, utility-maximizing itineraries. Users can simply pack their bags and enjoy the trip without worrying about where to go or how long to stay.
* 🛡️ **Proactive Risk Management**
Powered by a real-time travel database, the agent anticipates potential risks (e.g., weather issues, closures) during the trip. It proactively suggests alternative plans to minimize the chance of disruptions, ensuring a seamless travel experience.

---

## 🏗️ System Architecture & Core Modules

The backbone of Travel Vo Lo is a fully integrated **Multi-Agent System** operating on top of a robust **RAG (Retrieval-Augmented Generation)** database.

### Multi-Agent Backbone

* **Graph RAG for Ground Truth:** Ensures accurate, hallucination-free AI responses using verified travel data.
* **Relationship Modeling (Graph):**
* `USER_BEHAVIOR` $\rightarrow$ `VIBE` (Amenity, Tourism, Shop) or `TAG` (Feeling) driven by robust custom weight functions.
* `POI` $\rightarrow$ `POI` spatial and conceptual relations, fully mapped for: `NEAR_BY`, `SEQUENTIAL_FLOW`, and `SIMILAR_VIBE`.


* **POI Service:** Handles automated batch ingestion for POI data and GeoJSON files, seamlessly integrated with routing services to manage and structure all Point of Interest information.

### Dataset Aggregation

* **OpenStreetMap (OSM):** A highly structured foundational dataset of over 6,000 local POIs.
* **Traveloka & SearchNX Data:** Successfully integrated to enrich POI descriptions, reviews, and contextual data.

---

## 🚀 Technical Achievements & Capabilities

The system architecture has been fully realized with the completion of all core data models, interaction services, and AI integrations:

* **Multi-Agent Orchestration:** Seamless operation between the RAG database, crawling modules, and intelligent agent logic to answer complex user queries.
* **Knowledge Graph Integration:** Complete extraction of crawled JSON data into **Memgraph**, establishing a robust Knowledge Graph.
* **Vector Database:** Fully vectorized `seo_article` content using advanced embedding models for the Vector RAG database.
* **"Vi Vu" Engine Deployment:** Successful integration of LLM user preference grading, the Smart Planning Algorithm, and Graph RAG grounding for itinerary generation.
* **Data Models & Schemas:** Finalized Graph Entities Model Schemas, Relationship Schemas, and Repositories for each entity, fully supporting comprehensive CRUD operations.
* **Search Infrastructure:** Core search module deployed and highly optimized for rapid data retrieval.
* **UI/UX:** Complete and intuitive UI Schema implemented for the Trip Planning interface.
