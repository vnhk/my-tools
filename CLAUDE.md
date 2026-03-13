# My Tools - Project Notes

> **IMPORTANT**: Keep this file updated when making significant changes to the codebase. This file serves as persistent memory between Claude Code sessions.

## Overview
Multi-module Maven project (`com.bervan:my-tools`) — a suite of personal productivity and lifestyle applications built on a shared Spring Boot + Vaadin framework. All modules share common infrastructure from `common-vaadin` and `core` libraries.

## Modules

| Module | Description |
|--------|-------------|
| `common-vaadin` | Shared Vaadin base components, services, auth, search |
| `pocket-app` | Personal note storage with encrypted items in "pockets" |
| `invest-track-app` | Investment portfolio tracking, FIRE projections, budget management |
| `spreadsheet-app` | Browser-based spreadsheet editor with formula support |
| `project-mgmt-app` | Project management |
| `canvas-app` | Collaborative canvas/notebook with draggable elements |
| `streaming-platform-app` | Video streaming platform |
| `interview-app` | Technical interview management and live interview conductor |
| `my-tools-vaadin-app` | Main deployable Vaadin app integrating all modules |
| `english-text-stats-app` | Ebook/text analysis for vocabulary learning |
| `file-storage-app` | File manager: disk storage + DB metadata |
| `learning-language-app` | Flashcard-based language learning |
| `shopping-stats-server-app` | Product price monitoring and shopping analytics |
| `cook-book` | Digital recipe manager with fridge-based search |

## Shared Architecture Patterns

All modules follow the same conventions:
- **Framework**: Spring Boot 3.0.4 + Vaadin 24.4.8 + Java 17
- **Persistence**: Spring Data JPA, TABLE_PER_CLASS inheritance
- **Entities**: Extend `BervanOwnedBaseEntity` (multi-tenancy), `deleted` flag (soft deletes)
- **History**: `@HistorySupported` annotation + `Set<History*>` for audit trail
- **Services**: Extend `BaseService<UUID, Entity>`, use `@PostFilter` for security
- **Views**: Extend `AbstractBervanTableView` or `AbstractBervanEntityView`
- **Config**: `src/main/resources/autoconfig/*.yml` — auto-generates UI form/table columns
- **Excel I/E**: `ExcelIEEntity<UUID>` for import/export support

## Build

```bash
# Build all modules (from root)
mvn clean install -DskipTests

# Build individual module
cd <module> && mvn clean install -DskipTests
```

## Individual Module Notes
Each module has its own `CLAUDE.md` with detailed architecture notes:
- See `canvas-app/CLAUDE.md`, `cook-book/CLAUDE.md`, `english-text-stats-app/CLAUDE.md`
- See `file-storage-app/CLAUDE.md`, `interview-app/CLAUDE.md`, `pocket-app/CLAUDE.md`
- See `shopping-stats-server-app/CLAUDE.md`, `spreadsheet-app/CLAUDE.md`
- See `invest-track-app/CLAUDE.md`, `learning-language-app/CLAUDE.md`
- See `streaming-platform-app/CLAUDE.md`, `project-mgmt-app/CLAUDE.md`
- See `my-tools-vaadin-app/CLAUDE.md`, `common-vaadin/CLAUDE.md`

## Important Notes
1. All modules depend on `common-vaadin` which must be built first
2. Docker: each module has a multi-stage Dockerfile; root `docker-compose.yml` for full stack
3. `env_my_tools` — environment configuration file
4. External scraper modules in `profile-stealth/` (shopping-stats scraper)
