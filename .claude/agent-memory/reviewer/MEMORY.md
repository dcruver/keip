# Reviewer Agent Memory

## Project: keip (Kubernetes Enterprise Integration Patterns)

### Architecture
- Monorepo: webapp/ (Python 3.11 Starlette), operator/ (K8s manifests), minimal-app/ (Java Spring Boot)
- Webapp is a Metacontroller webhook that generates Deployment/Service manifests from IntegrationRoute CRs
- CRD at operator/crd/crd.yaml, two versions: v1alpha1 (deprecated), v1alpha2 (current)

### Webapp Code Layout
- `app.py` - Starlette app factory with CORS middleware
- `config.py` - Uses Starlette Config with .env file support
- `models.py` - Pydantic v2 models for deploy route validation
- `core/sync.py` - Core webhook logic, generates K8s Deployment + Service dicts
- `core/k8s_client.py` - K8s API client for deploy route (uses global mutable state)
- `routes/webhook.py` - Generic webhook builder with JSON error handling
- `routes/deploy.py` - Direct K8s deployment endpoint
- `addons/certmanager/main.py` - cert-manager Certificate generation
- `logconf.py` - Logging config with env var LOG_LEVEL

### Key Conventions
- Python formatted with black, linted with ruff
- Starlette (not FastAPI) as ASGI framework
- Pydantic v2 for validation
- Tests adjacent to source in test/ subdirectories
- Container images to ghcr.io/codice

### Known Issues (as of 2026-02-19, branch: upgrade)
- CI scripts reference stale paths: operator/webapp (should be webapp/), core-controller.yaml (should be webhook-deployment.yaml)
- README.md quick start and several example docs still reference deprecated v1alpha1 API
- deploy.py bug fixed: created_resources now uses .extend() correctly (was = overwrite)
- minimal-app renamed to keip-integration; has dual build: Jib in pom.xml + standalone Dockerfile
- GitHub Actions: mixed SHA/tag pinning; third-party actions in release jobs only tag-pinned
- Webapp Dockerfile now uses python:3.11-slim (unpinned patch)
- k8s_client.py uses global mutable state with threading.Lock for lazy init
- webhook.py catches KeyError as 400 but does not catch other unexpected exceptions (they become 500s)
- Route model xml field has no length validation
- Hardcoded JKS truststore password "changeit" in sync.py line 302
