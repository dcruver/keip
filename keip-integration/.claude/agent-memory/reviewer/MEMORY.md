# Reviewer Agent Memory

## Project Structure
- Monorepo root: /home/dcruver/Projects/keip
- Three artifacts: webapp/ (Python Starlette), operator/ (K8s manifests), keip-integration/ (Java Spring Boot)
- Tests in webapp live in adjacent test/ subdirectories with JSON fixtures in json/ dirs
- Python formatted with black, linted with ruff
- Java uses Spring Boot 4.0.2, Java 21, Jib for container builds

## Key Conventions
- Webapp uses Starlette (not FastAPI), Pydantic for validation
- K8s manifests via kustomize (no Helm)
- Metacontroller v4.11.6 for CRD watching
- CRD versions: v1alpha2 (storage), v1alpha1 (deprecated)
- Container images at ghcr.io/codice

## Review History
- Session 1 (2026-02-18): Comprehensive review on upgrade branch. Many fixes already applied including security contexts, non-root Dockerfiles, thread-safe k8s_client, probe additions, PDB, RBAC tightening, various bug fixes.
