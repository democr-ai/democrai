# Manifest

Every module has a `manifest.json` at its root.

```json
{
  "name": "chat",
  "label": "Chat",
  "version": "0.1.0",
  "icon": "ric.message-3-line",
  "description": "Conversation workspace.",
  "priority": 30,
  "enabled": true,
  "allowed_imports": [],
  "access": []
}
```

The `name` is the module id used by routing, action qualification, table
prefixes, translation loading, and RBAC. Keep it stable.

RBAC lives in `rbac.json`. Declare permissions explicitly and assign them to
roles:

```json
{
  "permissions": ["chat.view", "chat.write"],
  "assignments": {
    "super": ["chat.view", "chat.write"],
    "organization": ["chat.view", "chat.write"],
    "user": ["chat.view", "chat.write"],
    "guest": []
  }
}
```

Module code should use `@permission_required([...])` on views and actions that
need those permissions.
