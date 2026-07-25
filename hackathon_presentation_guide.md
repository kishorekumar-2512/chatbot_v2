# Hackathon Presentation Guide: AI-Powered Database Assistant (Chatbot V2)

This guide breaks down the advanced AI and software engineering techniques used in this project in **simple, presentation-ready terms**. Use these explanations to wow the judges in Hackathon Round 1!

---

## 🌟 Pitch (The "Why")
Most AI database assistants fail because they try to feed the entire database schema (234 tables!) to the LLM. This leads to **slow response times, high API costs, and hallucinations (incorrect queries)**. 
Our project solves this by introducing a **5-Layer Retrieval-Augmented Generation (RAG) and self-healing pipeline** that selects the exact right tables, figures out how to join them, validates query safety, and corrects itself if something goes wrong.

---

## 🛠️ The 5 Core Techniques (Explained Simply)

### 1. Hybrid Search for Table Retrieval (RAG)
* **The Problem:** We have 234 tables in our database. We cannot send all of them to the AI because it exceeds context limits and confuses the model.
* **The Solution:** We only send the tables relevant to the user's question. We use two types of search and merge them:
  * **Semantic (Dense) Search:** Uses vector embeddings (`ChromaDB` + `sentence-transformers`) to understand the *meaning* of the query (e.g. "technicians" matches the `user` table).
  * **Keyword (Sparse) Search:** Uses BM25 search to look for *exact words* (e.g. searching for a column name like `serial_number`).
  * **Reciprocal Rank Fusion (RRF):** Merges the results of both searches to give us the absolute best subset of tables.
* **Hackathon Keyword:** *Hybrid Retrieval, Semantic Search, ChromaDB Vector Indexing.*

---

### 2. Graph-Based Joins (GraphRAG)
* **The Problem:** Once the AI retrieves the relevant tables (e.g. `managed_device` and `alerts`), it doesn't know how to join them together. The AI often guesses the join conditions wrong, resulting in broken SQL.
* **The Solution:** We modeled the database schema as a **directed network graph** using the `NetworkX` library in Python. 
  * The tables are the **nodes**, and the foreign key relationships are the **edges**.
  * When the user asks a question, our algorithm calculates the **shortest path** between the retrieved tables on the graph and automatically generates the precise `JOIN` paths (e.g. `JOIN alerts ON alerts.device_id = managed_device.id`). 
  * We inject these join paths as "hints" into the AI's prompt.
* **Hackathon Keyword:** *GraphRAG, NetworkX Pathfinding, Schema Relationship Mapping.*

---

### 3. Self-Correcting & Self-Healing Pipeline (Corrective RAG)
* **The Problem:** Sometimes the generated SQL query contains syntax errors or targets non-existent columns. Returning an error message to the user is a terrible UX.
* **The Solution:** We built a self-healing loop:
  1. **Pre-execution validation:** We run the SQL query through a custom parser to ensure it only performs `SELECT` queries (no database deletion/manipulation) and check for syntax.
  2. **Execution & Reflexive Debugging:** If the database returns an error, we intercept it, package it, and feed it back to the LLM. 
  3. **AI Self-Reflection:** The LLM inspects the error message (e.g. "Column 'x' does not exist"), corrects the SQL, and tries running it again (up to 3 times).
* **Hackathon Keyword:** *Self-Correction loop, Reflexive AI agent, SQL Validation.*

---

### 4. Circuit-Breaker LLM Routing (High Availability)
* **The Problem:** If our primary LLM provider (e.g. Groq/OpenAI) goes down or hits rate limits during a hackathon demo, the application freezes.
* **The Solution:** We implemented a **Circuit Breaker** pattern:
  * The system polls the health of LLM providers.
  * If the primary model starts failing repeatedly, the circuit opens, and the system instantly routes the user's questions to a fallback model (e.g. DeepSeek, Claude, or a local Ollama instance) without the user ever noticing.
* **Hackathon Keyword:** *High Availability, Failover Routing, Circuit Breaker Pattern.*

---

### 5. Multimodal Vision-to-SQL
* **The Problem:** Sometimes, users don't know how to ask their question in words, but they have a screenshot of a dashboard or spreadsheet they want to reproduce.
* **The Solution:** We integrated a Vision model (Gemini Vision) to analyze images.
  * The user uploads a chart or screenshot.
  * The Vision LLM extracts the metrics, groups, and filters visible in the chart, translates them into a query intent, and injects it into our text-to-SQL pipeline to reconstruct the chart against live data.
* **Hackathon Keyword:** *Multimodal AI, OCR Data Extraction, Vision Agents.*

---

## 🎨 Frontend & UX Excellence
* **Server-Sent Events (SSE) Streaming:** Displays the AI's "thought process" live (using `<think>` blocks), making the app feel alive and fast.
* **Auto-Charting:** An algorithm inspects the shape of the query results and automatically picks the best visualization (Bar, Area, Line, Donut, etc.) using `Plotly.js`.
* **Interactive Schema Explorer:** Allows users to browse tables, columns, real database data types, and AI-generated descriptions directly from the sidebar.
* **Network-Level Abort:** Clicking "Stop generating" sends an abort signal to the browser's HTTP fetch call, instantly closing the server stream to conserve tokens.

---

## 💡 Hackathon Demo Tips
1. **Show, Don't Just Tell:** Start by showing the **Schema Explorer** on the right sidebar. Expand a table to show the data types and column descriptions (prove that the AI successfully documented all 2,723 columns!).
2. **Break it on Purpose:** Ask a question, let the SQL run. Then, show the **Trace** tab to show the latency, LLM confidence, and number of correction loops it took.
3. **Upload an Image:** Drag and drop a simple chart or data table screenshot and watch the assistant write the SQL and render a live chart from the database!
