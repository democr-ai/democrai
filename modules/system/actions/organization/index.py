from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator, model_validator

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action, validate

from modules.system.utils.actions.organization.module import module_rows_for_organization
from modules.system.utils.actions.organization.agents import organization_agent_rows
from modules.system.utils.actions.organization.mcp import organization_mcp_rows
from modules.system.utils.actions.organization.tools import organization_tool_rows
from modules.system.utils.actions.datatable import (
    datatable_payload,
    datatable_request,
    datatable_response,
)
from modules.system.utils.actions.user.index import (
    t,
)

TABLE_ID = "organization_list_table"


class OrganizationFormPayload(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("name is required")
        return name


class OrganizationCreatePayload(BaseModel):
    organization_create_form: OrganizationFormPayload


class OrganizationUpdatePayload(BaseModel):
    organization_id: int
    organization_update_form: OrganizationFormPayload


class OrganizationUserCreateFormPayload(BaseModel):
    username: str = Field(min_length=1)
    email: str = ""
    role: str = Field(min_length=1)
    access_level: int
    password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)

    @field_validator("username")
    @classmethod
    def _clean_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("username is required")
        return username

    @model_validator(mode="after")
    def _passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("password confirmation does not match")
        return self


class OrganizationUserCreatePayload(BaseModel):
    organization_id: int
    user_create_form: OrganizationUserCreateFormPayload


class RowItemPayload(BaseModel):
    id: int


class RowActionPayload(BaseModel):
    item: RowItemPayload


@action("list_organization")
@permission_required(["system.organization.list"])
async def list_organization(ctx: Dict[str, Any], session: dict, module_sdk):
    page, page_size, filters = datatable_request(ctx)
    listing = module_sdk.models.organizations.list(
        page=page,
        page_size=page_size,
        filters=filters,
    )
    payload = datatable_payload(
        listing,
        page=page,
        page_size=page_size,
        filters=filters,
    )
    return datatable_response(module_sdk, TABLE_ID, payload)


@action("view_organization")
@permission_required(["system.organization.view"])
async def view_organization(ctx: Dict[str, Any], session: dict, module_sdk):
    if ctx.get("op") == "open":
        item = ctx["item"]
        organization_id = item["id"]
        return module_sdk.effects.respond(
            module_sdk.effects.navigate(
                f"/system/organization/{organization_id}/view",
                render=True,
            )
        )

    if "organization_id" not in ctx:
        return module_sdk.effects.respond()

    organization_id = int(ctx["organization_id"])
    organization = module_sdk.models.organizations.view(organization_id)
    if organization is None:
        return {"ok": False, "error": "organization_not_found"}
    return {"ok": True, "organization": organization}


@action("create_organization")
@validate(OrganizationCreatePayload, strip_extra=True)
@permission_required(["system.organization.create"])
async def create_organization(ctx: Dict[str, Any], session: dict, module_sdk):
    payload = ctx["organization_create_form"]

    try:
        created = module_sdk.models.organizations.create(payload)
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.toast.created.title"),
                    "text": t(
                        module_sdk,
                        "system.organization.toast.created.text",
                        context={"name": created["name"]},
                    ),
                    "variant": "success",
                },
            ),
            module_sdk.effects.render(),
        )
    except ValueError as exc:
        message = str(exc).strip().lower()
        text = (
            t(module_sdk, "system.organization.toast.name_taken")
            if "already in use" in message
            else t(module_sdk, "system.organization.toast.create_error.text")
        )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.toast.create_error.title"),
                    "text": text,
                    "variant": "destructive",
                },
            )
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.organization] create_organization error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.toast.create_error.title"),
                    "text": t(module_sdk, "system.organization.toast.create_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("update_organization")
@validate(OrganizationUpdatePayload, strip_extra=True)
@permission_required(["system.organization.update"])
async def update_organization(ctx: Dict[str, Any], session: dict, module_sdk):
    organization_id = ctx["organization_id"]
    payload = ctx["organization_update_form"]

    try:
        updated = module_sdk.models.organizations.update(organization_id, payload)
        if updated is None:
            return module_sdk.effects.respond()
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.toast.updated.title"),
                    "text": t(
                        module_sdk,
                        "system.organization.toast.updated.text",
                        context={"name": updated["name"]},
                    ),
                    "variant": "success",
                },
            ),
            module_sdk.effects.render(),
        )
    except ValueError as exc:
        message = str(exc).strip().lower()
        text = (
            t(module_sdk, "system.organization.toast.name_taken")
            if "already in use" in message
            else t(module_sdk, "system.organization.toast.update_error.text")
        )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.toast.update_error.title"),
                    "text": text,
                    "variant": "destructive",
                },
            )
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.organization] update_organization error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.toast.update_error.title"),
                    "text": t(module_sdk, "system.organization.toast.update_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("delete_organization")
@validate(RowActionPayload, strip_extra=True)
@permission_required(["system.organization.delete"])
async def delete_organization(ctx: Dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    organization_id = item["id"]
    try:
        deleted = bool(module_sdk.models.organizations.delete(organization_id))
        if not deleted:
            return module_sdk.effects.respond()
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.toast.deleted.title"),
                    "text": t(module_sdk, "system.organization.toast.deleted.text"),
                    "variant": "success",
                },
            ),
            module_sdk.effects.render(),
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.organization] delete_organization error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.toast.delete_error.title"),
                    "text": t(module_sdk, "system.organization.toast.delete_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("create_organization_user")
@validate(OrganizationUserCreatePayload, strip_extra=True)
@permission_required(["system.user.create"])
async def create_organization_user(ctx: Dict[str, Any], session: dict, module_sdk):
    form_payload = ctx["user_create_form"]
    payload = {
        "username": form_payload["username"],
        "email": form_payload["email"],
        "role": form_payload["role"],
        "access_level": form_payload["access_level"],
        "password": form_payload["password"],
        "organization_id": ctx["organization_id"],
    }

    try:
        created = module_sdk.models.users.create(payload)
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.created.title"),
                    "text": t(
                        module_sdk,
                        "system.user.toast.created.text",
                        context={"username": created["username"]},
                    ),
                    "variant": "success",
                },
            ),
            module_sdk.effects.render(),
        )
    except ValueError as exc:
        message = str(exc).strip().lower()
        text = (
            t(module_sdk, "system.user.toast.username_taken")
            if "already in use" in message
            else t(module_sdk, "system.user.toast.create_error.text")
        )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.create_error.title"),
                    "text": text,
                    "variant": "destructive",
                },
            )
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.organization] create_organization_user error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.create_error.title"),
                    "text": t(module_sdk, "system.user.toast.create_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("disable_organization_module")
@permission_required(["system.organization.update"])
async def disable_organization_module(ctx: Dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    organization_id = int(item["organization_id"])
    module_name = str(item["module_name"]).strip()

    try:
        existing = module_sdk.models.module_locks.list(
            page=0,
            page_size=200,
            filters={"module_name": module_name, "organization_id": organization_id},
        )
        existing_rows = existing["rows"]
        already_locked = False
        for lock in existing_rows:
            if lock.get("user_id") is None and lock.get("role_id") is None:
                already_locked = True
                break
        if not already_locked:
            module_sdk.models.module_locks.create(
                {
                    "module_name": module_name,
                    "user_id": None,
                    "organization_id": organization_id,
                    "role_id": None,
                }
            )

        rows = module_rows_for_organization(organization_id, module_sdk)
        return module_sdk.effects.respond(
            module_sdk.effects.ui_property_update(
                "organization_modules_table", "rows", rows, action="set"
            ),
            module_sdk.effects.ui_property_update(
                "organization_modules_table", "total_rows", len(rows)
            ),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.modules.toast.disable.title"),
                    "text": t(
                        module_sdk,
                        "system.organization.modules.toast.disable.text",
                        context={"module_name": module_name},
                    ),
                    "variant": "success",
                },
            ),
        )
    except Exception as exc:
        module_sdk.system.log(
            f"[system.organization] disable_organization_module error: {exc}",
            "error",
        )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.modules.toast.disable_error.title"),
                    "text": t(module_sdk, "system.organization.modules.toast.disable_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("enable_organization_module")
@permission_required(["system.organization.update"])
async def enable_organization_module(ctx: Dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    organization_id = int(item["organization_id"])
    module_name = str(item["module_name"]).strip()

    try:
        existing = module_sdk.models.module_locks.list(
            page=0,
            page_size=50,
            filters={"module_name": module_name, "organization_id": organization_id},
        )
        existing_rows = existing["rows"]
        for lock in existing_rows:
            if lock.get("user_id") is not None or lock.get("role_id") is not None:
                continue
            lock_id = lock.get("id")
            if lock_id is None:
                continue
            module_sdk.models.module_locks.delete(int(lock_id))

        rows = module_rows_for_organization(organization_id, module_sdk)
        return module_sdk.effects.respond(
            module_sdk.effects.ui_property_update(
                "organization_modules_table", "rows", rows, action="set"
            ),
            module_sdk.effects.ui_property_update(
                "organization_modules_table", "total_rows", len(rows)
            ),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.modules.toast.enable.title"),
                    "text": t(
                        module_sdk,
                        "system.organization.modules.toast.enable.text",
                        context={"module_name": module_name},
                    ),
                    "variant": "success",
                },
            ),
        )
    except Exception as exc:
        module_sdk.system.log(
            f"[system.organization] enable_organization_module error: {exc}",
            "error",
        )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.organization.modules.toast.enable_error.title"),
                    "text": t(module_sdk, "system.organization.modules.toast.enable_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("enable_organization_agent")
@permission_required(["system.organization.update"])
async def enable_organization_agent(ctx: Dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    organization_id = int(item["organization_id"])
    agent_name = str(item["agent_name"]).strip()

    module_sdk.models.organization_agent.create(
        {"organization_id": organization_id, "agent_name": agent_name}
    )
    rows = organization_agent_rows(organization_id, module_sdk)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(
            "organization_agents_table", "rows", rows, action="set"
        ),
        module_sdk.effects.ui_property_update(
            "organization_agents_table", "total_rows", len(rows)
        ),
    )


@action("disable_organization_agent")
@permission_required(["system.organization.update"])
async def disable_organization_agent(ctx: Dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    organization_id = int(item["organization_id"])
    module_sdk.models.organization_agent.delete(int(item["link_id"]))

    rows = organization_agent_rows(organization_id, module_sdk)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(
            "organization_agents_table", "rows", rows, action="set"
        ),
        module_sdk.effects.ui_property_update(
            "organization_agents_table", "total_rows", len(rows)
        ),
    )


@action("enable_organization_mcp")
@permission_required(["system.organization.update"])
async def enable_organization_mcp(ctx: Dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    organization_id = int(item["organization_id"])
    mcp_server_id = int(item["mcp_server_id"])
    module_sdk.models.organization_mcp.create(
        {"organization_id": organization_id, "mcp_server_id": mcp_server_id}
    )
    rows = organization_mcp_rows(organization_id, module_sdk)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(
            "organization_mcp_table", "rows", rows, action="set"
        ),
        module_sdk.effects.ui_property_update(
            "organization_mcp_table", "total_rows", len(rows)
        ),
    )


@action("enable_organization_tool")
@permission_required(["system.organization.update"])
async def enable_organization_tool(ctx: Dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    organization_id = int(item["organization_id"])
    tool_name = str(item["tool_name"]).strip()

    module_sdk.models.organization_tool.create(
        {"organization_id": organization_id, "tool_name": tool_name}
    )
    rows = organization_tool_rows(organization_id, module_sdk)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(
            "organization_tools_table", "rows", rows, action="set"
        ),
        module_sdk.effects.ui_property_update(
            "organization_tools_table", "total_rows", len(rows)
        ),
    )


@action("disable_organization_tool")
@permission_required(["system.organization.update"])
async def disable_organization_tool(ctx: Dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    organization_id = int(item["organization_id"])
    module_sdk.models.organization_tool.delete(int(item["link_id"]))

    rows = organization_tool_rows(organization_id, module_sdk)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(
            "organization_tools_table", "rows", rows, action="set"
        ),
        module_sdk.effects.ui_property_update(
            "organization_tools_table", "total_rows", len(rows)
        ),
    )


@action("disable_organization_mcp")
@permission_required(["system.organization.update"])
async def disable_organization_mcp(ctx: Dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    organization_id = int(item["organization_id"])
    module_sdk.models.organization_mcp.delete(int(item["link_id"]))

    rows = organization_mcp_rows(organization_id, module_sdk)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(
            "organization_mcp_table", "rows", rows, action="set"
        ),
        module_sdk.effects.ui_property_update(
            "organization_mcp_table", "total_rows", len(rows)
        ),
    )
