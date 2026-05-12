# AGENTS — quick guide for AI coding agents

Priority reading (what to open first)
- `CLAUDE.md` (root) — high-level overview and module list.
- `common/CLAUDE.md` — shared infrastructure: repositories, `BaseService`, DTO mapper.
- `instructions.md` — frontend rules (React), E2E flow and CSS variables.
- `my-tools-app/CLAUDE.md` and `my-tools-app/src/main/java/com/bervan/toolsapp/security/SecurityConfig.java` — integration and security notes.

Key assumptions (short)
- Multi-module Maven project (root `pom.xml`) — most modules depend on `common`.
- Java 17, Spring Boot 3.2.8, Spring Data JPA (TABLE_PER_CLASS inheritance).
- Entities commonly extend `BervanOwnedBaseEntity` (owners), include a `deleted` soft-delete flag and support history via `@HistorySupported`.
- `BervanBaseRepositoryImpl.save()` auto-generates a UUID when `id == null`. IMPORTANT: entities persisted only via JPA CASCADE bypass this method — set UUID manually (`entity.setId(UUID.randomUUID())`).

Frontend and autoconfig (from `instructions.md`)
- Backend exposes form/column metadata from `src/main/resources/autoconfig/*.yml` via `GET /api/config` (`ViewAutoConfigLoader`).
- React MUST build table columns with `buildColumnsFromConfig<T>('EntityName', overrides)` and use `<DynamicForm entityName="EntityName" mode="save|edit" .../>` for create/edit forms.
- Use provided UI components: `Dialog` for modals and `InlineEditableField` for inline edits — look under `my-tools-react/src/components/ui/`.
- CSS rule: all colors and design tokens must reference `src/styles/variables.css` — do NOT hardcode color literals in CSS modules.

Integration E2E (Playwright + Spring Boot)
- Run from `my-tools-react/`:
```bash
npm run test:integration
```
- This starts `npm run dev:integration` (Vite on port 5173 proxying `/api`) and runs `mvn test -Dtest=ReactRunAllE2ETest -pl my-tools-app`.
- `ReactRunAllE2ETest` launches the backend with TestContainers (MariaDB + RabbitMQ) on port 9091 and creates a test user:
  - username: `testUser`, password: `testUser!2#4%6`
- Integration tests use `loginViaApi(page)` from `my-tools-react/e2e/integration/fixtures.ts` to POST `/api/auth/login` and set the returned JWT into `localStorage` via `addInitScript`.

Security and backend integration
- JWT + OTP are implemented; inspect `my-tools-app/security/*` (`JwtAuthenticationFilter`, `JwtService`, `CustomAuthenticationProvider`, `OTPService`, `AuthController`).
- `SecurityConfig` configures CORS, stateless sessions and permits `/api/auth/**`, `/api/config` and some TV/pocket routes.

Agent coding rules
- For owned entities (extend `BervanOwnedBaseEntity`) prefer controllers that extend `BaseOwnedController` — it provides standard endpoints and `@PostFilter` access checks.
- If an entity can be created via JPA CASCADE, set its `id` before persisting (UUID).
- After adding or changing view fields, update or add `src/main/resources/autoconfig/<Entity>.yml` (fields: `name`, `displayName`, `type`, `required`, `inSaveForm`, `inEditForm`, `strValues`).
- Use `BervanDTOMapper` for DTO ↔ model mapping; look for `@FieldMapperConfig`, `@PreCustomMappers`, `@PostCustomMappers` annotations.

Language
- Always write code, comments and documentation in English. This repository uses English as the source language for all new code, Javadoc, inline comments and README/CLAUDE updates.

Example: Adding a new entity — suggested flow
1. Create the JPA entity class under the appropriate module (e.g. `pocket-app/src/main/java/.../MyEntity.java`). Prefer extending `BervanOwnedBaseEntity<UUID>` when the entity is owned.
   - Add `@HistorySupported` if history is required.
   - If the entity may be persisted via JPA CASCADE from a parent, ensure you set `id` before persist: `entity.setId(UUID.randomUUID());`.
2. Add a Spring Data repository interface in the same module (extends relevant base repository). Rely on `BervanBaseRepositoryImpl` behaviour configured via `@EnableJpaRepositories` in `my-tools-app`.
3. Implement a service extending `BaseService<UUID, MyEntity>` (put business logic there).
4. Add a REST controller. If the entity extends `BervanOwnedBaseEntity`, extend `BaseOwnedController<MyEntity, UUID>` to get standard endpoints and `@PostFilter`-based access control. Otherwise provide a plain controller.
5. Add DTOs (if required) and configure `BervanDTOMapper` mappings with `@FieldMapperConfig` or custom mappers.
6. Add autoconfig metadata: create `src/main/resources/autoconfig/MyEntity.yml` in the module with fields used by React forms/tables. Example snippet:
```yaml
fields:
  - field: id
    name: id
    displayName: "ID"
    type: STRING
    required: true
    inSaveForm: false
    inEditForm: false
  - field: name
    name: name
    displayName: "Name"
    type: STRING
    required: true
    inSaveForm: true
    inEditForm: true
```
7. Add unit/integration tests for repository, service and controller. For E2E, update `my-tools-react` tests to use `loginViaApi(page)` and create required fixtures.
8. Update `CLAUDE.md` (module and/or root) with a short note about the new entity and any architectural decisions.
9. Build and test locally:
```bash
# build the module (or common first if you changed shared code)
mvn -pl common clean install -DskipTests
mvn -pl <module> clean install

# run tests for the module
mvn -pl <module> test
```
10. If the entity is surfaced to the React UI, run the integration flow to validate the autoconfig-driven forms:
```bash
cd my-tools-react && npm run dev:integration
# then run ReactRunAllE2ETest from my-tools-app (separate shell)
mvn -Dtest=ReactRunAllE2ETest -pl my-tools-app test
```

Where to find examples
- UUID/repo behaviour: `common/src/main/java/com/bervan/common/BervanBaseRepositoryImpl.java`
- Autoconfig loader: `common/src/main/java/com/bervan/common/config/ViewAutoConfigLoader.java`
- Frontend patterns: `instructions.md` and `my-tools-react/src/components/ui/*`
- Security bootstrap: `my-tools-app/src/main/java/com/bervan/toolsapp/security/SecurityConfig.java`
- E2E runner/test: `my-tools-app/src/test/java/ReactRunAllE2ETest.java`

Quick commands
```bash
# Build common first
mvn -pl common clean install -DskipTests

# Build all modules
mvn clean install -DskipTests

# Run integration e2e (from my-tools-react/)
cd my-tools-react && npm run test:integration
```

Documenting changes
- Update root `CLAUDE.md` and module `CLAUDE.md` files when making significant architectural changes.
- If you change `common` behaviour (repositories/mapper/security), add a note to `common/CLAUDE.md`.

If you want, I can expand this file with dedicated checklists for: "adding a new entity", "migrating a React view" or "writing an E2E test".

