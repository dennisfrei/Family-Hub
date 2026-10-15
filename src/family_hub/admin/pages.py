"""Admin area (`/admin`): delete people for good, API tokens, backups, system facts."""

import asyncio
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from nicegui import app, ui

from family_hub import db
from family_hub.admin import service
from family_hub.admin.schemas import ApiTokenRead
from family_hub.backup import service as backup_service
from family_hub.backup import storage
from family_hub.config import get_settings
from family_hub.core import service as core_service
from family_hub.core.schemas import PersonRead
from family_hub.module import registered_modules
from family_hub.ui import i18n
from family_hub.ui.components import Action, empty_state, page_title, section, stat_tile
from family_hub.ui.dialogs import confirm
from family_hub.ui.i18n import t
from family_hub.ui.layout import frame

logger = logging.getLogger(__name__)

RECENT_BACKUPS = 10
DEFAULT_TOKEN_DAYS = 365

i18n.register(
    {
        "admin.title": ("Verwaltung", "Admin"),
        "admin.subtitle": ("Personen, API-Zugänge, Backups und System", "People, API access, backups and system"),
        "admin.tab.people": ("Personen löschen", "Delete people"),
        "admin.tab.tokens": ("API-Tokens", "API tokens"),
        "admin.tab.backup": ("Backup", "Backup"),
        "admin.tab.system": ("System", "System"),
        "admin.people.hint": (
            "Deaktivieren (unter Personen) behält die Historie. Endgültiges Löschen entfernt die Person "
            "mit allen Daten aus allen Modulen; vorher wird automatisch ein Backup erstellt.",
            "Deactivating (under People) keeps the history. Deleting for good removes the person with all data "
            "in every module; a backup is created automatically first.",
        ),
        "admin.people.delete": ("Endgültig löschen", "Delete for good"),
        "admin.people.title": ("{name} endgültig löschen", "Delete {name} for good"),
        "admin.people.no_data": ("Keine weiteren Daten in den Modulen.", "No other data in the modules."),
        "admin.people.data": ("Diese Daten werden gelöscht oder angepasst:", "This data is deleted or adjusted:"),
        "admin.people.backup_first": (
            "Vor dem Löschen wird ein Backup erstellt ({target}).",
            "A backup is created before deleting ({target}).",
        ),
        "admin.people.confirm": ("Zum Bestätigen „{name}“ eingeben", "Type “{name}” to confirm"),
        "admin.people.deleted": ("{name} gelöscht. Backup: {backup}", "{name} deleted. Backup: {backup}"),
        "admin.people.backup_failed": (
            "Backup fehlgeschlagen, nichts gelöscht: {error}",
            "Backup failed, nothing deleted: {error}",
        ),
        "admin.tokens.hint": (
            "Tokens für Kurzbefehle und andere Clients der API. Ein Token wird nur einmal angezeigt.",
            "Tokens for shortcuts and other API clients. A token is shown only once.",
        ),
        "admin.tokens.new": ("Neues Token", "New token"),
        "admin.tokens.client": ("Client, z. B. iPhone-Kurzbefehl", "Client, e.g. iPhone shortcut"),
        "admin.tokens.days": ("Gültig (Tage)", "Valid (days)"),
        "admin.tokens.created_once": (
            "Jetzt kopieren, das Token wird nicht noch einmal angezeigt.",
            "Copy it now, the token will not be shown again.",
        ),
        "admin.tokens.copy": ("Kopieren", "Copy"),
        "admin.tokens.copied": ("Kopiert", "Copied"),
        "admin.tokens.done": ("Fertig", "Done"),
        "admin.tokens.empty": ("Noch keine Tokens.", "No tokens yet."),
        "admin.tokens.revoke": ("Widerrufen", "Revoke"),
        "admin.tokens.revoke_confirm": (
            "Token „{name}“ widerrufen? Clients damit erhalten sofort keinen Zugriff mehr.",
            "Revoke token “{name}”? Clients using it lose access immediately.",
        ),
        "admin.tokens.active": ("aktiv", "active"),
        "admin.tokens.expired": ("abgelaufen", "expired"),
        "admin.tokens.revoked": ("widerrufen", "revoked"),
        "admin.tokens.details": (
            "erstellt {created} · gültig bis {expires} · zuletzt genutzt {used}",
            "created {created} · valid until {expires} · last used {used}",
        ),
        "admin.tokens.never": ("nie", "never"),
        "admin.backup.target": ("Ziel", "Target"),
        "admin.backup.local_only": ("nur lokal ({dir})", "local only ({dir})"),
        "admin.backup.last": ("Letzter Upload", "Last upload"),
        "admin.backup.none": ("noch keiner", "none yet"),
        "admin.backup.now": ("Jetzt sichern", "Back up now"),
        "admin.backup.download": ("Aktuellen Stand herunterladen", "Download current data"),
        "admin.backup.done": ("Backup erstellt: {where}", "Backup created: {where}"),
        "admin.backup.unchanged": ("Keine Änderungen seit dem letzten Upload.", "No changes since the last upload."),
        "admin.backup.failed": ("Backup fehlgeschlagen: {error}", "Backup failed: {error}"),
        "admin.backup.recent": ("Backups im Speicher", "Stored backups"),
        "admin.backup.list_failed": ("Liste nicht verfügbar: {error}", "List not available: {error}"),
        "admin.backup.restore_hint": (
            "Wiederherstellen ersetzt alle Daten und läuft bewusst nur über die Kommandozeile: "
            "family-hub-restore --list, dann family-hub-restore --s3 --key <key>.",
            "Restoring replaces all data and on purpose only runs from the command line: "
            "family-hub-restore --list, then family-hub-restore --s3 --key <key>.",
        ),
        "admin.system.version": ("Version", "Version"),
        "admin.system.schema": ("Schema", "Schema"),
        "admin.system.database": ("Datenbank", "Database"),
        "admin.system.timezone": ("Zeitzone", "Time zone"),
        "admin.system.reference": ("Referenzdaten", "Reference data"),
        "admin.system.reference_files": ("{n} Dateien", "{n} files"),
        "admin.system.tables": ("Datensätze", "Records"),
    }
)


def register_pages() -> None:
    """Register the admin page."""

    @ui.page("/admin")
    async def admin_page() -> None:
        with frame("admin"):
            page_title(t("admin.title"), t("admin.subtitle"))
            with (
                ui.tabs()
                .props(
                    "dense no-caps inline-label active-color=primary indicator-color=primary align=left "
                    "mobile-arrows outside-arrows"
                )
                .classes("w-full") as tabs
            ):
                tab_people = ui.tab("people", t("admin.tab.people"))
                tab_tokens = ui.tab("tokens", t("admin.tab.tokens"))
                tab_backup = ui.tab("backup", t("admin.tab.backup"))
                tab_system = ui.tab("system", t("admin.tab.system"))
            with (
                ui.tab_panels(tabs, value=app.storage.user.get("admin_tab", "people"))
                .classes("w-full bg-transparent")
                .on_value_change(lambda e: app.storage.user.update(admin_tab=e.value))
            ):
                with ui.tab_panel(tab_people).classes("p-0 gap-4"):
                    people = ui.refreshable(_people_panel)
                    await people(people.refresh)
                with ui.tab_panel(tab_tokens).classes("p-0 gap-4"):
                    tokens = ui.refreshable(_tokens_panel)
                    await tokens(tokens.refresh)
                with ui.tab_panel(tab_backup).classes("p-0 gap-4"):
                    backup = ui.refreshable(_backup_panel)
                    await backup(backup.refresh)
                with ui.tab_panel(tab_system).classes("p-0 gap-4"):
                    await _system_panel()


def _local_time(value: datetime) -> str:
    local = value.astimezone(ZoneInfo(get_settings().timezone))
    return f"{i18n.day(local)} {local:%H:%M}"


def _backup_target() -> str:
    settings = get_settings()
    if settings.backup_bucket:
        return f"s3://{settings.backup_bucket}/{settings.backup_prefix}"
    return t("admin.backup.local_only", dir=settings.backup_dir)


async def _call(callback: Action) -> None:
    result = callback()
    if result is not None:
        await result


async def _people_panel(refresh: Action) -> None:
    async with db.session() as session:
        people = await core_service.list_people(session, include_inactive=True)
    with section():
        ui.label(t("admin.people.hint")).classes("text-sm hub-muted")
        if not people:
            empty_state(t("core.empty"))
        for person in people:
            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                ui.element("div").classes("rounded-full shrink-0").style(
                    f"background:{person.color}; width:12px; height:12px"
                )
                with ui.column().classes("gap-0 grow min-w-0"):
                    ui.label(person.name).classes("font-medium truncate")
                    details = [t(f"core.kind.{person.kind.value}")]
                    if not person.active:
                        details.append(t("core.inactive"))
                    ui.label(" · ".join(details)).classes("text-xs hub-muted")
                ui.button(t("admin.people.delete"), on_click=lambda p=person: _delete_dialog(p, refresh)).props(
                    "flat dense no-caps color=negative"
                ).mark(f"delete-person-{person.id}")


async def _delete_dialog(person: PersonRead, on_deleted: Action) -> None:
    modules = registered_modules()
    async with db.session() as session:
        usage = await service.person_usage(session, person.id, modules)
    with ui.dialog() as dialog, ui.card().classes("hub-card w-[28rem] max-w-full p-5 gap-3"):
        ui.label(t("admin.people.title", name=person.name)).classes("text-lg font-semibold")
        if usage:
            ui.label(t("admin.people.data")).classes("text-sm")
            with ui.column().classes("w-full gap-1"):
                for module in usage:
                    ui.label(t(module.label_key)).classes("text-sm font-semibold mt-1")
                    for key, count in module.items.items():
                        with ui.row().classes("w-full no-wrap gap-2 text-sm"):
                            ui.label(t(key)).classes("grow hub-muted")
                            ui.label(str(count)).classes("font-medium")
        else:
            ui.label(t("admin.people.no_data")).classes("text-sm hub-muted")
        ui.label(t("admin.people.backup_first", target=_backup_target())).classes("text-sm hub-muted")
        typed = ui.input(t("admin.people.confirm", name=person.name)).props("outlined").classes("w-full")

        async def delete() -> None:
            button.disable()
            try:
                result = await backup_service.create_backup(get_settings(), force=True)
            except Exception as exc:
                logger.error(f"Backup before deleting person {person.id} failed: {exc}")
                ui.notify(t("admin.people.backup_failed", error=exc), type="negative", multi_line=True)
                button.enable()
                return
            async with db.session() as session:
                await service.delete_person(session, person.id, modules)
            dialog.close()
            ui.notify(t("admin.people.deleted", name=person.name, backup=result.uri or result.path), type="positive")
            await _call(on_deleted)

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            button = (
                ui.button(t("admin.people.delete"), on_click=delete)
                .props("unelevated color=negative")
                .mark("confirm-delete")
            )
            button.bind_enabled_from(typed, "value", backward=lambda value: (value or "").strip() == person.name)
    dialog.open()


def _token_status(token: ApiTokenRead, now: datetime) -> tuple[str, str]:
    if token.revoked_at is not None:
        return t("admin.tokens.revoked"), "hub-muted"
    if token.expires_at <= now:
        return t("admin.tokens.expired"), "hub-muted"
    return t("admin.tokens.active"), "hub-accent"


async def _tokens_panel(refresh: Action) -> None:
    async with db.session() as session:
        tokens = await service.list_tokens(session)
    now = datetime.now(UTC)
    with section(toolbar=True) as header:
        with header:
            ui.label(t("admin.tokens.hint")).classes("text-sm hub-muted grow")
            ui.button(t("admin.tokens.new"), on_click=lambda: _new_token_dialog(refresh)).props(
                "unelevated rounded no-caps"
            )
        if not tokens:
            empty_state(t("admin.tokens.empty"))
        for token in tokens:
            status, status_class = _token_status(token, now)
            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                with ui.column().classes("gap-0 grow min-w-0"):
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        ui.label(token.name).classes("font-medium truncate")
                        ui.label(status).classes(f"text-xs {status_class}")
                    used = _local_time(token.last_used_at) if token.last_used_at else t("admin.tokens.never")
                    ui.label(
                        t(
                            "admin.tokens.details",
                            created=i18n.day(token.created_at),
                            expires=i18n.day(token.expires_at),
                            used=used,
                        )
                    ).classes("text-xs hub-muted")
                if token.is_active(now):
                    ui.button(t("admin.tokens.revoke"), on_click=lambda tk=token: _revoke(tk, refresh)).props(
                        "flat dense no-caps color=negative"
                    )


async def _revoke(token: ApiTokenRead, refresh: Action) -> None:
    if not await confirm(t("admin.tokens.revoke_confirm", name=token.name), ok_label=t("admin.tokens.revoke")):
        return
    async with db.session() as session:
        await service.revoke_token(session, token.id)
    await _call(refresh)


async def _new_token_dialog(refresh: Action) -> None:
    with ui.dialog() as dialog, ui.card().classes("hub-card w-[28rem] max-w-full p-5 gap-3"):
        ui.label(t("admin.tokens.new")).classes("text-lg font-semibold")
        form = ui.column().classes("w-full gap-3")
        with form:
            name = ui.input(t("admin.tokens.client")).props("outlined").classes("w-full")
            days = ui.number(t("admin.tokens.days"), value=DEFAULT_TOKEN_DAYS, min=1, precision=0).props("outlined")
        result = ui.column().classes("w-full gap-3")
        result.set_visibility(False)
        buttons = ui.row().classes("w-full justify-end gap-2")

        async def create() -> None:
            try:
                async with db.session() as session:
                    issued = await service.issue_token(session, get_settings(), name.value or "", int(days.value or 0))
            except ValueError as exc:
                ui.notify(i18n.error_text(exc), type="negative")
                return
            form.set_visibility(False)
            buttons.set_visibility(False)
            result.set_visibility(True)
            with result:
                ui.label(t("admin.tokens.created_once")).classes("text-sm")
                ui.textarea(value=issued.token).props("outlined readonly autogrow").classes("w-full font-mono text-xs")
                with ui.row().classes("w-full justify-end gap-2"):

                    async def copy() -> None:
                        ui.clipboard.write(issued.token)
                        ui.notify(t("admin.tokens.copied"))

                    ui.button(t("admin.tokens.copy"), on_click=copy).props("flat no-caps")
                    ui.button(t("admin.tokens.done"), on_click=dialog.close).props("unelevated no-caps")

        with buttons:
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            ui.button(t("common.create"), on_click=create).props("unelevated")
    dialog.open()
    await dialog
    await _call(refresh)


async def _backup_panel(refresh: Action) -> None:
    settings = get_settings()
    metadata = await asyncio.to_thread(storage.load_metadata, settings.backup_dir)
    with section():
        last = metadata.get("last_backup_timestamp")
        facts = (
            (t("admin.backup.target"), _backup_target()),
            (t("admin.backup.last"), _local_time(datetime.fromisoformat(last).astimezone()) if last else None),
        )
        with ui.element("div").classes("w-full grid gap-x-4 gap-y-1 text-sm").style("grid-template-columns: auto 1fr"):
            for label, value in facts:
                ui.label(label).classes("hub-muted")
                ui.label(value or t("admin.backup.none")).classes("font-medium break-all")
        with ui.row().classes("w-full gap-2"):
            ui.button(t("admin.backup.now"), on_click=lambda: _backup_now(refresh)).props("unelevated no-caps")
            ui.button(t("admin.backup.download"), on_click=_download).props("outline no-caps")
        ui.label(t("admin.backup.restore_hint")).classes("text-xs hub-muted")
    if settings.backup_bucket:
        with section(t("admin.backup.recent")):
            listing = ui.column().classes("w-full gap-1")
            with listing:
                ui.spinner()
            ui.timer(0.1, lambda: _list_backups(listing), once=True)


async def _list_backups(container: ui.column) -> None:
    settings = get_settings()
    bucket = settings.backup_bucket
    if bucket is None:
        return
    try:
        client = storage.s3_client(settings)
        backups = await asyncio.to_thread(storage.list_backups, client, bucket, settings.backup_prefix)
    except Exception as exc:
        container.clear()
        with container:
            ui.label(t("admin.backup.list_failed", error=exc)).classes("text-sm hub-muted")
        return
    container.clear()
    with container:
        if not backups:
            empty_state(t("admin.backup.none"))
        for backup in backups[:RECENT_BACKUPS]:
            with ui.row().classes("w-full no-wrap gap-3 text-sm"):
                ui.label(_local_time(backup["last_modified"])).classes("grow").tooltip(backup["key"])
                ui.label(f"{backup['size'] / 1024:.1f} KB").classes("hub-muted whitespace-nowrap")


async def _backup_now(refresh: Action) -> None:
    try:
        result = await backup_service.create_backup(get_settings())
    except Exception as exc:
        logger.error(f"Backup from the admin page failed: {exc}")
        ui.notify(t("admin.backup.failed", error=exc), type="negative", multi_line=True)
        return
    if result.unchanged:
        ui.notify(t("admin.backup.unchanged"))
    else:
        ui.notify(t("admin.backup.done", where=result.uri or result.path), type="positive")
    await _call(refresh)


async def _download() -> None:
    data = await backup_service.export_current()
    content = await asyncio.to_thread(backup_service.to_bytes, data)
    ui.download.content(content, f"{storage.BACKUP_FILE_PREFIX}{datetime.now():%Y%m%d_%H%M%S}.json.gz")


async def _system_panel() -> None:
    async with db.session() as session:
        info = await service.system_info(session, get_settings())
    with ui.element("div").classes("w-full grid grid-cols-2 md:grid-cols-3 gap-3"):
        stat_tile(t("admin.system.version"), info.version)
        stat_tile(t("admin.system.schema"), info.schema_revision or "–")
        stat_tile(t("admin.system.database"), info.database)
        stat_tile(t("admin.system.timezone"), info.timezone)
        stat_tile(t("admin.system.reference"), t("admin.system.reference_files", n=info.reference_files))
    with section(t("admin.system.tables")), ui.column().classes("w-full gap-1"):
        for table in info.tables:
            with ui.row().classes("w-full no-wrap gap-3 text-sm"):
                ui.label(table.name).classes("grow font-mono text-xs truncate")
                ui.label(str(table.rows)).classes("font-medium")
