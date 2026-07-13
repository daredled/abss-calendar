"""
sync_calendar.py

Maneja la autenticación OAuth contra Google Calendar API y expone
funciones para crear, actualizar y borrar eventos.

Primer uso: se abre el navegador para autorizar, y se genera token.json.
Usos siguientes: el token se refresca solo (mientras el script corra
al menos una vez cada ~6 meses, Google no revoca el refresh token).
"""

import os
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_credentials(credentials_path: str, token_path: str) -> Credentials:
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)

        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return creds


class CalendarSync:
    def __init__(self, credentials_path: str, token_path: str, calendar_id: str,
                 timezone: str = "America/Santiago"):
        creds = get_credentials(credentials_path, token_path)
        self.service = build("calendar", "v3", credentials=creds)
        self.calendar_id = calendar_id
        self.timezone = timezone

    def _build_event_body(self, partido: dict, duration_minutes: int) -> dict:
        start_dt = datetime.strptime(f"{partido['fecha']} {partido['hora']}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        location = partido["gimnasio"]
        if partido.get("direccion"):
            location = f"{location}, {partido['direccion']}"

        return {
            "summary": f"{partido['equipo_local']} vs {partido['equipo_visita']} ({partido['categoria']})",
            "location": location,
            "description": (
                f"Partido ABSS - ID {partido['id_partido']}\n"
                f"Cancha: {partido.get('cancha', '')}\n"
                f"Categoría: {partido['categoria']}"
            ),
            "start": {"dateTime": start_dt.isoformat(), "timeZone": self.timezone},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": self.timezone},
            # Guardamos el id_partido en el propio evento (no solo en
            # state.json) para poder recuperarlo con find_event_id_by_partido
            # si state.json se pierde, y así no crear duplicados.
            "extendedProperties": {
                "private": {"id_partido": str(partido["id_partido"])},
            },
        }

    def find_event_id_by_partido(self, id_partido: str) -> str | None:
        """
        Busca en el calendario un evento ya creado para este id_partido,
        usando la extended property guardada en _build_event_body. Sirve
        para no duplicar eventos si state.json se pierde o se corrompe.
        """
        result = self.service.events().list(
            calendarId=self.calendar_id,
            privateExtendedProperty=f"id_partido={id_partido}",
            maxResults=1,
        ).execute()
        items = result.get("items", [])
        return items[0]["id"] if items else None

    def insert_event(self, partido: dict, duration_minutes: int) -> str:
        body = self._build_event_body(partido, duration_minutes)
        created = self.service.events().insert(
            calendarId=self.calendar_id, body=body
        ).execute()
        return created["id"]

    def update_event(self, event_id: str, partido: dict, duration_minutes: int) -> None:
        body = self._build_event_body(partido, duration_minutes)
        self.service.events().update(
            calendarId=self.calendar_id, eventId=event_id, body=body
        ).execute()

    def delete_event(self, event_id: str) -> None:
        try:
            self.service.events().delete(
                calendarId=self.calendar_id, eventId=event_id
            ).execute()
        except Exception as e:
            # Si el evento ya no existe (ej. borrado manual), no es un error fatal
            print(f"  [aviso] no se pudo borrar el evento {event_id}: {e}")
