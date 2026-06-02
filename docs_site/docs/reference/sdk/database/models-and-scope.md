# Database: Models and Scope

## When To Use `sdk.database` vs `sdk.models`

Use `sdk.database` when:

- the table belongs to your module
- the schema is defined by your module
- the record lifecycle is defined by your module
- you need normal module-local persistence for notes, settings, conversations, cached metadata, local domain records, or similar module-owned entities

Use `sdk.models` when:

- the entity belongs to the platform rather than your module
- the platform already exposes a model-driven CRUD API for it
- the table is part of the core application contract

This is not a stylistic choice. It is an architectural boundary.

## `Base`

`Base` is part of the public domain:

```python
from democrai.sdk.database import Base
```

Use this declarative base for module-owned SQLAlchemy models.

### What it actually does

At runtime, the SDK generates a declarative base whose table naming convention is:

```text
p_<module_name>_<model_name_lowercase>
```

The resulting base also includes the user/organization mixin fields used by the scoped datastore.

### Example model

```python
from democrai.sdk.database import Base
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column


class Ticket(Base):
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    description: Mapped[str] = mapped_column(Text, default="")
```

## Scope Behavior

The datastore applies scope automatically according to the current access level:

- super access: no scope filter is applied
- organization access: filter by `organization_id` when the model exposes it
- user access: filter by `user_id` when the model exposes it

That means ordinary module code usually should **not** manually repeat these filters for basic ownership isolation.

### What happens on write

When you call `add(obj)`, the datastore automatically assigns:

- `obj.user_id = current_user_id` if the model exposes `user_id`
- `obj.organization_id = current_organization_id` if the model exposes `organization_id`

### What happens on read

When you call `get(...)`, `list(...)`, `all(...)`, `update(...)`, or `delete(...)`, the datastore first builds a scoped query and only then applies your explicit filters or row lookup.

That matters because a row outside the current scope behaves as "not found" for update/delete/get purposes.

`update(...)` preserves row ownership. If an update payload includes `user_id`
or `organization_id`, the datastore ignores those fields and logs a warning.
