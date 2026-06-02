# SDK Domain Refactor Map

Data: 2026-04-11
Scope: `core/platform/sdk`
Modalita': pulizia hard, **senza retrocompatibilita'**.

## Obiettivo del pass

Ridurre API duplicate, alias inutili e classi replicate nel dominio SDK,
lasciando una superficie piu' piccola e coerente.

## Modifiche applicate

### 1) Access API

File: `core/platform/sdk/access.py`

Rimosso metodo duplicato:
- `check_external_request` (era identico a `check_external_access`).

API canonicale rimasta:
- `check_external_access`

### 2) Effects API

File: `core/platform/sdk/effects.py`

Rimossi alias/wrapper ridondanti:
- `property_update`
- `collection_append`
- `collection_remove`
- `collection_replace`
- `agent_ui_commands`

API canonicale rimasta per aggiornamenti UI:
- `ui_property_update`
- `ui_collection_append`
- `ui_collection_remove`
- `ui_collection_replace`
- `ui_agent_commands`

### 3) Decorators API

Files:
- `core/platform/sdk/decorators.py`
- `core/platform/sdk/decorator_binding.py`

Rimosso alias:
- `command` (ora esiste solo `callable_command`).

Rimossa anche la bind scoped corrispondente:
- `sdk.command`

Surface canonicale:
- `@callable_command(...)`

### 4) A2UI Builder

File: `core/platform/sdk/a2ui.py`

Rimosso alias:
- `add_component` (resta solo `add`).

### 5) AI SDK runtime path

File: `core/platform/sdk/ai.py`

Pulizia strutturale:
- Rimossi wrapper pass-through/no-op:
  - `_build_enriched_context`
  - `_build_enriched_generator`
  - `_grant_provider_network_access`
  - `_grant_catalog_network_access`
- Rimossa logica pattern-only non usata:
  - `_provider_allowed_url_patterns`
  - `_catalog_allowed_url_patterns`
- Rimossi i proxy provider SDK: la risoluzione AI restituisce il provider core risolto.
- `run_tool`, `run_agent`, `run_pipeline` ora eseguono il path diretto senza wrapper finti.

### 6) Layout components dedupe

Files toccati (layout domain):
- `card.py`
- `column.py`
- `content_area.py`
- `dashboard_widget.py`
- `dialog.py`
- `flow.py`
- `grid.py`
- `grid_drop_zone.py`
- `header.py`
- `row.py`
- `scroll_area.py`
- `sidebar.py`
- `splitter.py`
- `surface_host.py`
- `tabs.py`

Pulizia:
- Rimossa la copia locale di `Container` in ciascun file.
- Tutti questi componenti ora importano il solo `Container` condiviso da:
  - `core/platform/sdk/components/domains/layout/container.py`

### 7) Forms / conversation components dedupe

Files toccati:
- `core/platform/sdk/components/base.py`
- `core/platform/sdk/components/domains/actions/button.py`
- `core/platform/sdk/components/domains/actions/vertical_button.py`
- `core/platform/sdk/components/domains/forms/form.py`
- `core/platform/sdk/components/domains/forms/checkbox.py`
- `core/platform/sdk/components/domains/forms/toggle.py`
- `core/platform/sdk/components/domains/forms/date_picker.py`
- `core/platform/sdk/components/domains/forms/attachment.py`
- `core/platform/sdk/components/domains/forms/calendar.py`
- `core/platform/sdk/components/domains/forms/select.py`
- `core/platform/sdk/components/domains/forms/text_field.py`
- `core/platform/sdk/components/domains/forms/textarea.py`
- `core/platform/sdk/components/domains/conversation/scroll_to_bottom_button.py`
- `core/platform/sdk/components/domains/conversation/suggestions.py`
- `core/platform/sdk/components/domains/conversation/thread_list.py`

Pulizia:
- Centralizzati in `Component` i metodi comuni:
  - `set_action`
  - `set_on_change_action`
  - `collect_input_ids`
  - `track_loading`
- Rimosse implementazioni duplicate dai componenti che facevano la stessa identica cosa.
- `Button.set_action` resta custom (per logica auto-collect), ma riusa `super().set_action(...)`.
- `TextField` non espone piu' `set_submit_action` separato: si usa `set_action` del base component.
- `Toggle` ora estende `Checkbox` (niente doppia implementazione dello stesso comportamento).

### 9) Media components dedupe

File:
- `core/platform/sdk/components/domains/media/video.py`

Pulizia:
- `Video` ora estende `Audio` e riusa il costruttore comune.

### 8) Doppia definizione componente Forms

Files:
- `core/platform/sdk/components/domains/forms/switch.py`
- `core/platform/sdk/components/domains/forms/combobox.py`
- `core/platform/sdk/components/domains/data/chart_provider.py` (rimosso)

Pulizia collisioni discovery:
- `switch.py` non ridefinisce piu' `Checkbox`; ora importa `Checkbox` da `checkbox.py`.
- `combobox.py` non ridefinisce piu' `Select`; ora importa `Select` da `select.py` e definisce solo `Combobox`.
- Rimossa seconda implementazione `Chart` in `chart_provider.py` per evitare override non deterministico del componente `Chart` durante discovery dinamica.

### 10) Import cleanup legacy `sdk.*`

File:
- `tests/platform/test_sdk_components_and_http_unit.py`

Pulizia:
- Rimosso import legacy verso modulo eliminato:
  - `sdk.components.domains.data.chart_provider.Chart`
- Allineato al modulo canonico:
  - `sdk.components.domains.data.chart.Chart`

## Note operative

- Questo pass **non mantiene retrocompatibilita' API** su metodi/alias rimossi.
- L'adeguamento dei chiamanti esterni (`modules/*`, package SDK esterno, docs) e' demandato al pass successivo.

### 11) Root SDK surface cleanup

Files:
- `core/platform/sdk/client.py`
- `sdk_doc/sdk.md`

Pulizia:
- Rimossi dal root SDK gli shortcut legacy:
  - `db`
  - `Base`
  - `A2UIBuilder`
  - `EXTERNAL_RESOURCE_NETWORK`
  - `EXTERNAL_RESOURCE_FILESYSTEM`
  - `EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY`
- Rimossi dal root anche gli helper infrastrutturali non-dominio:
  - `resolve_module_resource`
  - `get_translation_service`
  - `observability_service`
  - `ingest_chat_completion`
- Surface canonico aggiornato:
  - `sdk.database`
  - `sdk.ui.Builder`
  - `sdk.access.EXTERNAL_RESOURCE_*`

### 12) Database domain formalization

Files:
- `core/platform/sdk/database.py`
- `sdk_doc/database.md`

Pulizia:
- Introdotto dominio pubblico `Database`.
- `sdk.database` e' ora il solo entrypoint pubblico per persistenza modulo.
- `Base` e' stato spostato sotto:
  - `sdk.database.Base`
- CRUD canonico:
  - `sdk.database.add`
  - `sdk.database.get`
  - `sdk.database.list`
  - `sdk.database.update`
  - `sdk.database.delete`

### 13) UI builder migration and `a2ui.py` removal

Files:
- `core/platform/sdk/ui.py`
- `core/platform/sdk/a2ui.py` (rimosso)
- `sdk_doc/a2ui.md`
- `sdk_doc/sdk.md`

Pulizia:
- Spostato il builder UI nel dominio `ui`.
- `sdk.ui` ora contiene:
  - `Builder`
  - namespace `ui`
  - helper bound pubblici
  - facade `UI`
- Eliminato file legacy:
  - `core/platform/sdk/a2ui.py`
- Surface canonico:
  - `sdk.ui.Builder()`

### 14) Chiamanti migrati al nuovo contract pubblico

Scope:
- `modules/*`
- `core/*`
- `desktop/*`
- `sdk_doc/*`

Migrazione applicata:
- `sdk.db` -> `sdk.database`
- `module_sdk.db` -> `module_sdk.database`
- `sdk.Base` -> `sdk.database.Base`
- `sdk.A2UIBuilder` -> `sdk.ui.Builder`
- `module_sdk.A2UIBuilder` -> `module_sdk.ui.Builder`
- `sdk.EXTERNAL_RESOURCE_*` -> `sdk.access.EXTERNAL_RESOURCE_*`
- `module_sdk.EXTERNAL_RESOURCE_*` -> `module_sdk.access.EXTERNAL_RESOURCE_*`
- `from sdk.a2ui import ...` -> `from sdk.ui import ...`

### 15) UI helper migration for resource/media resolution

Files:
- `core/platform/sdk/ui.py`
- `modules/system/ui_helpers/capabilities/list.py`
- `modules/components/actions/audio.py`
- `modules/components/actions/video.py`
- `modules/components/actions/image.py`
- `modules/components/actions/ai_chat.py`

Pulizia:
- Rimossi i chiamanti modulo che dipendevano dagli helper root:
  - `resolve_module_resource`
  - `_maybe_proxy_external_media_source`
- Sostituiti con API di dominio UI:
  - `sdk.ui.resolve_resource(...)`
  - `sdk.ui.resolve_media_source(...)`
