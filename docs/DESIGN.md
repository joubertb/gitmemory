# GitMemory Design Document

> **Status**: Draft
> **Version**: 0.1.0
> **Last Updated**: 2025-12-19

---

## Table of Contents

1. [Overview](#overview)
2. [Goals and Non-Goals](#goals-and-non-goals)
3. [Architecture](#architecture)
4. [Pipeline Stages](#pipeline-stages)
5. [Data Model](#data-model)
6. [Storage Layer](#storage-layer)
7. [Retrieval & Ranking](#retrieval--ranking)
8. [API Design](#api-design)
9. [Incremental Processing](#incremental-processing)
10. [Security & Privacy](#security--privacy)
11. [Open Questions](#open-questions)
12. [Glossary](#glossary)

---

## Overview

### Problem Statement

AI coding assistants operate with limited context about a codebase's history. They can see current code but lack understanding of:

- **Why** code was written a certain way
- **How** it evolved over time
- **What** decisions led to current architecture
- **Which** changes are related to each other

Git repositories contain this rich history, but it's locked in commit messages, diffs, and issue references that aren't easily queryable by AI systems.

### Solution

**GitMemory** transforms Git repository history into structured, searchable knowledge that AI coding assistants can query to make better decisions.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Git Repository                           │
│  (commits, diffs, messages, branches, tags)                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         GitMemory                                │
│  ┌─────────┐  ┌────────────┐  ┌─────────┐  ┌──────────────────┐ │
│  │ Extract │→ │ Understand │→ │  Store  │→ │ Retrieve + Build │ │
│  └─────────┘  └────────────┘  └─────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Context Pack                              │
│  (structured knowledge ready for AI consumption)                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Goals and Non-Goals

### Goals

1. **Deep History Understanding** — Extract meaningful knowledge from commit history, not just surface-level diffs
2. **Semantic Search** — Find relevant history based on meaning, not just keyword matching
3. **Relationship Tracking** — Understand how code entities relate and co-evolve
4. **Token-Efficient Output** — Produce Context Packs that fit within LLM context windows
5. **Incremental Updates** — Efficiently process new commits without full reindexing
6. **Language Agnostic** — Support any programming language (with enhanced support for popular ones)

### Non-Goals

1. **Real-time Streaming** — Not designed for sub-second updates (batch processing is acceptable)
2. **Code Execution** — We analyze code, not run it
3. **Issue Tracker Replacement** — We reference issues, not manage them
4. **Full Git Client** — We read Git data, not write it
5. **IDE Integration** — We provide APIs; IDE plugins are separate projects

---

## Architecture

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              GitMemory Core                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────┐    ┌─────────────────┐    ┌────────────────────────────┐ │
│  │            │    │                 │    │       Storage Layer        │ │
│  │  Extract   │───▶│   Understand    │───▶│  ┌──────────────────────┐  │ │
│  │            │    │                 │    │  │    Vector Index      │  │ │
│  └────────────┘    └─────────────────┘    │  │    (embeddings)      │  │ │
│        │                   │              │  ├──────────────────────┤  │ │
│        │                   │              │  │   Knowledge Graph    │  │ │
│        ▼                   ▼              │  │ (entities + rels)    │  │ │
│  ┌────────────┐    ┌─────────────────┐    │  ├──────────────────────┤  │ │
│  │ Git Reader │    │   LLM / Models  │    │  │     Blob Store       │  │ │
│  │            │    │                 │    │  │   (diffs, files)     │  │ │
│  └────────────┘    └─────────────────┘    │  ├──────────────────────┤  │ │
│                                           │  │   Metadata Store     │  │ │
│                                           │  │  (commits, config)   │  │ │
│                                           │  └──────────────────────┘  │ │
│                                           └────────────────────────────┘ │
│                                                        │                 │
│                                                        ▼                 │
│                           ┌─────────────────────────────────────────┐    │
│                           │           Retrieval Engine              │    │
│                           │  ┌─────────┐ ┌─────────┐ ┌───────────┐  │    │
│                           │  │ Graph   │ │ Vector  │ │  Ranker   │  │    │
│                           │  │ Search  │ │ Search  │ │           │  │    │
│                           │  └─────────┘ └─────────┘ └───────────┘  │    │
│                           └─────────────────────────────────────────┘    │
│                                                        │                 │
│                                                        ▼                 │
│                           ┌─────────────────────────────────────────┐    │
│                           │          Context Builder                │    │
│                           │  (assembles token-fitted Context Pack)  │    │
│                           └─────────────────────────────────────────┘    │
│                                                        │                 │
└────────────────────────────────────────────────────────│─────────────────┘
                                                         │
                                                         ▼
                                              ┌───────────────────┐
                                              │   Context Pack    │
                                              │   (JSON output)   │
                                              └───────────────────┘
```

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Extract** | Read Git data (commits, diffs, refs, blame) and normalize into internal representation |
| **Understand** | Apply LLM/ML models to extract meaning, relationships, classifications |
| **Store** | Persist extracted knowledge across multiple specialized stores |
| **Retrieve** | Query stores using graph traversal and semantic search |
| **Build** | Assemble retrieved items into token-fitted Context Packs |

---

## Pipeline Stages

### Stage 1: Extract

**Input**: Git repository path + optional ref range
**Output**: Normalized commit data structures

```
ExtractedCommit:
  hash: string
  parent_hashes: string[]
  author: { name, email, timestamp }
  committer: { name, email, timestamp }
  message: string
  diffs: FileDiff[]
  refs: string[]              # branches/tags pointing here

FileDiff:
  path: string
  old_path: string | null     # for renames
  status: added | modified | deleted | renamed | copied
  hunks: DiffHunk[]
  language: string | null     # detected language

DiffHunk:
  old_start: int
  old_count: int
  new_start: int
  new_count: int
  content: string
```

**Extraction Tasks**:
- Parse commit metadata
- Generate diffs (with rename detection)
- Detect file languages
- Extract referenced issues/tickets from commit messages
- Identify merge commits and their structure

**Open Questions**:
- [ ] How deep to follow rename chains?
- [ ] How to handle binary files?
- [ ] Should we extract blame information at this stage?

---

### Stage 2: Understand

**Input**: ExtractedCommit
**Output**: UnderstoodCommit with enriched metadata

```
UnderstoodCommit:
  commit: ExtractedCommit
  summary: string                    # LLM-generated summary
  classification: ChangeType         # bugfix, feature, refactor, etc.
  entities_modified: EntityRef[]     # functions, classes, etc.
  relationships: Relationship[]      # detected relationships
  design_notes: DesignNote[]         # extracted rationale
  test_associations: TestRef[]       # related tests
  embeddings: Embedding[]            # vector representations
  security_flags: SecurityFlag[]     # secrets, vulnerabilities
```

**Understanding Tasks**:

| Task | Model | Description |
|------|-------|-------------|
| **Summarization** | LLM | Generate concise summary of changes |
| **Classification** | LLM or Classifier | Categorize change type |
| **Entity Extraction** | Tree-sitter + LLM | Identify modified code entities |
| **Relationship Detection** | LLM | Find connections between entities |
| **Design Note Extraction** | LLM | Extract rationale from messages/comments |
| **Test Association** | Heuristics + LLM | Link changes to relevant tests |
| **Embedding Generation** | Embedding Model | Create vector representations |
| **Security Screening** | Rules + LLM | Detect secrets/vulnerabilities |

**Change Classifications**:

```
ChangeType:
  - bugfix          # Fixes incorrect behavior
  - feature         # Adds new functionality
  - refactor        # Restructures without behavior change
  - performance     # Optimizes speed/memory
  - security        # Addresses security issues
  - documentation   # Updates docs/comments only
  - test            # Adds/modifies tests only
  - dependency      # Updates dependencies
  - configuration   # Changes config files
  - cleanup         # Removes dead code, formatting
```

**Open Questions**:
- [ ] Which LLM to use? (Cost vs quality tradeoffs)
- [ ] How to batch commits for efficient LLM usage?
- [ ] How to handle commits that span multiple classifications?
- [ ] What embedding model and dimensions?

---

### Stage 3: Store

**Input**: UnderstoodCommit
**Output**: Persisted to storage layer

#### Storage Components

**1. Vector Index** (e.g., ChromaDB, Qdrant, Pinecone)
```
Stored vectors:
  - Commit summary embeddings
  - Code change embeddings
  - Design note embeddings
  - Function/class description embeddings
```

**2. Knowledge Graph** (e.g., Neo4j, DGraph, in-memory)
```
Nodes:
  - Repository
  - Commit
  - File
  - Function | Class | Method
  - Issue
  - DesignNote
  - TestCase

Edges:
  - MODIFIES (Commit → Entity)
  - CO_EVOLVES_WITH (Entity ↔ Entity)
  - FIXES (Commit → Issue)
  - REPLACED_BY (Entity → Entity)
  - INTRODUCES (Commit → Entity)
  - VERIFIED_BY (Entity → TestCase)
  - REFERENCES (Commit → Issue)
  - PARENT_OF (Commit → Commit)
  - CONTAINS (File → Entity)
```

**3. Blob Store** (e.g., filesystem, S3, SQLite)
```
Stored blobs:
  - Raw diff content
  - File snapshots at key commits
  - Full commit messages
```

**4. Metadata Store** (e.g., SQLite, PostgreSQL)
```
Tables:
  - repositories (id, path, remote_url, last_sync)
  - commits (hash, repo_id, author, timestamp, summary, classification)
  - sync_state (repo_id, last_processed_hash, cursor)
  - processing_queue (commit_hash, status, attempts, error)
```

**Open Questions**:
- [ ] Which specific databases/stores to use?
- [ ] How to handle storage consistency across stores?
- [ ] What's the sharding/partitioning strategy for large repos?

---

### Stage 4: Retrieve

**Input**: Query (natural language or structured)
**Output**: Ranked list of relevant items

**Query Types**:
```
Query:
  | NaturalLanguageQuery { text: string }
  | EntityQuery { entity_type, name, path }
  | CommitQuery { hash | date_range | author }
  | RelationshipQuery { from_entity, relationship_type }
```

**Retrieval Algorithm**:

```python
def retrieve(query: Query, limit: int, token_budget: int) -> RetrievalResult:
    # 1. Parallel search across stores
    vector_results = vector_search(query.embedding, k=limit*3)
    graph_results = graph_search(query.entities, depth=2)

    # 2. Merge and deduplicate
    candidates = merge_results(vector_results, graph_results)
    candidates = deduplicate(candidates)

    # 3. Score and rank
    for item in candidates:
        item.score = compute_score(item, query)

    candidates.sort(by=score, descending=True)

    # 4. Token-aware selection
    selected = []
    tokens_used = 0
    for item in candidates:
        if tokens_used + item.token_count <= token_budget:
            selected.append(item)
            tokens_used += item.token_count

    return RetrievalResult(items=selected, tokens=tokens_used)
```

**Scoring Formula**:
```
score = (
    w1 * vector_similarity +      # Semantic relevance
    w2 * recency_score +          # Prefer recent changes
    w3 * importance_score +       # Commit/entity importance
    w4 * relationship_bonus +     # Connected to query entities
    w5 * author_relevance         # If querying about author's work
)

# Default weights (tunable)
w1 = 0.4
w2 = 0.2
w3 = 0.2
w4 = 0.15
w5 = 0.05
```

**Open Questions**:
- [ ] How to tune scoring weights?
- [ ] Should we support user feedback to improve ranking?
- [ ] How to handle queries with no good matches?

---

### Stage 5: Build (Context Assembly)

**Input**: RetrievalResult + token_budget
**Output**: Context Pack

**Context Pack Structure**:
```yaml
ContextPack:
  metadata:
    query: string
    repository: string
    generated_at: timestamp
    token_count: int

  summary: string                 # High-level answer to query

  timeline:                       # Evolution of relevant entities
    - date: timestamp
      summary: string
      commits: string[]

  key_items:                      # Most relevant commits
    - hash: string
      summary: string
      classification: string
      relevance_score: float

  code_context:                   # Relevant code snippets
    - path: string
      entity: string
      snippet: string
      explanation: string

  important_diffs:                # Key changes (trimmed)
    - commit: string
      path: string
      diff: string
      explanation: string

  design_notes:                   # Extracted rationale
    - source: string              # commit hash or file path
      note: string
      relevance: string

  related_tests:                  # Relevant test information
    - path: string
      name: string
      description: string

  provenance:                     # Source references
    commits: string[]
    files: string[]
    authors: string[]
```

**Token Fitting Strategy**:
```
Priority order for token allocation:
1. Summary (required, ~200 tokens)
2. Key items (required, ~100 tokens each, max 5)
3. Timeline (important, ~50 tokens per entry)
4. Design notes (important, ~100 tokens each)
5. Code context (if space, ~200 tokens each)
6. Important diffs (if space, ~300 tokens each)
7. Related tests (if space, ~100 tokens each)
```

**Open Questions**:
- [ ] How to generate the summary? (LLM call or template?)
- [ ] Should Context Pack format be configurable?
- [ ] How to handle multilingual codebases?

---

## Data Model

### Entity Model

```typescript
interface Repository {
  id: string;
  path: string;
  remote_url?: string;
  default_branch: string;
  languages: string[];
  created_at: Date;
  last_synced_at: Date;
}

interface Commit {
  hash: string;
  repository_id: string;
  parent_hashes: string[];
  author: Author;
  committer: Author;
  message: string;
  summary: string;           // LLM-generated
  classification: ChangeType;
  timestamp: Date;
  files_changed: number;
  insertions: number;
  deletions: number;
}

interface CodeEntity {
  id: string;
  repository_id: string;
  type: 'function' | 'class' | 'method' | 'module' | 'variable';
  name: string;
  qualified_name: string;    // Full path including module/class
  file_path: string;
  start_line: number;
  end_line: number;
  language: string;
  signature?: string;        // For functions/methods
  first_seen_commit: string;
  last_modified_commit: string;
  is_deleted: boolean;
}

interface DesignNote {
  id: string;
  repository_id: string;
  source_type: 'commit_message' | 'code_comment' | 'doc_file';
  source_ref: string;        // commit hash or file path
  content: string;
  entities: string[];        // Related entity IDs
  extracted_at: Date;
}

interface TestCase {
  id: string;
  repository_id: string;
  file_path: string;
  name: string;
  type: 'unit' | 'integration' | 'e2e';
  tested_entities: string[]; // Entity IDs this test covers
  last_modified_commit: string;
}
```

### Relationship Model

```typescript
interface Relationship {
  id: string;
  type: RelationshipType;
  from_id: string;
  from_type: EntityType;
  to_id: string;
  to_type: EntityType;
  properties: Record<string, any>;
  created_at: Date;
  confidence: number;        // 0-1, how confident we are in this relationship
}

type RelationshipType =
  | 'MODIFIES'          // Commit modifies Entity
  | 'CO_EVOLVES_WITH'   // Entity frequently changes with Entity
  | 'FIXES'             // Commit fixes Issue
  | 'REPLACED_BY'       // Entity replaced by Entity
  | 'INTRODUCES'        // Commit introduces Entity
  | 'VERIFIED_BY'       // Entity verified by TestCase
  | 'REFERENCES'        // Commit references Issue
  | 'PARENT_OF'         // Commit is parent of Commit
  | 'CONTAINS'          // File contains Entity
  | 'CALLS'             // Entity calls Entity
  | 'IMPORTS'           // File imports File/Module
  | 'IMPLEMENTS'        // Class implements Interface
  | 'EXTENDS';          // Class extends Class
```

---

## Storage Layer

### Storage Interface

```typescript
interface StorageLayer {
  // Vector operations
  vectors: {
    upsert(id: string, vector: number[], metadata: object): Promise<void>;
    search(vector: number[], k: number, filter?: object): Promise<VectorResult[]>;
    delete(id: string): Promise<void>;
  };

  // Graph operations
  graph: {
    createNode(type: string, properties: object): Promise<string>;
    createEdge(from: string, to: string, type: string, properties?: object): Promise<string>;
    query(cypher: string, params?: object): Promise<any[]>;
    getNeighbors(nodeId: string, edgeTypes?: string[], depth?: number): Promise<Node[]>;
  };

  // Blob operations
  blobs: {
    store(key: string, content: Buffer | string): Promise<void>;
    retrieve(key: string): Promise<Buffer | null>;
    delete(key: string): Promise<void>;
  };

  // Metadata operations
  metadata: {
    query<T>(sql: string, params?: any[]): Promise<T[]>;
    execute(sql: string, params?: any[]): Promise<void>;
    transaction<T>(fn: () => Promise<T>): Promise<T>;
  };
}
```

### Recommended Stack

| Component | Development | Production |
|-----------|-------------|------------|
| Vector Index | ChromaDB (embedded) | Qdrant or Pinecone |
| Knowledge Graph | SQLite + manual joins | Neo4j or DGraph |
| Blob Store | Filesystem | S3 or GCS |
| Metadata Store | SQLite | PostgreSQL |

### Consistency Strategy

```
Write Order (for new commit):
1. Write to metadata store (commit record)
2. Write to blob store (diffs, snapshots)
3. Write to knowledge graph (entities, relationships)
4. Write to vector index (embeddings)
5. Update sync state in metadata store

On Failure:
- Metadata store is source of truth for "what's processed"
- Partial writes are detected by checking sync state
- Recovery: re-process commits after last successful sync state
```

**Open Questions**:
- [ ] How to handle vector index rebuilds?
- [ ] Should we support pluggable storage backends?
- [ ] What's the backup/restore strategy?

---

## API Design

### Core API

```typescript
interface GitMemoryAPI {
  // Repository management
  repositories: {
    add(path: string, options?: AddOptions): Promise<Repository>;
    remove(id: string): Promise<void>;
    list(): Promise<Repository[]>;
    sync(id: string, options?: SyncOptions): Promise<SyncResult>;
    status(id: string): Promise<RepositoryStatus>;
  };

  // Querying
  query: {
    natural(text: string, options?: QueryOptions): Promise<ContextPack>;
    entity(entity: EntityQuery): Promise<ContextPack>;
    commit(commit: CommitQuery): Promise<ContextPack>;
    history(path: string, options?: HistoryOptions): Promise<ContextPack>;
  };

  // Direct access (for advanced use)
  entities: {
    get(id: string): Promise<CodeEntity | null>;
    search(query: string, type?: EntityType): Promise<CodeEntity[]>;
    relationships(id: string, types?: RelationshipType[]): Promise<Relationship[]>;
  };

  commits: {
    get(hash: string): Promise<Commit | null>;
    range(from: string, to: string): Promise<Commit[]>;
    search(query: CommitSearchQuery): Promise<Commit[]>;
  };
}

interface QueryOptions {
  repository_id?: string;      // Limit to specific repo
  token_budget?: number;       // Max tokens in response (default: 4000)
  include_diffs?: boolean;     // Include diff snippets (default: true)
  include_tests?: boolean;     // Include test info (default: true)
  recency_weight?: number;     // 0-1, prefer recent (default: 0.2)
  date_range?: DateRange;      // Limit to date range
}
```

### CLI Interface

```bash
# Repository management
gitmemory add /path/to/repo
gitmemory add . --name my-project
gitmemory list
gitmemory sync my-project
gitmemory status my-project

# Querying
gitmemory query "Why was the auth module refactored?"
gitmemory query "What changes affected the login function?"
gitmemory history src/auth/login.ts
gitmemory entity "signInViaSSO"

# Output options
gitmemory query "..." --format json
gitmemory query "..." --format markdown
gitmemory query "..." --tokens 8000
```

### MCP Server Interface

For integration with AI assistants via Model Context Protocol:

```typescript
// MCP Tool definitions
tools: [
  {
    name: "gitmemory_query",
    description: "Query repository history for relevant context",
    parameters: {
      query: { type: "string", description: "Natural language query" },
      repository: { type: "string", optional: true },
      token_budget: { type: "number", optional: true }
    }
  },
  {
    name: "gitmemory_entity_history",
    description: "Get history of a specific code entity",
    parameters: {
      entity_name: { type: "string" },
      entity_type: { type: "string", enum: ["function", "class", "file"] }
    }
  },
  {
    name: "gitmemory_recent_changes",
    description: "Get recent changes to repository or path",
    parameters: {
      path: { type: "string", optional: true },
      days: { type: "number", optional: true, default: 7 }
    }
  }
]
```

---

## Incremental Processing

### Sync Strategy

```
Initial Sync:
1. Walk all commits from oldest to newest
2. Process in batches of N commits
3. Track progress in sync_state table
4. Resume from last successful batch on failure

Incremental Sync:
1. Fetch new commits since last sync (git log since_hash..HEAD)
2. Process new commits
3. Update sync state

Force Push Detection:
1. Check if stored HEAD still exists in repo
2. If not, find divergence point
3. Mark orphaned commits as "rewritten"
4. Process new history from divergence point
```

### Branch Handling

```
Strategies:
1. Main-only: Only process default branch
2. All-branches: Process all branches, track per-branch
3. Selective: User specifies branches to track

Merge Commits:
- Extract merge commit metadata
- Avoid double-processing changes already seen in feature branch
- Track which commits came from which branch
```

### Processing Queue

```typescript
interface ProcessingQueue {
  enqueue(commits: string[], priority?: number): Promise<void>;
  dequeue(batch_size: number): Promise<QueueItem[]>;
  markComplete(commit: string): Promise<void>;
  markFailed(commit: string, error: string): Promise<void>;
  retry(commit: string): Promise<void>;
  getStatus(): Promise<QueueStatus>;
}

interface QueueItem {
  commit_hash: string;
  repository_id: string;
  priority: number;
  attempts: number;
  last_error?: string;
  enqueued_at: Date;
}
```

---

## Security & Privacy

### Secret Detection

```
Scanning Points:
1. Commit messages (before storing)
2. Diff content (before storing)
3. Extracted design notes

Detection Methods:
- Regex patterns for common secrets (API keys, tokens)
- Entropy analysis for high-entropy strings
- Known secret patterns (AWS keys, GitHub tokens, etc.)

Actions on Detection:
- Flag commit with security_warning
- Redact secret from stored content
- Alert user during sync
```

### Access Control

```
For shared/team usage:
- Repository-level permissions
- Query audit logging
- Rate limiting per user/client

Data Isolation:
- Each repository has isolated storage namespace
- Cross-repo queries require explicit permission
- No data mixing between repos
```

### Data Retention

```
Configurable policies:
- Keep all history (default)
- Rolling window (last N days/commits)
- Size-based limits

Deletion:
- Hard delete from all stores
- Cascading delete of relationships
- Audit log of deletions
```

---

## Open Questions

### Architecture
- [ ] Should we support real-time/streaming updates via webhooks?
- [ ] How to handle monorepos with millions of files?
- [ ] Should entity resolution use ML or heuristics?

### Understanding Pipeline
- [ ] Which LLM provider/model to use by default?
- [ ] How to handle rate limits and costs?
- [ ] Should we support local/offline LLM models?
- [ ] What embedding model and dimensions?

### Storage
- [ ] What's the minimum viable storage stack for MVP?
- [ ] How to handle storage migrations?
- [ ] Should storage be pluggable or fixed?

### Retrieval
- [ ] How to evaluate retrieval quality?
- [ ] Should we support user feedback for ranking improvement?
- [ ] How to handle ambiguous queries?

### Integration
- [ ] What's the primary integration point? (CLI, MCP, API, library?)
- [ ] How to package for distribution?
- [ ] What's the configuration format?

---

## Glossary

| Term | Definition |
|------|------------|
| **Context Pack** | Structured output containing relevant repository knowledge, formatted for LLM consumption |
| **Entity** | A code element (function, class, method, file) tracked across history |
| **Understand** | The process of extracting meaning from raw Git data using LLM/ML |
| **Knowledge Graph** | Graph database storing entities and their relationships |
| **Design Note** | Extracted rationale or decision documentation from commits or comments |
| **Co-evolution** | Pattern where multiple entities frequently change together |
| **Token Budget** | Maximum number of tokens allowed in a Context Pack |
| **Sync** | Process of updating GitMemory with new commits from a repository |

---

## Appendix A: Example Walkthrough

**Scenario**: Developer asks "Why does signInViaSSO retry 3 times?"

**Query Processing**:
```
1. Parse query → identify entity "signInViaSSO" and concept "retry"
2. Vector search → find commits mentioning retry logic
3. Graph search → find commits that modified signInViaSSO
4. Merge → 12 candidate commits
5. Score → top 5 by relevance
6. Build Context Pack:
   - Summary: "The 3-retry logic was added in commit abc123 to handle
     intermittent SSO provider failures. Original issue #456 reported
     login failures during high load."
   - Timeline: 3 key changes to signInViaSSO over 6 months
   - Key commits: abc123 (added retry), def456 (tuned to 3), ghi789 (added backoff)
   - Design notes: "SSO provider has 99.9% uptime but occasional blips..."
```

---

## Appendix B: Technology Candidates

| Component | Candidates |
|-----------|------------|
| Git parsing | libgit2, isomorphic-git, simple-git |
| Code parsing | Tree-sitter, ast-grep |
| Vector DB | ChromaDB, Qdrant, Pinecone, Weaviate |
| Graph DB | Neo4j, DGraph, TypeDB, in-memory |
| Embeddings | OpenAI, Cohere, local (sentence-transformers) |
| LLM | Claude, GPT-4, local (Ollama) |
| Metadata DB | SQLite, PostgreSQL, DuckDB |

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2025-12-19 | Initial draft |
