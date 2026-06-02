from fastapi import APIRouter, File, Form, Request, UploadFile

from democrai.core.application.handler.services.runtime import (
    media_proxy,
    media_serving,
    uploads,
)

media_desktop_router = APIRouter()
media_router = APIRouter()


@media_desktop_router.get("/proxy")
async def route_proxy_external_media(
    module_name: str,
    url: str,
    request: Request,
    width: int | None = None,
    height: int | None = None,
):
    return await media_proxy.proxy_external_media(
        module_name,
        url,
        request,
        width=width,
        height=height,
    )


@media_desktop_router.post("/uploads/raw")
async def route_upload_media_asset(
    module_name: str = Form(...),
    ingest: bool = Form(True),
    file: UploadFile = File(...),
):
    return await uploads.upload_media_asset(
        module_name=module_name,
        ingest=ingest,
        file=file,
    )


@media_desktop_router.get("/uploads/by-storage-path")
async def route_serve_uploaded_media_by_storage_path(
    storage_path: str,
    download: bool = False,
):
    return await media_serving.serve_uploaded_media_by_storage_path(
        storage_path=storage_path,
        download=download,
    )


@media_desktop_router.get("/uploads/{file_id}")
async def route_serve_uploaded_media(
    file_id: str,
    download: bool = False,
):
    return await media_serving.serve_uploaded_media(file_id, download=download)


@media_desktop_router.get("/engine/{engine_id}/{file_path:path}")
async def route_serve_engine_media(engine_id: str, file_path: str):
    return await media_serving.serve_engine_media(engine_id, file_path)


@media_desktop_router.get("/extractors/{extractor_id}/{file_path:path}")
async def route_serve_extractor_media(extractor_id: str, file_path: str):
    return await media_serving.serve_extractor_media(extractor_id, file_path)


@media_desktop_router.get("/modules/{module_name}/{file_path:path}")
async def route_serve_module_media(module_name: str, file_path: str):
    return await media_serving.serve_module_media(module_name, file_path)


media_router.include_router(media_desktop_router)
