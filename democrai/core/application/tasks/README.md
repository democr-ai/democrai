# Tasks

This package owns runtime tasks, persistent task state, notifications and event
bridges. It keeps persistent task state separate from transient progress
streams.

## Key Files

- `task_manager.py`: task execution, progress, confirmation, persistence and
  recovery.
- `models.py`: task and notification tables.
- `notification_queue.py`: pending notification queue.
- `redis_task_bridge.py`: distributed bridge when Redis is configured.

## State vs Stream

Persistent state is for meaningful checkpoints:

- created/running/completed/failed/cancelled.
- current significant phase.
- consolidated progress when useful.
- final error.
- final result or result reference.

Transient streams are for noisy output:

- engine installation logs.
- frequent download progress.
- incremental log lines.
- high-frequency UI events.

Do not use the database as a transport for noisy output. Persist only state that
is needed for recovery, audit or UI resume.

## Notifications

Pending notifications should be incrementally updateable by clients. A
notification decision should not force a full rerender when a collection update,
counter update or toast is enough.

## Rules

- Frequent progress goes to streams.
- Meaningful state goes to the database.
- UI actions must not block while waiting for long tasks.
- Recovery must be possible from persisted state without relying on old streams.
