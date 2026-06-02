# Database: CRUD Operations

## `add(obj)`

Use this method to insert one module-owned ORM object.

Use `add(...)` because it gives you all of the expected module safeguards in one place:

- validates that the model belongs to the current module
- applies automatic `user_id` and `organization_id` assignment when those fields exist
- persists the object
- commits the transaction
- refreshes the object before returning it

### Example

```python
row = module_sdk.database.add(
    Ticket(
        id=ticket_id,
        title=title,
        preview="",
    )
)
```

## `get(model, id)`

Use this method to load one row by primary identifier inside the current module and current access scope.

The method:

1. validates that the model belongs to the current module
2. builds the scoped query
3. filters by `model.id == id`
4. returns the first matching row or `None`

## `list(model, **filters)`

Use this method to load multiple rows for one module-owned model inside the current access scope.

The method:

1. validates that the model belongs to the current module
2. builds the scoped query
3. applies each provided filter only if the model has that attribute
4. returns `query.all()`

### Example

```python
rows = module_sdk.database.list(TicketMessage, ticket_id=ticket_id)
```

## `all(model, **filters)`

`all(...)` is functionally the same shape as `list(...)` in the current implementation.

Both methods:

- validate the model
- apply scope
- apply the provided equality filters
- return `query.all()`

## `update(model, id, **updates)`

Use this method to update one row by id inside the current module and current access scope.

The method:

1. validates that the model belongs to the current module
2. builds the scoped query
3. loads the row by id inside that scope
4. ignores ownership fields such as `user_id` and `organization_id`
5. applies each remaining update with `setattr`
6. commits
7. refreshes the row
8. returns the updated row

If the row is not visible in the current scope, the method returns `None`.

`update(...)` is not an ownership-transfer API. Passing `user_id` or
`organization_id` does not move a row to another owner; those fields are ignored
and the runtime logs a warning.

## `delete(model, id) -> bool`

Use this method to delete one row by id inside the current module and current access scope.

The method:

1. validates that the model belongs to the current module
2. builds the scoped query
3. looks up the row by id inside that scope
4. deletes it if found
5. commits
6. returns `True` if a row was deleted, otherwise `False`

## Example CRUD Flow

```python
row = module_sdk.database.add(
    Ticket(
        id="ticket_42",
        title="Broken login",
        status="open",
    )
)

open_rows = module_sdk.database.list(Ticket, status="open")
loaded = module_sdk.database.get(Ticket, row.id)
updated = module_sdk.database.update(Ticket, row.id, status="closed")
deleted = module_sdk.database.delete(Ticket, row.id)
```
