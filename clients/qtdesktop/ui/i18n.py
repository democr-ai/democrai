from __future__ import annotations

from typing import Any


_SUPPORTED_LANGUAGES = {"en", "it", "es", "fr", "de", "zh"}

_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "blocked_url": "URL blocked",
        "reload": "Reload",
        "reload_url": "Reload URL",
        "loading": "Loading...",
        "pdf_not_available": "PDF not available.",
        "pdf_preview_unavailable": "PDF preview unavailable in this runtime.",
        "pdf_show_thumbnails": "Show thumbnails",
        "pdf_previous_page": "Previous page",
        "pdf_next_page": "Next page",
        "pdf_zoom_out": "Zoom out",
        "pdf_zoom_in": "Zoom in",
        "pdf_fit_width": "Fit width",
        "pdf_download": "Download",
        "pdf_save_title": "Save PDF",
        "pdf_page": "Page",
    },
    "it": {
        "blocked_url": "URL bloccato",
        "reload": "Ricarica",
        "reload_url": "Ricarica URL",
        "loading": "Caricamento...",
        "pdf_not_available": "PDF non disponibile.",
        "pdf_preview_unavailable": "Anteprima PDF non disponibile in questo runtime.",
        "pdf_show_thumbnails": "Mostra miniature",
        "pdf_previous_page": "Pagina precedente",
        "pdf_next_page": "Pagina successiva",
        "pdf_zoom_out": "Riduci zoom",
        "pdf_zoom_in": "Aumenta zoom",
        "pdf_fit_width": "Fit larghezza",
        "pdf_download": "Scarica",
        "pdf_save_title": "Salva PDF",
        "pdf_page": "Pagina",
    },
    "es": {
        "blocked_url": "URL bloqueada",
        "reload": "Recargar",
        "reload_url": "Recargar URL",
        "loading": "Cargando...",
        "pdf_not_available": "PDF no disponible.",
        "pdf_preview_unavailable": "La vista previa PDF no está disponible en este entorno.",
        "pdf_show_thumbnails": "Mostrar miniaturas",
        "pdf_previous_page": "Pagina anterior",
        "pdf_next_page": "Pagina siguiente",
        "pdf_zoom_out": "Alejar",
        "pdf_zoom_in": "Acercar",
        "pdf_fit_width": "Ajustar al ancho",
        "pdf_download": "Descargar",
        "pdf_save_title": "Guardar PDF",
        "pdf_page": "Pagina",
    },
    "fr": {
        "blocked_url": "URL bloquee",
        "reload": "Recharger",
        "reload_url": "Recharger l'URL",
        "loading": "Chargement...",
        "pdf_not_available": "PDF non disponible.",
        "pdf_preview_unavailable": "L'aperçu PDF n'est pas disponible dans cet environnement.",
        "pdf_show_thumbnails": "Afficher les miniatures",
        "pdf_previous_page": "Page precedente",
        "pdf_next_page": "Page suivante",
        "pdf_zoom_out": "Zoom arriere",
        "pdf_zoom_in": "Zoom avant",
        "pdf_fit_width": "Ajuster a la largeur",
        "pdf_download": "Telecharger",
        "pdf_save_title": "Enregistrer le PDF",
        "pdf_page": "Page",
    },
    "de": {
        "blocked_url": "URL blockiert",
        "reload": "Neu laden",
        "reload_url": "URL neu laden",
        "loading": "Wird geladen...",
        "pdf_not_available": "PDF nicht verfugbar.",
        "pdf_preview_unavailable": "PDF-Vorschau ist in dieser Laufzeit nicht verfugbar.",
        "pdf_show_thumbnails": "Miniaturen anzeigen",
        "pdf_previous_page": "Vorherige Seite",
        "pdf_next_page": "Nachste Seite",
        "pdf_zoom_out": "Verkleinern",
        "pdf_zoom_in": "Vergrossern",
        "pdf_fit_width": "An Breite anpassen",
        "pdf_download": "Herunterladen",
        "pdf_save_title": "PDF speichern",
        "pdf_page": "Seite",
    },
    "zh": {
        "blocked_url": "URL 已阻止",
        "reload": "重新加载",
        "reload_url": "重新加载 URL",
        "loading": "加载中...",
        "pdf_not_available": "PDF 不可用。",
        "pdf_preview_unavailable": "此运行时中 PDF 预览不可用。",
        "pdf_show_thumbnails": "显示缩略图",
        "pdf_previous_page": "上一页",
        "pdf_next_page": "下一页",
        "pdf_zoom_out": "缩小",
        "pdf_zoom_in": "放大",
        "pdf_fit_width": "适应宽度",
        "pdf_download": "下载",
        "pdf_save_title": "保存 PDF",
        "pdf_page": "页",
    },
}


def get_ui_language(app_instance: Any) -> str:
    store = getattr(app_instance, "store", None)
    if store is None or not hasattr(store, "get"):
        return "en"
    try:
        raw = store.get("/core/user/language", "en", "global")
    except Exception:
        return "en"
    value = str(raw or "").strip().lower()
    if value in _SUPPORTED_LANGUAGES:
        return value
    return "en"


def get_i18n(app_instance: Any) -> dict[str, str]:
    return _MESSAGES[get_ui_language(app_instance)]
