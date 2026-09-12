# AI Database Text-to-SQL Engine v2 — Complete Architecture, Pipelines & Flowcharts

> **Comprehensive Visual Guide to the System Architecture, 6-Layer Accuracy Pipeline, Multi-Tenant Security, and Execution Workflows**  
> *Project: `chatbot_v2` | Single-Server Text-to-SQL Engine (Port 8000)*

---

## 📑 Table of Contents

1. [High-Level System Architecture](#1-high-level-system-architecture)
2. [End-to-End Request / Response Lifecycle](#2-end-to-end-request--response-lifecycle)
3. [The 6-Layer Accuracy Pipeline](#3-the-6-layer-accuracy-pipeline)
   - [Layer 1: Query Intelligence Engine](#layer-1-query-intelligence-engine)
   - [Layer 2: Hybrid Retrieval & RAG Pipeline](#layer-2-hybrid-retrieval--rag-pipeline)
   - [Layer 3: Schema Graph Engine (GraphRAG)](#layer-3-schema-graph-engine-graphrag)
   - [Layer 4: Context Assembly & Dynamic Prompt Budgeting](#layer-4-context-assembly--dynamic-prompt-budgeting)
   - [Layer 5: LLM Orchestrator & Multi-Provider Circuit Breakers](#layer-5-llm-orchestrator--multi-provider-circuit-breakers)
   - [Layer 6: AST Security Validation & Self-Correction Feedback Loop](#layer-6-ast-security-validation--self-correction-feedback-loop)
4. [Multi-Turn Conversational Context Engine](#4-multi-turn-conversational-context-engine)
5. [Multi-Tenant Security & AST Validation Architecture](#5-multi-tenant-security--ast-validation-architecture)
6. [Offline Database Introspection & ChromaDB Vector Indexing](#6-offline-database-introspection--chromadb-vector-indexing)
7. [Component & Directory Cross-Reference](#7-component--directory-cross-reference)

---

## 1. High-Level System Architecture

The following diagram illustrates the high-level boundary of the **Chatbot v2** platform, mapping external clients, gateway security, core pipeline engines, in-memory caches, and upstream model providers.

```mermaid
graph TB
    subgraph Clients["External Clients & Consumers"]
        Postman["Postman / API Clients"]
        Frontend["Web Dashboard / Frontend"]
        Cognito["OIDC / Cognito / Okta IdP"]
    end

    subgraph Server["FastAPI Application Server (:8000)"]
        subgraph Gateway["API Gateway & Middleware Layer"]
            SlowAPI["SlowAPI Rate Limiter\n(10 req/min/IP)"]
            AuthMiddleware["JWT / JWKS Auth Validator\n(backend/auth.py)"]
            JWKSCache[("JWKS In-Memory Cache\nTTL: 6 Hours")]
        end

        subgraph CoreEngine["Core Text-to-SQL Engine (backend/main.py)"]
            PipelineManager["generate_sql_with_retry()\nOrchestrator"]
            L1["L1: Query Intelligence\n(backend/query_intelligence.py)"]
            L2["L2: Hybrid Retrieval\n(backend/hybrid_retriever.py)"]
            L3["L3: Schema Graph Engine\n(backend/schema_graph.py)"]
            L4["L4: Context Assembly & Budget\n(_trim_prompt_to_budget)"]
            L5["L5: LLM Orchestrator\n(backend/llm_orchestrator.py)"]
            L6["L6: AST & Security Validator\n(backend/sql_validator.py)"]
            SelfCorrection["Self-Correction Feedback Loop\n(backend/self_correction.py)"]
        end

        subgraph MemoryStores["Local Storage & Knowledge Bases"]
            ChromaStore[("ChromaDB Vector Store\n(./embeddings/chroma_store)")]
            BM25Index[("In-Memory BM25 Corpus\n(Tokenized DDL Descriptions)")]
            SchemaGraphObj[("NetworkX DiGraph\n(234-Table FK Constraints)")]
            BreakerStore[("Circuit Breaker State Store\n(Per-Tenant / Provider Locks)")]
        end
    end

    subgraph LLMProviders["Upstream LLM Provider Pool"]
        GroqAPI["Groq Cloud API\n(openai/gpt-oss-120b / llama-3.3-70b)"]
        GeminiAPI["Google Gemini API\n(gemini-2.5-flash)"]
        OllamaAPI["Local Ollama Server\n(qwen2.5-coder:7b / num_ctx: 8192)"]
    end

    subgraph Database["Underlying Enterprise Database"]
        PostgresDB[("PostgreSQL Database\n(intern_db / 234 Tables)")]
    end

    %% Client flows
    Postman -->|"POST /chat"| SlowAPI
    Frontend -->|"POST /chat"| SlowAPI
    Postman -->|"GET /health"| Server
    Cognito -.->|"Fetch JWKS Keys"| AuthMiddleware
    AuthMiddleware <--> JWKSCache

    %% Gateway to Engine
    SlowAPI --> AuthMiddleware
    AuthMiddleware -->|"Validated Tenant / Org ID"| PipelineManager

    %% Pipeline Internals
    PipelineManager --> L1
    L1 --> L2
    L2 <--> ChromaStore
    L2 <--> BM25Index
    L2 --> L3
    L3 <--> SchemaGraphObj
    L3 --> L4
    L4 --> L5
    L5 <--> BreakerStore
    L5 --> GroqAPI
    L5 -.->|"Fallback 1"| GeminiAPI
    L5 -.->|"Fallback 2"| OllamaAPI
    L5 --> L6
    L6 -->|"Failure / Unknown Cols"| SelfCorrection
    SelfCorrection -->|"Diff Retry Prompt"| L5
    L6 -->|"Pass"| PipelineManager
    PipelineManager -.->|"Store Successful Example"| ChromaStore

    %% Offline Indexing
    PostgresDB -.->|Schema Introspection & DDLs| ChromaStore
```

---

## 2. End-to-End Request / Response Lifecycle

Every HTTP request to `POST /chat` goes through strict validation, context retrieval, multi-strategy ranking, multi-model execution, and security gating.

```mermaid
sequenceDiagram
    autonumber
    actor Client as Client (Frontend / Postman)
    participant API as FastAPI Router (backend/main.py)
    participant Auth as JWT Auth (backend/auth.py)
    participant L1 as L1: Query Intelligence
    participant L2 as L2: Hybrid Retrieval (BM25 + Chroma)
    participant L3 as L3: Schema Graph (NetworkX)
    participant L4 as L4: Context & Budget
    participant L5 as L5: LLM Orchestrator
    participant Breaker as Circuit Breakers
    participant LLM as Provider (Groq / Gemini / Ollama)
    participant L6 as L6: AST & Org Validator
    participant Store as ChromaDB Example Store

    Client->>API: POST /chat { question, context, org_id }
    API->>Auth: Verify JWT Token (if REQUIRE_AUTH=true)
    Auth-->>API: AuthenticatedUser(org_id)
    
    API->>API: Check is_complex_query(question) & is_followup_question(question)
    
    API->>L1: build_query_context(question)
    L1-->>API: { intent, entities, time_filter, skeleton }
    
    API->>L2: retrieve_tables(question, top_k=8 or 12)
    L2->>L2: Dense Chroma query + Sparse BM25 scoring
    L2->>L2: Reciprocal Rank Fusion & Tiering
    L2-->>API: { tables_used, schema_text, similarity_scores }

    API->>L3: force_anchor_tables() + expand_related_tables()
    API->>L3: get_join_hints(tables_used)
    L3-->>API: Shortest Path BFS JOIN paths
    
    API->>L4: Assemble prompt & _trim_prompt_to_budget()
    L4-->>API: Budgeted prompt (< MAX_PROMPT_TOKENS)

    loop Retry Loop (Attempt 1 to 3)
        API->>L5: generate(prompt, excluded_providers)
        L5->>Breaker: allow(provider)?
        Breaker-->>L5: True / False
        L5->>LLM: POST /chat/completions or /generateContent
        LLM-->>L5: Raw LLM response text
        L5-->>API: raw text, model_used, provider_used
        
        API->>L6: extract_sql(raw_no_think)
        API->>L6: validate_sql(sql, known_tables, known_columns)
        API->>L6: validate_org_security(sql, org_id)

        alt SQL is Valid & Passes Org Security
            API->>Store: store_successful_example(question, sql)
            API-->>Client: 200 OK { sql, model_used, attempts, tables_used }
        else Validation Failed
            API->>API: failed_attempts.append((sql, error))
            API->>API: rejected_providers.add(provider_used)
            API->>API: build_retry_context() with diff
        end
    end

    alt Max Attempts Exhausted
        API-->>Client: 400 Bad Request: "Could not generate working SQL after 3 attempts"
    end
```

---

## 3. The 6-Layer Accuracy Pipeline

### Layer 1: Query Intelligence Engine
**File:** [`backend/query_intelligence.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/query_intelligence.py)

Classifies natural language questions into formal query intents, maps keywords to database tables, extracts exact filter values, and prepares a deterministic SQL skeleton.

```mermaid
flowchart TD
    UserQuery["User Question String\n(e.g., 'top 5 unpatched windows laptops in last 30 days')"] --> IntentClassifier{"classify_intent(q)\nRegex Match"}

    IntentClassifier -->|"how many / count"| IntentCount["Intent: COUNT\nHint: COUNT(DISTINCT id)"]
    IntentClassifier -->|"top N / highest / most"| IntentTopN["Intent: TOP_N\nHint: ORDER BY metric DESC LIMIT N"]
    IntentClassifier -->|"trend / over time / monthly"| IntentTrend["Intent: TREND\nHint: DATE_TRUNC('month', col)"]
    IntentClassifier -->|"average / sum / total"| IntentAgg["Intent: AGGREGATE\nHint: SUM/AVG/MIN/MAX with GROUP BY"]
    IntentClassifier -->|"compare / vs / versus"| IntentComp["Intent: COMPARE\nHint: GROUP BY comparison dimension"]
    IntentClassifier -->|"is there / does have"| IntentExists["Intent: EXISTS\nHint: COUNT() > 0 or EXISTS()"]
    IntentClassifier -->|Fallback / No Match| IntentList["Intent: LIST\nHint: SELECT DISTINCT ... ORDER BY"]

    UserQuery --> EntityExtractor["extract_entities(question)"]
    EntityExtractor --> TableKeywords["TABLE_KEYWORDS Lookup\n(Maps 'laptop' -> 'managed_device',\n'unpatched' -> 'device_missing_patch')"]
    EntityExtractor --> ColumnValues["COLUMN_VALUE_HINTS Lookup\n(Maps 'windows' -> platform=1,\n'active' -> status=1)"]
    EntityExtractor --> TimeFilter["Temporal Regex Parser\n(Matches 'last 30 days' -> INTERVAL '30 days')"]

    IntentCount & IntentTopN & IntentTrend & IntentAgg & IntentComp & IntentExists & IntentList --> SkeletonBuilder["build_sql_skeleton()"]
    TableKeywords & ColumnValues & TimeFilter --> SkeletonBuilder

    SkeletonBuilder --> QueryContext["Output: qctx Dict\n• intent & intent_hint\n• entities (tables, filters, time)\n• filter_hints (ILIKE templates)\n• skeleton (Pre-structured SQL scaffold)"]
```

---

### Layer 2: Hybrid Retrieval & RAG Pipeline
**Files:** [`backend/hybrid_retriever.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/hybrid_retriever.py), [`embeddings/retrieve.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/embeddings/retrieve.py)

Combines **dense semantic search** with **sparse keyword search (BM25)** using **Reciprocal Rank Fusion (RRF)** to pick the top-K tables out of 234 schema tables.

```mermaid
flowchart TD
    subgraph InputStage["Query Ingestion"]
        Q["User Question"]
        IsIndexReady{"is_index_ready()?"}
        Q --> IsIndexReady
    end

    subgraph DensePath["Dense Semantic Search (65% Weight)"]
        MiniLM["SentenceTransformer\n(all-MiniLM-L6-v2)"]
        QueryEmbedding["Query Vector (384-dim)"]
        ChromaQuery["ChromaDB Cosine Search\n(Collection: table_schemas)"]
        DenseDistances["L2 Distances -> Similarities\nsim = max(0, 1 - dist/2)"]

        Q --> MiniLM --> QueryEmbedding --> ChromaQuery --> DenseDistances
    end

    subgraph SparsePath["Sparse Keyword Search (35% Weight)"]
        Tokenize["Tokenize Query into Terms"]
        BM25Calc["Okapi BM25 Scoring across\nCached Table Descriptions"]
        NormaliseBM25["Normalized Scores (0.0 - 1.0)"]

        Q --> Tokenize --> BM25Calc --> NormaliseBM25
    end

    subgraph FusionStage["Reciprocal Rank Fusion (RRF) & Gating"]
        RRF["Combined Score =\n(0.65 * Semantic) + (0.35 * BM25)"]
        DenseDistances --> RRF
        NormaliseBM25 --> RRF

        Tiers{"Tier Categorization"}
        RRF --> Tiers

        HighTier["High Tier: Score >= 0.60"]
        MedTier["Medium Tier: 0.35 <= Score < 0.60"]
        LowTier["Low Tier: Score < 0.35"]

        Tiers --> HighTier
        Tiers --> MedTier
        Tiers --> LowTier

        Selection["Select High + Fill with Medium up to Top-K (8 or 12)\n(Ensure minimum 3 tables)"]
        HighTier & MedTier & LowTier --> Selection
    end

    subgraph PostRetrieval["Schema Enhancement & Anchoring"]
        AnchorCheck["force_anchor_tables()\n(Inject critical roots: managed_device, customer, etc.)"]
        FollowupCheck["Context Table Union\n(Inject context.tables_used from prior turn)"]
        DDLFetch["Fetch DDL Text from Metadata"]

        Selection --> AnchorCheck --> FollowupCheck --> DDLFetch
    end

    subgraph FallbackPath["Degraded Mode (No Embeddings)"]
        EntityTables["Extract tables from TABLE_KEYWORDS"]
        AnchorFallback["Force Anchor Tables"]
        ExpandFallback["Expand Related Tables"]

        IsIndexReady -->|No| EntityTables --> AnchorFallback --> ExpandFallback
    end

    IsIndexReady -->|Yes| DensePath
    IsIndexReady -->|Yes| SparsePath

    DDLFetch --> FinalOutput["Final Schema Context & Table List"]
    ExpandFallback --> FinalOutput
```

---

### Layer 3: Schema Graph Engine (GraphRAG)
**File:** [`backend/schema_graph.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/schema_graph.py)

Uses **NetworkX** to construct a bi-directional directed graph of all 234 tables and their foreign-key constraints. Eliminates hallucinated joins by computing the shortest join path and injecting junction/connector tables.

```mermaid
flowchart LR
    subgraph GraphBuilding["Schema Graph Initialization"]
        FKDict["SCHEMA_GRAPH Dict\n(Child -> Parent: ON child.col = parent.col)"]
        NXBuild["NetworkX Graph Constructor\n_build_graph()"]
        DiGraph[("nx.DiGraph\nNodes: 234 Tables\nEdges: FK Constraints")]

        FKDict --> NXBuild --> DiGraph
    end

    subgraph PathFinding["BFS Join Path Discovery"]
        TablesIn["Retrieved Tables\n(e.g., managed_device, org_patch)"]
        RootSelect["Select Root Table\n(Table with highest degree/parents)"]
        ShortestPath["nx.shortest_path(_G, root, target)\nBreadth-First Search"]

        TablesIn --> RootSelect
        RootSelect --> ShortestPath
        DiGraph --> ShortestPath

        EdgeJoin["Extract Edge Join Attributes\n'JOIN parent ON child.col = parent.col'"]
        ShortestPath --> EdgeJoin
    end

    subgraph ConnectorExpansion["Junction Table Expansion"]
        Expand["expand_related_tables()"]
        CheckJunction{"Are endpoints disconnected\nwithout a connector?"}
        AddConnector["Inject Bridge Table\n(e.g., device_missing_patch between\nmanaged_device and org_patch)"]

        TablesIn --> Expand --> CheckJunction
        CheckJunction -->|Yes| AddConnector
        CheckJunction -->|No| Ready["Keep Tables"]
    end

    EdgeJoin --> JoinHints["Join Hints String Injected into Prompt:\nSuggested JOIN path starting from 'managed_device':\nJOIN device_missing_patch ON dmp.managed_device_id = md.id\nJOIN org_patch ON op.patch_id = dmp.patch_id"]
```

---

### Layer 4: Context Assembly & Dynamic Prompt Budgeting
**File:** [`backend/main.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/main.py)

Assembles the system prompt, guidelines, conversation history, schema DDLs, few-shot examples, and skeletons, then runs a progressive token shedding algorithm to guarantee strict adherence to LLM context limits.

```mermaid
flowchart TD
    subgraph Assembly["Context Blocks Aggregation"]
        P1["1. Base System Prompt\n(COMPACT_SYSTEM_PROMPT / Postgres Rules)"]
        P2["2. Advanced SQL Hints\n(Injected only if is_complex_query == True)"]
        P3["3. Tenant / Org Security Mandate\n(Injected if org_id is provided)"]
        P4["4. Conversation Context Block\n(Previous Q, Previous SQL, Tables Used)"]
        P5["5. Dynamic Few-Shot Examples\n(ChromaDB sql_examples collection)"]
        P6["6. Relevant Schema DDL\n(Selected Tables from Layer 2 & 3)"]
        P7["7. Join Hints & Edge Paths\n(NetworkX Paths from Layer 3)"]
        P8["8. Intent, Hints & SQL Skeleton\n(Output from Layer 1)"]
        P9["9. Self-Correction Diff Block\n(Failed SQL + Errors from prior attempts)"]
        P10["10. Question String"]
    end

    P1 & P2 & P3 & P4 & P5 & P6 & P7 & P8 & P9 & P10 --> RawPrompt["Assembled Full Prompt String"]

    subgraph BudgetGuard["Dynamic Token Budget Guard (_trim_prompt_to_budget)"]
        RawPrompt --> Estimate["Token Estimate = len(prompt) // 4 + max_tokens"]
        BudgetCheck{"total <= MAX_PROMPT_TOKENS\n(default: 3000 tokens)?"}
        Estimate --> BudgetCheck

        BudgetCheck -->|Fits Budget| PromptReady["Prompt Ready for LLM"]

        BudgetCheck -->|Exceeds Budget| SplitDDL["Split schema_text into individual table DDL blocks"]
        SplitDDL --> DropLeastRelevant["Pop least relevant table DDL block\n(tail of retrieved list)"]
        DropLeastRelevant --> UpdateTables["Update tables_used list\n& replace schema in prompt"]
        UpdateTables --> Recheck["Re-estimate tokens"]
        Recheck --> BudgetCheck
    end
```

---

### Layer 5: LLM Orchestrator & Multi-Provider Circuit Breakers
**Files:** [`backend/llm_orchestrator.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/llm_orchestrator.py), [`backend/llm_config.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/llm_config.py), [`backend/llm_registry.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/llm_registry.py)

Manages request-scoped routing across **Groq**, **Google Gemini**, and **Local Ollama/Qwen**, armed with dynamic thread-safe circuit breakers, error classification, and transparent failover.

```mermaid
flowchart TD
    Start["generate(prompt, tenant_id, excluded_providers)"] --> ConfigSnapshot["runtime_config.snapshot()\n(Hot-reloads .env if file mtime changed)"]
    ConfigSnapshot --> Resolve["CredentialResolver.resolve()\nDetermines candidate provider chain:\n1. Groq -> 2. Gemini -> 3. Ollama"]
    
    Resolve --> FilterExcluded["Filter out excluded_providers\n(Providers that failed validation in this turn)"]
    FilterExcluded --> CandidatesList["Candidate Queue"]

    CandidatesList --> NextCandidate{"Next Provider Available?"}
    NextCandidate -->|No candidates left| FailAll["Raise AllProvidersFailed\n('All LLM candidates failed')"]

    NextCandidate -->|Yes| CheckBreaker{"CircuitBreaker.allow()?\n(Is open_until < now?)"}

    CheckBreaker -->|Breaker Open| SkipProvider["Log breaker_open\nAdvance to next candidate"] --> NextCandidate

    CheckBreaker -->|Breaker Closed / Half-Open| Dispatch["ProviderGateway.invoke()"]

    subgraph GatewayExecution["Provider Invocation & Protocol Adaptation"]
        Dispatch --> StyleCheck{"provider.style"}
        StyleCheck -->|openai| GroqCall["POST https://api.groq.com/openai/v1/chat/completions\nAuth: Bearer GROQ_API_KEY\nTimeout: 60s"]
        StyleCheck -->|gemini| GeminiCall["POST .../v1beta/models/{model}:generateContent?key={key}\nTimeout: 60s"]
        StyleCheck -->|ollama| OllamaCall["POST http://localhost:11434/api/generate\nnum_ctx: 8192 | Timeout: 120s"]
    end

    GroqCall & GeminiCall & OllamaCall --> ResultCheck{"Call Successful?"}

    ResultCheck -->|Success| RecordSuccess["CircuitBreaker.record_success()\nReset consecutive_failures = 0"]
    RecordSuccess --> ReturnResponse["Return (raw_text, model_name, provider_name)"]

    ResultCheck -->|Error / Exception| ClassifyError["Classify ProviderCallError:\n• 429 -> rate_limit (cooldown = retry_after or 300s)\n• 401/403 -> auth (cooldown = 60s)\n• 5xx -> service\n• Timeout -> timeout (instant failover)\n• Network -> network (instant failover)"]

    ClassifyError --> RecordFailure["CircuitBreaker.record_failure()\nIncrement failures / Set open_until"]
    RecordFailure --> RetryPolicyCheck{"RetryPolicy.should_retry()?\n(Only for 'service' errors & attempt < 3)"}

    RetryPolicyCheck -->|Retryable| BackoffSleep["asyncio.sleep(exponential_backoff)"] --> Dispatch
    RetryPolicyCheck -->|Not Retryable| Advance["Instant failover to next provider"] --> NextCandidate
```

#### Circuit Breaker State Transition Diagram

```mermaid
stateDiagram-v2
    [*] --> Closed: Initial State

    Closed --> Closed: Request Succeeds / Reset Failures
    Closed --> Open: Consecutive Failures >= 3
    Closed --> TimedCooldown: Auth / Rate Limit Error (429/401/403)

    TimedCooldown --> HalfOpen: Monotonic Time > open_until (60s auth / 300s rate limit)
    Open --> HalfOpen: Monotonic Time > open_until (Recovery Time Elapsed)

    HalfOpen --> Closed: Probe Request Succeeds
    HalfOpen --> Open: Probe Request Fails
```

---

### Layer 6: AST Security Validation & Self-Correction Feedback Loop
**Files:** [`backend/sql_validator.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/sql_validator.py), [`backend/self_correction.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/self_correction.py)

Acts as the immutable security barrier and accuracy loop. Sanitizes LLM outputs, enforces AST schema correctness, verifies tenant isolation, and powers the self-correction engine.

```mermaid
flowchart TD
    RawOutput["Raw LLM Output Text"] --> StripThink["Strip &lt;think&gt;...&lt;/think&gt; Scratchpads"]
    StripThink --> ExtractSQL["extract_sql()\n(Regex extraction of ```sql fence or SELECT ... FROM)"]
    
    ExtractSQL --> SelectGuard{"Starts with SELECT or WITH?\n(Rejects non-query text)"}
    SelectGuard -->|No| RejectNonSelect["Record Failure: Non-SELECT SQL returned"]

    SelectGuard -->|Yes| ForbiddenCheck{"Contains Forbidden Write/DDL?\n(INSERT, UPDATE, DELETE, DROP,\nALTER, TRUNCATE, GRANT, EXECUTE)"}
    ForbiddenCheck -->|Found| SecurityBlock["Record Failure: Security violation - Write/DDL forbidden"]

    ForbiddenCheck -->|None| SemicolonCheck{"Contains chained statements?\n(Multiple ';' delimiters)"}
    SemicolonCheck -->|Found| MultiStmtBlock["Record Failure: Chained SQL statements prohibited"]

    SemicolonCheck -->|Single Statement| CTEMap["Identify Local CTE Aliases\nWITH cte_name AS (...)"]
    CTEMap --> TableCheck{"Verify all FROM / JOIN tables\nexist in _known_tables"}

    TableCheck -->|Unknown Table| TableErr["Record Failure: Table does not exist in schema"]
    TableCheck -->|All Tables Known| ColumnCheck{"Verify all alias.col references\nexist in _known_columns"}

    ColumnCheck -->|Unknown Column| ColErr["Record Failure: Column does not exist in table"]
    ColumnCheck -->|All Columns Known| OrgIsolationCheck{"Is org_id specified?"}

    OrgIsolationCheck -->|No| QualityLint["check_sql_quality()\n(Warns on SELECT *, missing LIMIT, string booleans)"]
    OrgIsolationCheck -->|Yes| OrgSecurityRegex{"validate_org_security()\nMatches: zecure_org_id = '{org_id}'\nor zecure_org_id IN ('{org_id}')"}

    OrgSecurityRegex -->|Missing / Bypassed| OrgSecErr["Record Failure: Security violation -\nMissing mandatory organization filter"]
    OrgSecurityRegex -->|Present| QualityLint

    QualityLint --> SuccessDone["VALIDATION PASSED\nStore in ChromaDB sql_examples\nReturn HTTP 200 OK"]

    %% Self Correction Branch
    RejectNonSelect & SecurityBlock & MultiStmtBlock & TableErr & ColErr & OrgSecErr --> AddFailure["Append to failed_attempts: (sql, error)\nAdd provider to rejected_providers"]

    AddFailure --> AttemptCount{"Attempt < MAX_ATTEMPTS (3)?"}
    AttemptCount -->|Yes| BuildDiff["build_retry_context()\nConstructs diff showing prior failed SQL & exact error"]
    BuildDiff --> RePrompt["Inject diff into prompt & retry generation\n(Cycles to next LLM in chain)"]
    RePrompt --> RawOutput

    AttemptCount -->|No| Exhausted["Raise ValueError:\n'Could not generate working SQL after 3 attempts'"]
```

---

## 4. Multi-Turn Conversational Context Engine

Enables intelligent context continuity so users can issue natural conversational follow-ups without repeating the full context.

```mermaid
flowchart TD
    ClientReq["Client Request:\nquestion: 'now filter that to critical only'\ncontext: { previous_q, previous_sql, tables_used }"] --> DetectFollowup{"is_followup_question(question)\nRegex matching:\nthat, it, those, now show, instead,\nfilter further, break down..."}

    DetectFollowup -->|No / Standalone Query| NormalPipeline["Standard Execution:\nFresh retrieval, no previous SQL injected"]

    DetectFollowup -->|Yes / Follow-Up Query| ContextBlock["build_conversation_context_block()\nInjects Previous Question, Previous SQL (up to 600 chars),\nand Previous Tables Involved into prompt"]

    ContextBlock --> SchemaInheritance["Schema Inheritance Gating:\nCheck context.tables_used"]

    SchemaInheritance --> UnionTables["Union Previous Tables:\nnew_tables = context.tables_used - current_retrieved"]

    UnionTables --> IndexCheck{"is_index_ready()?"}
    IndexCheck -->|Yes| FetchDDL["get_schema_for_tables(new_tables)\nDirect lookup by ID from ChromaDB"]
    IndexCheck -->|No| FilterKnown["Filter against _known_tables"]

    FetchDDL --> MergeSchema["Append prior turn's DDL to schema_text\nEnsure LLM sees all relevant parent tables"]
    FilterKnown --> MergeSchema

    MergeSchema --> AssemblePrompt["Assemble final prompt instructing LLM:\n'Build on same tables/filters, adjust only what changed'"]
```

---

## 5. Multi-Tenant Security & AST Validation Architecture

A defense-in-depth visual of how tenant isolation (`zecure_org_id`) is strictly enforced at every level of the pipeline without administrative bypass.

```mermaid
flowchart TD
    subgraph Layer0["1. Ingestion & Authentication Boundary"]
        Req["HTTP POST /chat Request"]
        AuthMode{"REQUIRE_AUTH == true?"}
        Req --> AuthMode

        AuthMode -->|Production Mode| DecodeJWT["auth.py: _decode_token()\n• Validate RS256 with Provider JWKS\n• Verify Issuer & Audience\n• Verify Expiration"]
        DecodeJWT --> ExtractClaim["Extract Org Claim: payload['custom:org_id']\nOverwrites any unverified body param"]

        AuthMode -->|Development Mode| BodyOrg["Accept org_id from Request Body"]
        ExtractClaim --> VerifiedOrg["Strictly Bound org_id"]
        BodyOrg --> VerifiedOrg
    end

    subgraph Layer1["2. Prompt-Level Guardrails"]
        VerifiedOrg --> InjectPrompt["MANDATORY REQUIREMENT:\n'User specified org_id = {org_id}.\nEVERY SQL query generated MUST strictly include\nzecure_org_id = {org_id} in the WHERE clause.'"]
    end

    subgraph Layer2["3. Lexical & AST Boundary"]
        LLMGen["LLM Generates SQL"] --> ASTGate["sql_validator.py"]
        
        ASTGate --> CheckReadOnly["Read-Only Check:\nRegex rejects INSERT, UPDATE, DELETE, DROP, ALTER..."]
        ASTGate --> CheckNoChained["Single-Query Check:\nRejects ';' chaining multiple queries"]
        
        CheckReadOnly --> PassedLexical["Lexically Safe SELECT"]
        CheckNoChained --> PassedLexical
    end

    subgraph Layer3["4. Tenant Isolation Security Gate"]
        PassedLexical --> OrgValidator["validate_org_security(sql, org_id)"]
        OrgValidator --> RegexPattern{"Regex Validation:\nzecure_org_id = '{org_id}'\nOR\nzecure_org_id IN ('{org_id}')"}

        RegexPattern -->|Missing or Mismatched| SecurityException["SECURITY VIOLATION REJECTED\nThrows error back into self-correction diff.\nQuery will NEVER be returned to client."]
        RegexPattern -->|Matched Exact Org| PassSec["Security Passed\nQuery strictly isolated to tenant"]
    end

    InjectPrompt --> LLMGen
```

---

## 6. Offline Database Introspection & ChromaDB Vector Indexing
**Files:** [`embeddings/schema_introspect.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/embeddings/schema_introspect.py), [`embeddings/build_index.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/embeddings/build_index.py)

The offline pipeline that syncs the real 234-table PostgreSQL database schema into ChromaDB with rich metadata and incremental change detection.

```mermaid
flowchart TD
    CLI["Command: python -m embeddings.build_index\n(--full or incremental)"] --> Introspect["schema_introspect.py: introspect_all()"]

    subgraph PostgresIntrospection["PostgreSQL Catalog Reflection"]
        Introspect --> QueryCols["Query information_schema.columns\n(name, data_type, nullable, default)"]
        Introspect --> QueryComments["Query col_description() & obj_description()\n(Schema comments on tables & columns)"]
        Introspect --> QueryFKs["Query information_schema.table_constraints\n(Foreign key relationships & targets)"]
        Introspect --> QueryEnums["Query pg_enum & check constraints\n(Valid enum values and codes)"]
    end

    QueryCols & QueryComments & QueryFKs & QueryEnums --> TableSchemaObj["TableSchema Object per Table"]

    subgraph Synthesis["Description Synthesis Priority"]
        TableSchemaObj --> PriorityCheck{"Description Priority"}
        PriorityCheck -->|1. Top Priority| ManualOverride["RICH_DESCRIPTIONS\n(Hand-curated semantic summaries)"]
        PriorityCheck -->|2. Second Priority| DBComments["PostgreSQL COMMENT ON TABLE"]
        PriorityCheck -->|3. Fallback| AutoSynth["Synthesized from Column Names,\nForeign Keys & Types"]
    end

    ManualOverride & DBComments & AutoSynth --> FinalDesc["Final Semantic Table Description"]

    subgraph IncrementalGating["Content Hash & Incremental Gating"]
        TableSchemaObj --> HashCalc["Compute Stable SHA-256 Content Hash\n(columns + types + comments + FKs + enums)"]
        HashCalc --> HashCompare{"Hash == Stored Chroma Hash?"}
        
        HashCompare -->|Unchanged| SkipTable["Skip Re-Embedding\n(Zero Token / Compute Cost)"]
        HashCompare -->|Modified or New| EmbedDoc["Generate Embedding Document\n(Chunked at <= 5000 chars)"]
    end

    FinalDesc --> EmbedDoc

    subgraph ChromaStorage["ChromaDB Ingestion"]
        EmbedDoc --> Transformer["SentenceTransformer('all-MiniLM-L6-v2')\nGenerates 384-dimensional dense vectors"]
        Transformer --> ChromaUpsert["ChromaDB PersistentClient\nCollection: 'table_schemas'\nUpsert ID: table_name\nMetadata: { raw_ddl, hash, table_name }"]
        ChromaUpsert --> DiskStore[("Persistent Store on Disk\n./embeddings/chroma_store")]
    end
```

---

## 7. Component & Directory Cross-Reference

| Layer / Subsystem | Primary Code File | Key Functions & Classes | Primary Responsibilities |
| :--- | :--- | :--- | :--- |
| **API Entrypoint** | [`backend/main.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/main.py) | `chat()`, `health()`, `generate_sql_with_retry()`, `_trim_prompt_to_budget()` | FastAPI router, lifespan setup, token budgeting, pipeline execution loop. |
| **L1: Query Intelligence** | [`backend/query_intelligence.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/query_intelligence.py) | `classify_intent()`, `extract_entities()`, `build_sql_skeleton()`, `build_query_context()` | Intent mapping (7 classes), entity dictionary (234 tables), temporal parsing. |
| **L2: Hybrid Retrieval** | [`backend/hybrid_retriever.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/hybrid_retriever.py) | `retrieve_tables()`, `_bm25_scores()`, `get_similar_examples()`, `store_successful_example()` | BM25 sparse + ChromaDB dense retrieval, RRF scoring, tiered table gating. |
| **L2: Vector Query Interface** | [`embeddings/retrieve.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/embeddings/retrieve.py) | `retrieve_relevant_tables()`, `is_index_ready()`, `_get_model()` | ChromaDB collection connection, sentence transformer singleton, RRF ranking. |
| **L3: Schema Graph** | [`backend/schema_graph.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/schema_graph.py) | `get_join_hints()`, `find_join_path()`, `expand_related_tables()`, `force_anchor_tables()` | NetworkX BFS shortest-path join discovery, bridge table expansion. |
| **L4: Prompts & Rules** | [`backend/prompts.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/prompts.py) | `get_system_prompt()`, `COMPACT_SYSTEM_PROMPT` | Postgres guidelines, integer platform/status mappings, few-shot prompts. |
| **L5: LLM Orchestrator** | [`backend/llm_orchestrator.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/llm_orchestrator.py) | `LLMOrchestrator.generate()`, `ProviderGateway`, `CredentialBreakerStore` | Multi-LLM failover (Groq &rarr; Gemini &rarr; Ollama), request-scoped circuit breakers. |
| **L5: LLM Configuration** | [`backend/llm_config.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/llm_config.py) | `RuntimeConfig`, `RuntimeConfigSnapshot`, `system_llm_status()` | Zero-restart hot reloading of `.env`, fallback chain definition. |
| **L5: LLM Registry** | [`backend/llm_registry.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/llm_registry.py) | `get_provider()`, `PROVIDERS`, `ProviderDefinition` | Provider metadata, endpoints, authentication headers, default models. |
| **L6: AST & Org Validator** | [`backend/sql_validator.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/sql_validator.py) | `extract_sql()`, `validate_sql()`, `validate_org_security()` | Read-only verification, CTE tracking, table/column verification, tenant isolation. |
| **L6: Self-Correction** | [`backend/self_correction.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/self_correction.py) | `build_retry_context()`, `check_sql_quality()` | Diff formatting for retries, warnings for `SELECT *` and unindexed filters. |
| **Security & Auth** | [`backend/auth.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/backend/auth.py) | `get_current_user()`, `_decode_token()`, `_fetch_jwks()` | OIDC / JWKS RS256 token validation, 6-hour key cache, `org_id` claim extraction. |
| **Offline Schema Introspection** | [`embeddings/schema_introspect.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/embeddings/schema_introspect.py) | `introspect_all()`, `_fetch_column_metadata()`, `TableSchema` | Live PostgreSQL catalog reflection, comment extraction, stable hash computation. |
| **Offline Vector Indexer** | [`embeddings/build_index.py`](file:///c:/Users/kisho/OneDrive/Desktop/chatbot_v2/embeddings/build_index.py) | Incremental build CLI, `RICH_DESCRIPTIONS` | Embedding generation (`all-MiniLM-L6-v2`) and persistent ChromaDB storage. |
