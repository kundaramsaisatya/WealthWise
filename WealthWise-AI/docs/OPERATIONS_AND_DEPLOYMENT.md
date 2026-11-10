# WealthWise AI operations and deployment notes

## AMFI NAV refresh behavior

The risk endpoints now read the local AMFI SQLite cache first. If a requested ISIN has uncached ranges, the endpoint schedules the existing bounded AMFI refresh as a FastAPI background task and returns risk results from currently cached observations and uploaded statement history. The request does not wait for external AMFI range downloads.

Important deployment limits:

- FastAPI in-process background tasks are best-effort, not a durable job queue. A process restart or deployment termination can interrupt a refresh. A later risk request schedules it again.
- The background task runs in the API process. Use a persistent external queue and dedicated worker before horizontal scaling or if guaranteed completion is required.
- Set WEALTHWISE_DATA_DIR to an absolute path on a persistent mounted volume. The AI service stores uploaded statements, per-client FAISS indexes/documents, structured portfolio JSON and (by default) the AMFI SQLite cache under this directory.
- AMFI_NAV_CACHE_PATH optionally overrides the SQLite file location. If it points outside WEALTHWISE_DATA_DIR, mount and back up that location separately.
- The data directory contains sensitive financial documents and derived data. Restrict filesystem permissions to the AI service account, encrypt the volume and backups, define retention/deletion procedures, and never expose it through the web server.
- Do not put the SQLite database, WAL or SHM files, uploaded statements, portfolio JSON, or vector indexes in source control.
- For multiple API replicas, do not use separate local SQLite files as if they were a shared cache. Use a shared database/cache and a durable worker queue.
- Each ISIN is limited to two date-range fetches per refresh run. The three-year history is progressively backfilled across runs.
- The cache is a scheme-level public NAV source, not a folio-specific return record.

## Runtime configuration

Required environment variables:

- SESSION_SECRET: a random secret with at least 32 characters.
- AI_SERVICE_SECRET: a separate random secret with at least 32 characters, shared only between the Node.js service and the Python AI service.
- MONGODB_URI: MongoDB connection string.
- AI_SERVICE_URL: private/internal URL for the Python service.
- WEALTHWISE_DATA_DIR: optional absolute path to persistent storage for uploaded files, vector indexes, structured portfolio files and the default AMFI cache.
- AMFI_NAV_CACHE_PATH: optional absolute path to a persistent SQLite database file; overrides the default path under WEALTHWISE_DATA_DIR.

Never commit .env, credentials, session secrets, API keys, customer statements, or database files.

## Pre-deployment checklist

1. Configure TLS at the ingress or reverse proxy and redirect HTTP to HTTPS.
2. Set secure cookies in production and configure Express trust proxy only for known trusted proxies.
3. Restrict the Python service to private network access; retain service-secret authentication on internal endpoints.
4. Use a shared rate-limit store such as Redis before running multiple Node.js replicas. The current in-memory limiter is per process.
5. Set WEALTHWISE_DATA_DIR to a persistent volume for the complete AI-service data directory; back it up and test restore. If AMFI_NAV_CACHE_PATH is overridden, persist that location too.
6. Set CPU, memory, request-body and request-time limits at the platform ingress and service level.
7. Pin and regularly update dependencies; run dependency and container vulnerability scans.
8. Configure log retention and redaction. Never log tokens, session cookies, full account identifiers or uploaded document contents.
9. Verify MongoDB backups, least-privilege credentials, network allowlists and encryption at rest.
10. Test account-holder isolation and cross-user access controls in the deployed environment.
11. Monitor AMFI provider failures, cache growth, background-task interruptions and API latency.
12. Obtain qualified financial-domain and compliance review of scoring rules before using them to guide customer investment decisions.

## Analytics interpretation

- Portfolio snapshot percentage changes are not time-weighted returns or XIRR and are not adjusted for external deposits or withdrawals.
- NAV changes are not investor returns; distributions, fees, taxes and cash flows are not adjusted.
- Per-observation NAV volatility is not annualized.
- Sector and issuer exposure are only as complete as the metadata supplied in uploaded records. Coverage is displayed separately.
- Missing data is not evidence of low risk.
- Risk scores are illustrative product heuristics, not regulated ratings, loss probabilities or suitability assessments.
