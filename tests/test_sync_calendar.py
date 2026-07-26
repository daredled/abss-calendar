from unittest.mock import patch, MagicMock

from sync_calendar import CalendarSync


def _partido(**overrides):
    base = {
        "id_partido": "336",
        "fecha": "2026-07-12",
        "hora": "13:00",
        "gimnasio": "RECINTO DOS",
        "direccion": "CALLE DOS 200, COMUNA DOS.",
        "equipo_local": "MI EQUIPO 45-A",
        "equipo_visita": "OTRO EQUIPO 45-A",
        "categoria": "SERIE 45",
        "cancha": "14",
    }
    base.update(overrides)
    return base


def _make_sync_with_mocked_service():
    """Crea un CalendarSync evitando el flujo real de OAuth/build."""
    with patch("sync_calendar.get_credentials", return_value=MagicMock()), \
         patch("sync_calendar.build", return_value=MagicMock()) as mock_build:
        sync = CalendarSync(
            credentials_path="fake_credentials.json",
            token_path="fake_token.json",
            calendar_id="fake_calendar_id",
        )
    return sync, mock_build.return_value


def test_build_event_body_calcula_horario_correcto():
    sync, _ = _make_sync_with_mocked_service()
    partido = _partido(hora="13:00")

    body = sync._build_event_body(partido, duration_minutes=80)

    assert body["start"]["dateTime"] == "2026-07-12T13:00:00"
    assert body["end"]["dateTime"] == "2026-07-12T14:20:00"  # 13:00 + 80 min
    assert body["start"]["timeZone"] == "America/Santiago"


def test_build_event_body_incluye_equipos_y_categoria_en_el_titulo():
    sync, _ = _make_sync_with_mocked_service()
    partido = _partido()

    body = sync._build_event_body(partido, duration_minutes=80)

    assert "MI EQUIPO 45-A" in body["summary"]
    assert "OTRO EQUIPO 45-A" in body["summary"]
    assert "SERIE 45" in body["summary"]


def test_build_event_body_usa_solo_la_direccion_en_location():
    sync, _ = _make_sync_with_mocked_service()
    partido = _partido()

    body = sync._build_event_body(partido, duration_minutes=80)

    assert body["location"] == "CALLE DOS 200, COMUNA DOS."
    assert "RECINTO DOS" not in body["location"]


def test_build_event_body_sin_direccion_no_falla():
    sync, _ = _make_sync_with_mocked_service()
    partido = _partido(direccion=None)

    body = sync._build_event_body(partido, duration_minutes=80)

    assert body["location"] == "RECINTO DOS"


def test_insert_event_llama_a_la_api_y_devuelve_event_id():
    sync, service = _make_sync_with_mocked_service()
    service.events.return_value.insert.return_value.execute.return_value = {"id": "evt-123"}

    event_id = sync.insert_event(_partido(), duration_minutes=80)

    assert event_id == "evt-123"
    service.events.return_value.insert.assert_called_once()


def test_update_event_llama_a_la_api_con_event_id_existente():
    sync, service = _make_sync_with_mocked_service()

    sync.update_event("evt-existente", _partido(hora="15:00"), duration_minutes=80)

    _, kwargs = service.events.return_value.update.call_args
    assert kwargs["eventId"] == "evt-existente"
    assert kwargs["body"]["start"]["dateTime"].startswith("2026-07-12T15:00")


def test_delete_event_no_lanza_excepcion_si_la_api_falla():
    sync, service = _make_sync_with_mocked_service()
    service.events.return_value.delete.return_value.execute.side_effect = Exception("404")

    # No debe propagar la excepción (evento ya borrado manualmente, por ejemplo)
    sync.delete_event("evt-inexistente")


def test_build_event_body_incluye_id_partido_en_extended_properties():
    sync, _ = _make_sync_with_mocked_service()
    partido = _partido(id_partido="336")

    body = sync._build_event_body(partido, duration_minutes=80)

    assert body["extendedProperties"]["private"]["id_partido"] == "336"


def test_find_event_id_by_partido_devuelve_id_si_existe():
    sync, service = _make_sync_with_mocked_service()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt-336"}]
    }

    event_id = sync.find_event_id_by_partido("336")

    assert event_id == "evt-336"
    _, kwargs = service.events.return_value.list.call_args
    assert kwargs["privateExtendedProperty"] == "id_partido=336"


def test_find_event_id_by_partido_devuelve_none_si_no_existe():
    sync, service = _make_sync_with_mocked_service()
    service.events.return_value.list.return_value.execute.return_value = {"items": []}

    event_id = sync.find_event_id_by_partido("999")

    assert event_id is None
