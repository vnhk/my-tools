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

`BaseOwnedController` handles all mapping automatically via `BervanDTOMapper`:
- **DTO → Model**: `mapper.map(dto)` — used internally in `create()` and `update()`
- **Model → DTO**: `mapper.map(model, DtoClass.class)` — used internally in `getById()`, `load()`, `create()`, `update()`

For **simple fields** (same name + compatible type): no extra code needed — mapped automatically.

For **complex fields** (type conversion, related entity lookup, custom logic):
- Annotate the DTO field with `@FieldCustomMapper`
- Implement `DefaultCustomMapper<FROM, TO>` as a Spring `@Service`

`@FieldCustomMapper` applies **only to the DTO → Model direction** (iterates DTO fields during `mapper.map(dto)`).
For **Model → DTO with renamed fields** (e.g. `task.project: Project` → `taskDto.projectId: UUID`):
- The mapper does NOT pick up `@FieldCustomMapper` (it iterates Model fields, not DTO fields)
- **Prefer `mapper.map(model, DtoClass)` and accept null for renamed fields** if the list/create/update responses don't need those fields (e.g. `projectId` in task list — the list UI doesn't display it)
- **Use a manual `toXxxDto()` helper** only for detail endpoints that require extra computed data (e.g. `toTaskDetailDto()` builds relation lists — this cannot be done by the mapper)
- `@FieldCustomMapper` on DTO fields IS used when the DTO is the `from` object (create/update direction)

Reference example (MANDATORY):
- `pocket-app/src/main/java/com/bervan/pocketapp/pocketitem/api/PocketItemCreateRequest.java`
- `pocket-app/src/main/java/com/bervan/pocketapp/pocketitem/api/ToPocketMapper.java`

```java
// On DTO field:
@FieldCustomMapper(mapper = ToPocketMapper.class, targetFieldName = "pocket")
private String pocketName;

// Mapper implementation:
@Service
public class ToPocketMapper implements DefaultCustomMapper<String, Pocket> {
    @Override public Pocket map(String pocketName) { ... }
    @Override public Class<String> getFrom() { return String.class; }
    @Override public Class<Pocket> getTo() { return Pocket.class; }
}
```

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

### E2E Tests (React)

* After migrating a module:
    * Create E2E tests for the React implementation.
    * Tests must cover main user flows.
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
* `interview-app/.../interviewapp/view/InterviewQuestionsRestController.java`

**pocket-app**:
* `pocket-app/.../pocketapp/api/PocketRestController.java`
* `pocket-app/.../pocketapp/pocketitem/api/PocketItemRestController.java`

**my-tools-vaadin-app — cook-book**:
* `my-tools-vaadin-app/.../views/cookbook/CookBookRestController.java`
* `my-tools-vaadin-app/.../views/cookbook/DietRestController.java`

**my-tools-vaadin-app — invest-track**:
* `my-tools-vaadin-app/.../views/investtrackapp/BudgetEntryRestController.java`
* `my-tools-vaadin-app/.../views/investtrackapp/DataIERestController.java`
* `my-tools-vaadin-app/.../views/investtrackapp/InvestDashboardRestController.java`
* `my-tools-vaadin-app/.../views/investtrackapp/InvestmentRecommendationRestController.java`
* `my-tools-vaadin-app/.../views/investtrackapp/StockAlertRestController.java`
* `my-tools-vaadin-app/.../views/investtrackapp/StockReportRestController.java`
* `my-tools-vaadin-app/.../views/investtrackapp/WalletRestController.java`

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

* `e2e/app.spec.ts` — general app smoke test
* `e2e/pocket/pocket-list.spec.ts` — Pocket: list pockets flow
* `e2e/projects/project-list.spec.ts` — Projects: list, create, delete project
* `e2e/projects/project-details.spec.ts` — Projects: detail view, task list, description edit
* `e2e/projects/task-details.spec.ts` — Projects: task detail, tags, relations, progress
* `e2e/pocket/pocket-items.spec.ts` — Pocket: items within pocket flow