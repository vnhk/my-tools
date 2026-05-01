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
- ALWAYS follow the provided example.
- DO NOT invent your own patterns.
- If the example does NOT cover required functionality:
    - STOP
    - Inform the user BEFORE making changes.

#### DTO Mapping

`BaseOwnedController` handles all mapping automatically via `BervanDTOMapper`:
- **DTO → Model**: `mapper.map(dto)` — used internally in `create()` and `update()`
- **Model → DTO**: `mapper.map(model, DtoClass.class)` — used internally in `getById()`, `load()`, `create()`, `update()`

For **simple fields** (same name + compatible type): no extra code needed — mapped automatically.

For **complex fields** (type conversion, related entity lookup, custom logic):
- Annotate the DTO field with `@FieldCustomMapper`
- Implement `DefaultCustomMapper<FROM, TO>` as a Spring `@Service`

`@FieldCustomMapper` applies to **both** directions (DTO → Model and Model → DTO).

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

#### Rules:
- Every Vaadin View must have a corresponding React implementation.
- Do NOT partially migrate components — full migration required.

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

---

### E2E Tests Created

* `e2e/app.spec.ts` — general app smoke test
* `e2e/pocket/pocket-list.spec.ts` — Pocket: list pockets flow
* `e2e/pocket/pocket-items.spec.ts` — Pocket: items within pocket flow