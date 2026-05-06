# Instructions for AI model

## Migration from Vaadin to React

### General Rules
- All Vaadin views MUST be migrated to React (100% coverage required).
- After migrating any view, ALWAYS double-check that the migration is complete and correct.
- Do NOT skip any view or component.
- Migration must be consistent across the entire project.
- Update this document as needed.

---

### Backend Migration (Vaadin → REST)

To implement a controller, ALWAYS use:
- `BaseOwnedController`
    - path: `rc/main/java/com/bervan/common/controller/BaseOwnedController.java`

Reference example (MANDATORY):
- `/interview-app/src/main/java/com/bervan/interviewapp/view/InterviewQuestionsRestController.java`
- `/pocket-app/src/main/java/com/bervan/pocketapp/pocketitem/api/PocketItemRestController.java`

#### Rules:
- Convert Vaadin Views into REST Controllers.
- REST controllers MUST be placed in the **module itself** (e.g. `project-mgmt-app/api/`), NOT in `my-tools-vaadin-app`.
  - `my-tools-vaadin-app` is integration/deployment only — modules must be self-sufficient.
  - All modules have `spring-web` available transitively via `vaadin-spring-boot-starter`.
- ALWAYS follow the provided example.
- DO NOT invent your own patterns.
- If the example does NOT cover required functionality:
    - STOP
    - Inform the user BEFORE making changes.

#### UUID Generation
- `BervanBaseRepositoryImpl.save()` **auto-generates UUID** if `entity.getId() == null`.
- Entities persisted via **JPA CASCADE** (not through their own repository) do **NOT** go through `BervanBaseRepositoryImpl` → UUID must be set **manually**: `entity.setId(UUID.randomUUID())`.
- Example: `TaskRelation` is persisted via cascade on `Task.parentRelationships` → **MUST** set id manually.

#### `super.update()` — When to use vs. manual update
- `BaseOwnedController.super.update()` uses `getDeclaredFields()` on the newly-mapped model and copies **ALL** fields (including `null` collections) onto the original entity.
- **Safe to use** for entities with no owned collections (e.g. simple entities like `Question`, `Project`... but Project has `Set<Task> tasks`).
- **Use manual update** for entities **with collections** (e.g. `Task` with `parentRelationships`, `childRelationships`): load the original entity, update only the intended scalar fields, then save. Never use `super.update()` when the entity has `Set<?>` or `List<?>` fields — it will null them out.

#### DTO Files

**Every DTO, request, and response class MUST be in its own separate `.java` file — NO EXCEPTIONS.**
- Never define DTOs, request objects, or response records as inner classes or `record`s inside a controller.
- Place all DTO files in the same `api/` package as the controller (e.g. `project-mgmt-app/.../api/TaskDto.java`).
- Always use @Getter @Setter @NoArgConstructor and @AllArgsConstructor and class. Do not use recrods for dtos.

#### DTO Mapping

**Any entity (model) that is mapped to/from a DTO MUST implement `BaseModel<ID>`** (from `com.bervan.core.model`):
```java
public interface BaseModel<ID> {
    ID getId();
    void setId(ID id);
}
```
`BervanDTOMapper.map(BaseModel<ID> model, DtoClass)` requires this — compilation will fail without it.
`BervanOwnedBaseEntity` already implements `BaseModel<UUID>`, so all standard entities are covered automatically.
Only custom/lightweight model classes used as mapping targets need to explicitly implement it.

**Any DTO that is the target of auto-mapping (including nested DTOs inside collections) MUST implement `BaseDTO<ID>`**:
```java
public interface BaseDTO<ID> {
    ID getId();
    void setId(ID id);
    Class<? extends BaseModel<ID>> dtoTarget(); // tells the mapper which model class this DTO maps to
}
```
This is how the mapper knows what model class to instantiate when mapping a `List<TaskRelation>` → `List<TaskRelationDto>`. Without `BaseDTO`, nested collection elements cannot be auto-mapped.

**Rule**: If a DTO appears as an element type in a `List<?>` or `Set<?>` field of another DTO, it **must** implement `BaseDTO<UUID>` with the correct `dtoTarget()`. Example:
```java
// TaskRelationDto is used as List<TaskRelationDto> in TaskDetailDto → must implement BaseDTO
public class TaskRelationDto implements BaseDTO<UUID> {
    // ...
    @Override
    public Class<? extends BaseModel<UUID>> dtoTarget() {
        return TaskRelation.class; // the model this DTO maps to
    }
}
```
And the corresponding model (`TaskRelation`) must also implement `BaseModel<UUID>` — `BervanOwnedBaseEntity` does this, but if a model only extends `BervanOwnedBaseEntity` without overriding the interface, verify it's on the class signature:
```java
// If not already covered by BervanOwnedBaseEntity, add explicitly:
public class TaskRelation extends BervanOwnedBaseEntity<UUID> implements ExcelIEEntity<UUID>, BaseModel<UUID> { ... }
```

`BaseOwnedController` handles all mapping automatically via `BervanDTOMapper`:
- **DTO → Model**: `mapper.map(dto)` — used internally in `create()` and `update()`
- **Model → DTO**: `mapper.map(model, DtoClass.class)` — used internally in `getById()`, `load()`, `create()`, `update()`

For **simple fields** (same name + compatible type): no extra code needed — mapped automatically.

For **complex fields** (type conversion, related entity lookup, custom logic):
- Annotate the DTO field with `@FieldMapperConfig`
- Implement `DefaultCustomMapper<FROM, TO>` as a Spring `@Service`

##### `@FieldMapperConfig` — Bidirectional

`@FieldMapperConfig` works in **both directions**:
- **DTO → Model**: annotation on the DTO field; `targetFieldNames` names the model field to write
- **Model → DTO**: the mapper scans DTO fields looking for `@FieldMapperConfig` whose `targetFieldNames` contains the current model field name — if found, writes to that DTO field

This means annotating a DTO field once covers both create/update (DTO→Model) AND read (Model→DTO).

**Dot-path support in `targetFieldNames`**: use `"project.id"` to read/write nested model fields.
```java
// In TaskDetailDto — reads task.project.id → projectId, and writes projectId → task.project.id
@FieldMapperConfig(targetFieldNames = "project.id")
private UUID projectId;

@FieldMapperConfig(targetFieldNames = "project.number")
private String projectNumber;

@FieldMapperConfig(targetFieldNames = "project.name")
private String projectName;
```

**With a custom mapper** (for type conversion or entity lookup):
```java
// In TaskCreateRequest — mapper converts UUID → Project entity
@FieldMapperConfig(mapper = ToProjectMapper.class, targetFieldNames = "project")
private UUID projectId;
```
```java
// Mapper implementation (updated signature — Field args are required):
@Service
public class ToProjectMapper implements DefaultCustomMapper<UUID, Project> {
    @Override
    public Project map(UUID projectId, Field fromField, Field toField) {
        return projectService.loadById(projectId).orElse(null);
    }
    @Override public Class<UUID> getFrom() { return UUID.class; }
    @Override public Class<Project> getTo() { return Project.class; }
}
```

**Collection accumulation**: if the DTO target field is already a `Collection`, the mapper **adds** to it (not replaces). This lets multiple model fields feed into one DTO list — e.g. `task.parentRelationships` and `task.childRelationships` both accumulate into `dto.someList`.

Reference example:
- `pocket-app/src/main/java/com/bervan/pocketapp/pocketitem/api/PocketItemCreateRequest.java`
- `pocket-app/src/main/java/com/bervan/pocketapp/pocketitem/api/ToPocketMapper.java`
- `project-mgmt-app/.../api/TaskDetailDto.java` (dot-path + PostMapper pattern)
- `project-mgmt-app/.../api/ToProjectMapper.java`

##### `PreMapper` / `PostMapper` — for complex cases

Use `PreMapper` / `PostMapper` when you need custom logic that runs **before** or **after** the automatic field mapping. Declare them on the DTO class with `@PreCustomMappers` / `@PostCustomMappers`.

**When to use PostMapper** (most common):
- Combining multiple DTO fields into one (e.g. merging `parentRelationships` + `childRelationships` → `relations`)
- Post-processing auto-mapped values (setting direction flags, resolving display names, etc.)
- Any logic that depends on already-mapped fields

```java
// Declare on the DTO class:
@PostCustomMappers(mappers = {TaskToDetailsPostMapper.class})
public class TaskDetailDto {
    @JsonIgnore
    private List<TaskRelationDto> parentRelationships; // auto-mapped from task
    @JsonIgnore
    private List<TaskRelationDto> childRelationships;  // auto-mapped from task
    private List<TaskRelationDto> relations;           // populated by PostMapper
}
```
```java
// PostMapper implementation:
@Service
public class TaskToDetailsPostMapper implements PostMapper<Task, TaskDetailDto> {
    @Override
    public void map(Task task, TaskDetailDto dto) {
        List<TaskRelationDto> relations = new ArrayList<>();
        for (TaskRelationDto r : dto.getParentRelationships()) {
            r.setDirection("CHILD");
            // set relatedTask fields from r.getChild()...
            relations.add(r);
        }
        for (TaskRelationDto r : dto.getChildRelationships()) {
            r.setDirection("PARENT");
            // set relatedTask fields from r.getParent()...
            relations.add(r);
        }
        dto.setRelations(relations);
    }
    @Override public Class<Task> getFromType() { return Task.class; }
    @Override public Class<TaskDetailDto> getToType() { return TaskDetailDto.class; }
}
```

**`PreMapper`** — runs before field mapping; use when the source object needs to be pre-processed or target needs initialization before fields are copied.
```java
@Service
public class MyPreMapper implements PreMapper<MyModel, MyDto> {
    @Override
    public void map(MyModel from, MyDto to) { /* initialize to before field mapping */ }
}
```
Declare with: `@PreCustomMappers(mappers = {MyPreMapper.class})` on the DTO class.

**Do NOT write manual `toXxxDto()` helper methods** for complex mappings — use `PostMapper` instead. Manual helpers duplicate logic that the mapper handles automatically and make the mapping non-reusable.

---

### Frontend Migration (Vaadin → React)
#### React project structure
Path: ~/IdeaProjects/my-tools-react
[src](../my-tools-react/src)
[api](../my-tools-react/src/api)
[assets](../my-tools-react/src/assets)
[auth](../my-tools-react/src/auth)
[components](../my-tools-react/src/components)
[hooks](../my-tools-react/src/hooks)
[pages](../my-tools-react/src/pages)
[cook-book](../my-tools-react/src/pages/cook-book)
[files](../my-tools-react/src/pages/files)
[interview](../my-tools-react/src/pages/interview)
[invest-track](../my-tools-react/src/pages/invest-track)
[pocket](../my-tools-react/src/pages/pocket)
[streaming-platform](../my-tools-react/src/pages/streaming-platform)
[NotFoundPage.module.css](../my-tools-react/src/pages/NotFoundPage.module.css)
[NotFoundPage.tsx](../my-tools-react/src/pages/NotFoundPage.tsx)
[styles](../my-tools-react/src/styles)
[types](../my-tools-react/src/types)
[utils](../my-tools-react/src/utils)
[App.css](../my-tools-react/src/App.css)
[App.tsx](../my-tools-react/src/App.tsx)
[index.css](../my-tools-react/src/index.css)
[main.tsx](../my-tools-react/src/main.tsx)
- Each module MUST have its own folder.
- Structure should be modular and consistent.
- Update the structure as needed.

#### Visual Consistency Rule
**MANDATORY**: All modules (except `streaming-platform`) must look identical — same buttons, inputs, dropdowns, badges, cards. Never invent one-off styled elements; always use the shared components below.

#### Shared UI Components
All shared components are in `src/components/`. Use them everywhere. Do NOT create raw `<button>`, `<select>`, `<input>` with custom inline styles when a shared component exists.

##### `Button` — `src/components/ui/Button.tsx`
```tsx
<Button variant="primary" size="sm">Save</Button>
<Button variant="secondary" size="md">Cancel</Button>
<Button variant="success" size="sm">Confirm</Button>
<Button variant="danger" size="sm">Delete</Button>
<Button variant="ghost" size="sm">← Back</Button>
```
Variants: `primary` (purple gradient, main CTA), `secondary` (glass, general actions), `success` (green), `danger` (red), `ghost` (transparent, navigation/back links).
Sizes: `sm`, `md` (default), `lg`.

##### `Badge` — `src/components/ui/Badge.tsx`
```tsx
<Badge color="success">Done</Badge>
<Badge color="warning">In Progress</Badge>
<Badge color="info">Open</Badge>
<Badge color="danger">Critical</Badge>
<Badge color="neutral">Canceled</Badge>
<Badge color="primary">Featured</Badge>
```
Colors map to CSS variables (`--color-*-subtle` background, `--color-*` text).

##### `StatusBadge` — `src/components/ui/StatusBadge.tsx`
Wrapper around `Badge` — automatically picks the right color for task/project statuses and priorities.
```tsx
<StatusBadge value={row.status} />   // Open→info, In Progress→warning, Done→success, Canceled→neutral
<StatusBadge value={row.priority} /> // Low→neutral, Medium→warning, High→danger, Critical→danger
```
Use in table column overrides for `status` and `priority` columns.

##### `CustomSelect` — `src/components/fields/CustomSelect.tsx`
Fully styled dropdown with keyboard navigation, animations. Replaces all native `<select>`.
```tsx
<CustomSelect
  options={[{ value: 'a', label: 'Option A' }, ...]}
  value={selected}
  onChange={(v) => setSelected(String(v))}
  size="sm"   // optional, for compact layouts
/>
```

##### `TextField` — `src/components/fields/TextField.tsx`
```tsx
<TextField label="Name" value={val} onChange={(e) => setVal(e.target.value)} error={errors.name} />
```
For standalone inputs without label, import `Field.module.css` and apply `fieldStyles.input` class directly to a raw `<input>`:
```tsx
import fieldStyles from '../../components/fields/Field.module.css'
<input className={fieldStyles.input} ... />
```

##### `TextArea` — `src/components/fields/TextArea.tsx`
```tsx
<TextArea value={text} onChange={(e) => setText(e.target.value)} />
```
Same styling as TextField. Use for description/note editors.

##### `InlineEditableField` — `src/components/ui/InlineEditableField.tsx`
Click-to-edit field with auto-save. Used on detail pages instead of always-visible form inputs.
```tsx
<InlineEditableField
  label="Status"
  value={item.status}
  fieldType="COMBOBOX"   // TEXT | NUMBER | DATE | COMBOBOX | MULTI_SELECT
  options={STATUSES}
  onSave={(v) => patch({ status: String(v) })}
/>
```

##### `Dialog` — `src/components/ui/Dialog.tsx`
All modals/popups must use `Dialog`. Never build custom overlays.
```tsx
<Dialog open={open} title="Edit Item" onClose={() => setOpen(false)} onConfirm={handleSave} confirmLabel="Save">
  <DynamicForm ... />
</Dialog>
```

##### `DynamicForm` — `src/components/ui/DynamicForm.tsx`
Auto-generates form fields from backend YML config. Use together with `buildColumnsFromConfig`.
```tsx
<DynamicForm entityName="Task" mode="save" values={draft} onChange={(f, v) => setDraft(s => ({...s, [f]: v}))} errors={errors} />
```

#### Rules:
- Every Vaadin View must have a corresponding React implementation.
- Do NOT partially migrate components — full migration required.

#### React Table Views (from `AbstractBervanTableView`)
If the Vaadin view extended `AbstractBervanTableView` (or any subclass):
- React table columns MUST be built with `buildColumnsFromConfig<T>('EntityName', overrides)` — values come from the backend YML autoconfig files.
- Create/Edit forms MUST use `<DynamicForm entityName="EntityName" mode="save"|"edit" .../>` — fields come from the same YML.
- Do NOT hardcode column names or form fields; they are defined in `src/main/resources/autoconfig/*.yml`.
- See `PocketListPage.tsx` as the reference example for this pattern.

#### React Detail Views (from `AbstractPageView`)
If the Vaadin view extended `AbstractPageView` (custom detail/edit page):
- Implement custom inline editing in React (click-to-edit fields, auto-save on blur/Enter).
- Use the existing `InlineEditableField` component from `components/ui/InlineEditableField.tsx`.
- See `RecipeDetailPage.tsx` as a reference for inline editing patterns.

#### CSS Variables — ALL colors must use variables
**MANDATORY RULE**: Never use hardcoded color values (hex, rgb, rgba) in CSS module files.
All colors, shadows, borders, backgrounds must reference variables from `src/styles/variables.css`.

**Why**: Shared variables allow global theme changes without hunting through every `.module.css` file.
If a variable for a needed value does not yet exist, **add it to `variables.css`** first, then reference it.

##### Available CSS variables (defined in `src/styles/variables.css`)

**Base colors:**
- `--color-bg`, `--color-bg-elevated` — page backgrounds
- `--color-surface`, `--color-surface-hover`, `--color-surface-active` — surface layers
- `--color-border`, `--color-border-strong` — borders
- `--color-text-primary`, `--color-text-secondary`, `--color-text-tertiary` — text
- `--color-primary`, `--color-primary-dark`, `--color-primary-hover`, `--color-primary-glow`, `--color-primary-subtle` — brand/accent
- `--color-success`, `--color-success-subtle` — green
- `--color-warning`, `--color-warning-subtle` — orange/yellow
- `--color-danger`, `--color-danger-subtle` — red
- `--color-info`, `--color-info-subtle` — blue

**Glass / Blur:**
- `--glass-bg`, `--glass-surface`, `--glass-border` — glass-morphism card backgrounds

**Shadows:**
- `--shadow-sm`, `--shadow-md`, `--shadow-lg`, `--shadow-xl` — elevation shadows
- `--shadow-glow`, `--shadow-glow-sm` — primary glow effects

**Spacing:** `--space-xs(4px)`, `--space-sm(8px)`, `--space-md(16px)`, `--space-lg(24px)`, `--space-xl(36px)`, `--space-2xl(48px)`

**Radii:** `--radius-xs(4px)`, `--radius-sm(8px)`, `--radius-md(12px)`, `--radius-lg(18px)`, `--radius-xl(24px)`, `--radius-pill(9999px)`

**Typography:** `--font-sans`, `--font-mono`, `--font-size-xs(11px)`, `--font-size-sm(13px)`, `--font-size-md(15px)`, `--font-size-lg(18px)`, `--font-size-xl(24px)`, `--font-size-2xl(32px)`, `--line-height-tight(1.25)`, `--line-height-normal(1.55)`

**Motion:** `--transition(0.16s ease)`, `--transition-slow(0.3s ease)`, `--spring(spring easing)`

**Component variables (cards, buttons, inputs, badges, tags — defined in `variables.css`):**
- `--card-bg`, `--card-border`, `--card-bg-elevated`, `--card-shadow`, `--card-radius`
- `--input-bg`, `--input-border`, `--input-border-focus`, `--input-color`
- `--btn-bg`, `--btn-border`, `--btn-color`, `--btn-hover-bg`
- `--btn-primary-bg/border/color/hover-bg`, `--btn-success-*`, `--btn-danger-*`
- `--status-open-bg/color`, `--status-in-progress-bg/color`, `--status-done-bg/color`, `--status-canceled-bg/color`
- `--priority-low-bg/color`, `--priority-medium-bg/color`, `--priority-high-bg/color`, `--priority-critical-bg/color`
- `--tag-bg`, `--tag-border`, `--tag-color`
- `--progress-track-bg`, `--progress-fill-color`
- `--mono-bg`, `--mono-color` — monospace number/code pill backgrounds
- `--relation-row-bg`, `--relation-row-hover-bg` — relation list rows (project management)

#### Already migrated views
- Update the list as needed.

---

### Deprecation Rules

After successful migration:

- The original Vaadin class (View or Component) MUST be marked as:
```java
@Deprecated
```
* The annotation must be applied to the ENTIRE class.

---

### Migration Tracking (THIS FILE)

* Every migrated element MUST be added to this .md file.
* This file must be continuously UPDATED.

Add entries for:

* Migrated Views
* Migrated Components
* Migrated Modules
* Created REST Controllers
* Created React Views
* Created E2E Tests

---

### E2E Tests (React) — Integration tests against a real backend, NO mocking

**MANDATORY**: After migrating any view, write integration e2e tests that hit the real backend. Tests with mocked API routes are **forbidden** for new work.

#### Infrastructure

The integration test stack consists of:
- **Spring Boot backend** started by `ReactRunAllE2ETest.java` via `@SpringBootTest` + TestContainers (MariaDB + RabbitMQ), on port 9091 (HTTP).
- **React dev server** with a proxy to the backend (`vite.integration.config.ts`, `npm run dev:integration`), on port 5173.
- **Playwright** (`playwright.integration.config.ts`, `testDir: ./e2e/integration/`).

Start everything with one command from `my-tools-react/`:
```bash
npm run test:integration
# which runs: scripts/run-integration-tests.sh
```

The shell script:
1. Starts `npm run dev:integration` (Vite → proxies `/api` → `http://localhost:9091`)
2. Runs `mvn test -Dtest=ReactRunAllE2ETest -pl my-tools-vaadin-app` → Spring Boot starts via TestContainers, creates test user, then runs Playwright as a subprocess

#### Test user (created by backend on startup)

`ReactRunAllE2ETest.java` calls `createTestUser()` before Playwright runs:
- username: `testUser`, password: `testUser!2#4%6`
- Everything else (pockets, tasks, etc.) must be created and torn down by the e2e tests themselves.

#### Writing integration tests

All integration tests go in `my-tools-react/e2e/integration/<module>/` and use the fixtures from `e2e/integration/fixtures.ts`.

**Login**: call `loginViaApi(page)` in `test.beforeEach`. It logs in via `POST /api/auth/login`, gets a real JWT, and stores it in `localStorage` via `addInitScript` so the React app treats the session as authenticated.

```typescript
import { test, expect, loginViaApi } from '../fixtures'

test.describe('MyModule — integration', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaApi(page)
  })

  test('create item, verify it appears, then delete it', async ({ page }) => {
    await page.goto('/my-module')
    await page.getByRole('button', { name: /New/i }).click()
    await page.getByLabel('Name').fill('E2ETestItem')
    await page.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByRole('cell', { name: 'E2ETestItem' })).toBeVisible()

    // cleanup
    await page.getByRole('row', { name: /E2ETestItem/ }).getByRole('checkbox').check()
    page.once('dialog', d => d.accept())
    await page.getByRole('button', { name: 'Delete' }).first().click()
    await expect(page.getByRole('cell', { name: 'E2ETestItem' })).not.toBeVisible()
  })
})
```

**Naming convention**: Use unique, obviously-test prefixes (e.g. `E2EPocket`, `E2ETask`) so test data is identifiable. Each test must clean up after itself (real database, not wiped between tests within a run).

**Reference**: `e2e/integration/pocket/pocket.spec.ts`

* E2E tests MUST also be listed in this file.

---

## Migration Log

### Migrated Views

**cook-book** (`my-tools-vaadin-app`):
* `DietDashboardView`
* `DietView`
* `IngredientListView`
* `RecipeDetailView`
* `RecipeListView`
* `RecipeSearchView`
* `ShoppingCartView`

**interview** (`my-tools-vaadin-app`):
* `InterviewQuestionsView`
* `InterviewHomeView`
* `StartInterviewView`
* `CodingTaskView`
* `InterviewPlanView`
* `QuestionConfigView`
* `InterviewSessionView`
* `InterviewSessionListView`
* `ImportExportInterviewDataView`

**invest-track** (`my-tools-vaadin-app`):
* `BudgetDashboardView`
* `ImportExportDataView`
* `InvestmentRecommendationView`
* `InvestmentWalletsView`
* `ReportRecommendationsView`
* `StockAlertViewStock`
* `WalletView`

**pocket** (`my-tools-vaadin-app`):
* `PocketItemsListView`
* `PocketItemsTableView`
* `PocketSideMenuView`
* `PocketTableView`

**project-mgmt-app** (`my-tools-vaadin-app`):
* `ProjectListView`
* `ProjectDetailsView`
* `AllTasksListView`
* `TaskDetailsView`

**project-mgmt-app** (module abstract views):
* `AbstractProjectListView`
* `AbstractProjectDetailsView`
* `AbstractAllTasksListView`
* `AbstractTaskDetailsView`
* `ProjectTaskListView`
* `TaskRelationsPanel`
* `ProjectsPageLayout`
* `StatusBadgeHelper`
* `TaskTypeIconHelper`

---

### Migrated Components

**common-vaadin**:
* `BervanImageViewer`
* `BervanJsonLogViewer`
* `AbstractAsyncTaskDetails`
* `AbstractAsyncTaskList`
* `AbstractBervanEntityView`
* `AbstractBervanTableDTOView`
* `AbstractBervanTableView`
* `AbstractDataIEView`
* `AbstractFiltersLayout`
* `AbstractHomePageView`
* `AbstractOneValueView`
* `AbstractPageNotFoundErrorView`
* `AbstractPageView`
* `AbstractLowCodeGeneratorView`

**cook-book**:
* `AbstractDietDashboardView`
* `AbstractDietView`
* `AbstractIngredientListView`
* `AbstractRecipeDetailView`
* `AbstractRecipeListView`
* `AbstractRecipeSearchView`
* `AbstractShoppingCartView`

**interview-app**:
* `AbstractInterviewQuestionsView`
* `AbstractInterviewHomeView`
* `AbstractStartInterviewView`
* `AbstractCodingTaskView`
* `AbstractInterviewPlanView`
* `AbstractQuestionConfigView`
* `AbstractInterviewSessionView`
* `AbstractInterviewSessionListView`
* `AbstractImportExportView`

**invest-track-app**:
* `AbstractImportExportData`
* `AbstractReportsRecommendationsView`
* `AbstractStockPriceAlertsView`
* `AbstractWalletView`
* `AbstractWalletsView`

**pocket-app**:
* `AbstractAllPocketItemsView`
* `AbstractPocketView`

---

### Migrated Modules

* `pocket-app`
* `interview-app`
* `invest-track-app`
* `cook-book`
* `file-storage-app`
* `streaming-platform-app`
* `project-mgmt-app`

---

### REST Controllers Created

**interview-app**:
* `interview-app/.../interviewapp/view/InterviewQuestionsRestController.java` (+ `/tags` and `/by-tag-difficulty` endpoints)
* `interview-app/.../interviewapp/api/CodingTaskRestController.java`
* `interview-app/.../interviewapp/api/QuestionConfigRestController.java`
* `interview-app/.../interviewapp/api/InterviewSessionRestController.java`
* `interview-app/.../interviewapp/api/InterviewPlanRestController.java`

**pocket-app**:
* `pocket-app/.../pocketapp/api/PocketRestController.java`
* `pocket-app/.../pocketapp/pocketitem/api/PocketItemRestController.java`

**my-tools-vaadin-app — cook-book**:
* `my-tools-vaadin-app/.../views/cookbook/CookBookRestController.java`
* `my-tools-vaadin-app/.../views/cookbook/DietRestController.java`

**invest-track-app** (in-module, `com.bervan.investtrack.api`):
* `WalletRestController` — extends `BaseOwnedController<Wallet, UUID>`; includes snapshot sub-resource endpoints
* `StockAlertRestController` — extends `BaseOwnedController<StockPriceAlert, UUID>`; manual create/update due to nested `StockPriceAlertConfig` + emails collection
* `BudgetEntryRestController` — plain REST (cannot use `BaseOwnedController`: `BudgetEntry extends BervanBaseEntity`, not `BervanOwnedBaseEntity`)
* `InvestmentRecommendationRestController` — plain REST (same reason as above)
* `InvestDashboardRestController` — analytics aggregator, no CRUD entity
* `StockReportRestController` — async trigger + report reader
* `DataIERestController` — import/export

**streaming-platform-app**:
* `streaming-platform-app/.../streamingapp/ProductionsApiController.java`
* `streaming-platform-app/.../streamingapp/StreamingAdminApiController.java`
* `streaming-platform-app/.../streamingapp/VideoController.java`
* `streaming-platform-app/.../streamingapp/tv/PairingApiController.java`

**file-storage-app**:
* `file-storage-app/.../filestorage/FileStorageApiController.java`

**project-mgmt-app** (in-module, as per rule):
* `project-mgmt-app/.../projectmgmtapp/api/ProjectRestController.java`
* `project-mgmt-app/.../projectmgmtapp/api/TaskRestController.java`

---

### React Views Created

**pocket** (`my-tools-react/src/pages/pocket/`):
* `PocketListPage.tsx`
* `PocketItemsPage.tsx`

**interview** (`my-tools-react/src/pages/interview/`):
* `QuestionListPage.tsx`
* `CodingTaskListPage.tsx`
* `QuestionConfigListPage.tsx`
* `InterviewSessionListPage.tsx`
* `InterviewSessionPage.tsx`
* `StartInterviewPage.tsx`
* `InterviewPlanPage.tsx`
* `InterviewLayout.tsx`

**invest-track** (`my-tools-react/src/pages/invest-track/`):
* `DashboardPage.tsx`
* `WalletListPage.tsx`
* `WalletDetailPage.tsx`
* `BudgetEntriesPage.tsx`
* `StockAlertsPage.tsx`
* `RecommendationsPage.tsx`
* `StockReportPage.tsx`
* `DataIEPage.tsx`

**cook-book** (`my-tools-react/src/pages/cook-book/`):
* `RecipeListPage.tsx`
* `RecipeDetailPage.tsx`
* `FridgeSearchPage.tsx`
* `ShoppingCartPage.tsx`
* `IngredientsPage.tsx`
* `DietPage.tsx`
* `DietDashboardPage.tsx`

**streaming-platform** (`my-tools-react/src/pages/streaming-platform/`):
* `ProductionListPage.tsx`
* `ProductionDetailsPage.tsx`
* `VideoPlayerPage.tsx`
* `RemoteControlPage.tsx`
* `TvPairingPage.tsx`

**files** (`my-tools-react/src/pages/files/`):
* `FilesPage.tsx`

**general** (`my-tools-react/src/pages/`):
* `AsyncTaskListPage.tsx`
* `AsyncTaskDetailsPage.tsx`
* `LowCodeGeneratorPage.tsx`

**projects** (`my-tools-react/src/pages/projects/`):
* `ProjectListPage.tsx`
* `ProjectDetailsPage.tsx`
* `AllTasksPage.tsx`
* `TaskDetailsPage.tsx`

---

### E2E Tests Created

#### Mocked (legacy — do not add more of these)
* `e2e/app.spec.ts` — general app smoke test
* `e2e/pocket/pocket-list.spec.ts` — Pocket: list pockets flow
* `e2e/projects/project-list.spec.ts` — Projects: list, create, delete project
* `e2e/projects/project-details.spec.ts` — Projects: detail view, task list, description edit
* `e2e/projects/task-details.spec.ts` — Projects: task detail, tags, relations, progress
* `e2e/pocket/pocket-items.spec.ts` — Pocket: items within pocket flow

#### Integration (real backend via TestContainers — add all new tests here)
* `e2e/integration/pocket/pocket.spec.ts` — Pocket: full CRUD (create pocket, add item, edit, delete)
* `e2e/integration/interview/interview.spec.ts` — Interview: questions CRUD, coding tasks CRUD, question configs CRUD (including % validation), interview plan save/reload, session list view, full session flow (create via API → open page → score question → complete)
* `e2e/integration/projects/project-list.spec.ts` — Projects: list, create, edit, delete project, search/filter, navigation to details and all-tasks, validation
* `e2e/integration/projects/project-details.spec.ts` — Projects: project header/stats, inline edit (status, priority, description), task CRUD, search, overdue stat, form validation
* `e2e/integration/projects/all-tasks.spec.ts` — Projects: all-tasks view, display, navigation to task details, edit/delete task, search/filter, task type icon
* `e2e/integration/projects/task-details.spec.ts` — Projects: task detail (header, progress, tags, relations), inline edit (status, priority, type, assignee, due date, estimated hours, completion %), add/remove tags, add/remove/search relations, relation group collapse, breadcrumb navigation
* `e2e/integration/invest-track/wallet.spec.ts` — Invest Track: wallet CRUD (create, edit/rename, delete), navigate to wallet detail and back, validation (missing name), snapshot CRUD (add snapshot, edit, delete)
* `e2e/integration/invest-track/stock-alerts.spec.ts` — Invest Track: stock alert CRUD (create, edit/rename, delete)
* `e2e/integration/invest-track/budget-entries.spec.ts` — Invest Track: budget entry create, verify appears, delete