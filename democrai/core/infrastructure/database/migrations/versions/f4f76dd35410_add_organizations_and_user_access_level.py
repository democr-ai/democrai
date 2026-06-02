"""add organizations and user access level

Revision ID: f4f76dd35410
Revises: 51cad5333f91
Create Date: 2026-02-28 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4f76dd35410"
down_revision: Union[str, Sequence[str], None] = "51cad5333f91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "organizations" not in inspector.get_table_names():
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    user_indexes = {idx["name"] for idx in inspector.get_indexes("users")}
    user_foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("users")}

    needs_batch = any(
        [
            "access_level" not in user_columns,
            "organization_id" not in user_columns,
            op.f("ix_users_access_level") not in user_indexes,
            "fk_users_organization_id_organizations" not in user_foreign_keys,
        ]
    )

    if needs_batch:
        with op.batch_alter_table("users") as batch_op:
            if "access_level" not in user_columns:
                batch_op.add_column(
                    sa.Column(
                        "access_level",
                        sa.Integer(),
                        nullable=False,
                        server_default="3",
                    )
                )
            if "organization_id" not in user_columns:
                batch_op.add_column(
                    sa.Column("organization_id", sa.Integer(), nullable=True)
                )
            if op.f("ix_users_access_level") not in user_indexes:
                batch_op.create_index(
                    batch_op.f("ix_users_access_level"),
                    ["access_level"],
                    unique=False,
                )
            if "fk_users_organization_id_organizations" not in user_foreign_keys:
                batch_op.create_foreign_key(
                    "fk_users_organization_id_organizations",
                    "organizations",
                    ["organization_id"],
                    ["id"],
                )

    op.execute("UPDATE roles SET name = 'super' WHERE lower(name) = 'admin'")

    if "access_level" in {col["name"] for col in sa.inspect(bind).get_columns("users")}:
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column("access_level", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint(
            "fk_users_organization_id_organizations", type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_users_access_level"))
        batch_op.drop_column("organization_id")
        batch_op.drop_column("access_level")
    op.drop_table("organizations")
