"""add media uploads table

Revision ID: ab12cd34ef56
Revises: 9d4a7e1b2c55
Create Date: 2026-03-05 17:20:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ab12cd34ef56"
down_revision: Union[str, Sequence[str], None] = "9d4a7e1b2c55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_uploads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("file_id", sa.String(length=64), nullable=False),
        sa.Column("module_name", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("stored_filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=128), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("uploader_access_level", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id"),
        sa.UniqueConstraint("storage_path"),
    )
    op.create_index(op.f("ix_media_uploads_file_id"), "media_uploads", ["file_id"], unique=False)
    op.create_index(op.f("ix_media_uploads_module_name"), "media_uploads", ["module_name"], unique=False)
    op.create_index(op.f("ix_media_uploads_sha256"), "media_uploads", ["sha256"], unique=False)
    op.create_index(op.f("ix_media_uploads_scope_type"), "media_uploads", ["scope_type"], unique=False)
    op.create_index(op.f("ix_media_uploads_owner_user_id"), "media_uploads", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_media_uploads_organization_id"), "media_uploads", ["organization_id"], unique=False)
    op.create_index(op.f("ix_media_uploads_uploaded_by"), "media_uploads", ["uploaded_by"], unique=False)
    op.create_index(
        op.f("ix_media_uploads_uploader_access_level"),
        "media_uploads",
        ["uploader_access_level"],
        unique=False,
    )
    op.create_index(op.f("ix_media_uploads_created_at"), "media_uploads", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_media_uploads_created_at"), table_name="media_uploads")
    op.drop_index(op.f("ix_media_uploads_uploader_access_level"), table_name="media_uploads")
    op.drop_index(op.f("ix_media_uploads_uploaded_by"), table_name="media_uploads")
    op.drop_index(op.f("ix_media_uploads_organization_id"), table_name="media_uploads")
    op.drop_index(op.f("ix_media_uploads_owner_user_id"), table_name="media_uploads")
    op.drop_index(op.f("ix_media_uploads_scope_type"), table_name="media_uploads")
    op.drop_index(op.f("ix_media_uploads_sha256"), table_name="media_uploads")
    op.drop_index(op.f("ix_media_uploads_module_name"), table_name="media_uploads")
    op.drop_index(op.f("ix_media_uploads_file_id"), table_name="media_uploads")
    op.drop_table("media_uploads")
