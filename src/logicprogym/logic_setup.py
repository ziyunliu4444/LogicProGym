"""Live Logic setup and Mackie parameter-discovery helpers."""

from __future__ import annotations

from pathlib import Path
import re
import time
from typing import Any, Iterable

import yaml

from logicprogym.adapters.mackie import (
    button_messages,
    instrument_page,
    instrument_header,
    send_all,
    track_select_messages,
)


def mackie_adapter(env):
    """Return the Mackie component from a Mackie-only or hybrid environment."""

    adapter = env.unwrapped.adapter if hasattr(env, "unwrapped") else env.adapter
    component = getattr(adapter, "mackie", adapter)
    if not hasattr(component, "service"):
        raise ValueError("This configuration does not contain a Mackie adapter")
    return component


def expected_names(component, track_id: str) -> set[str]:
    """Return configured parameter names for one logical track."""

    return {
        parameter.name.strip().lower()
        for parameter in component.parameter_descriptors
        if parameter.track_id == track_id and parameter.name.strip()
    }


def is_parameter_view(controller, names: Iterable[str] = ()) -> bool:
    """Recognize either Logic's page header or its parameter name/value view."""

    lcd = controller.lcd
    if instrument_header(lcd) is not None:
        return True
    configured = {name.strip().lower() for name in names if name.strip()}
    displayed = {upper.strip().lower() for upper, _lower in lcd.strips if upper.strip()}
    if configured & displayed:
        return True

    # A Mackie value view has parameter names above values but no Track/Page
    # header. Recognize it independently of the configured page so a scanner
    # can recover when Logic was left on page 2 or later. Mixer/select views
    # generally contain instrument names rather than several numeric values.
    numeric_values = sum(
        re.search(r"[-+]?\d", lower) is not None
        for _upper, lower in lcd.strips
        if lower.strip()
    )
    return numeric_values >= 2


def _wait_until(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _scan_header(controller, logic_track: int) -> bool:
    """Require a complete name-page header for the requested track."""
    header = instrument_header(controller.lcd)
    return header is not None and header['track'] == logic_track


def _wait_stable_view(controller, predicate, timeout):
    """Allow partial LCD writes to settle before accepting a mode transition."""
    deadline = time.monotonic() + timeout
    rows = controller.lcd.rows
    changed = time.monotonic()
    while time.monotonic() < deadline:
        current = controller.lcd.rows
        if current != rows:
            rows, changed = current, time.monotonic()
        if predicate() and time.monotonic() - changed >= 0.15:
            return True
        time.sleep(0.02)
    return False


def activate_parameter_view(component, track_id: str, timeout: float = 3.0, *, scan=False):
    """Select a track and enter Instrument Edit without overshooting the view."""

    bridge = component.service.bridge
    if bridge is None:
        raise RuntimeError("The Mackie service is not connected")
    controller = bridge.pool.acquire(track_id)
    track = bridge.pool.tracks[track_id]
    names = expected_names(component, track_id)
    ready = (lambda: _scan_header(controller, track.logic_track)) if scan else (
        lambda: is_parameter_view(controller, names)
    )
    before = controller.lcd.rows
    send_all(controller.output, track_select_messages(track.logic_track - 1))
    _wait_until(lambda: controller.lcd.rows != before, min(0.75, timeout))
    time.sleep(0.10)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _wait_stable_view(controller, ready, 0.20):
            return controller
        before = controller.lcd.rows
        send_all(controller.output, button_messages("instrument"))
        # Wait for this individual button press to produce feedback before
        # considering another press. Logic emits each display as several
        # partial SysEx writes, so also give the frame a short settling window.
        if _wait_stable_view(controller, ready, min(0.75, timeout)):
            return controller
    raise RuntimeError(
        f"Logic did not expose Instrument parameters for {track_id!r}; "
        f"current display is {controller.lcd.strips!r}. Confirm that this "
        f"Mackie controller is assigned to Logic track {track.logic_track}."
    )


def validate_parameter_names(component, track_id: str, controller) -> tuple[str, ...]:
    """Return configured names that are absent from the current Mackie page."""

    configured = expected_names(component, track_id)
    displayed = {upper.strip().lower() for upper, _ in controller.lcd.strips}
    return tuple(sorted(configured - displayed))


def compare_catalog(bindings, pages):
    """Match names at exact page/slot addresses, never anywhere in a display."""
    actual = {(p['page'], item['slot']): item['name'] for p in pages for item in p['parameters']}
    failures = []
    for binding in bindings:
        address = (binding['page'], binding['slot'])
        name = actual.get(address)
        if name is None or name.strip().casefold() != binding['name'].strip().casefold():
            failures.append(f"page {address[0]} slot {address[1]}: expected {binding['name']!r}, got {name!r}")
    return tuple(failures)


def scan_parameters(
    component,
    track_id: str,
    *,
    pages: int,
    timeout: float = 3.0,
    start_page: int | None = None,
) -> list[dict[str, Any]]:
    """Read parameter names from consecutive Mackie Instrument pages."""

    if start_page is not None and start_page < 1:
        raise ValueError('start_page must be positive')
    if pages < 1:
        raise ValueError("pages must be positive")
    # Scan activation must not accept mixer numeric values or names left over
    # from another instrument. Reach the requested track's header directly.
    controller = activate_parameter_view(component, track_id, timeout, scan=True)
    bridge_track = component.service.bridge.pool.tracks[track_id].logic_track

    # Scanning must use Logic's stable header/name view: its upper row contains
    # the track/instrument/Page marker and its lower row contains parameter
    # names. The value view is useful during control, but partial page updates
    # can otherwise make percentages look like parameter names.
    marker = instrument_page(controller.lcd)
    if marker is not None and start_page is not None and marker[0] != start_page:
        raise RuntimeError(f'Visible page {marker[0]} contradicts --start-page {start_page}')
    if marker is None:
        if start_page is None or start_page < 1:
            raise RuntimeError(
                "Instrument header recognized, but its page number is truncated. "
                "Set the desired page in the emulator, then supply --start-page N "
                "to explicitly identify the current page. No catalog was written."
            )
        marker = (start_page, start_page + pages - 1)
    assert marker is not None

    # Make --pages deterministic even if a previous program left the Mackie on
    # another page.
    while marker[0] > 1 and start_page is None:
        current = marker[0]
        send_all(controller.output, button_messages("cursor_left"))
        if not _wait_until(
            lambda: (instrument_page(controller.lcd) or (current, 0))[0] < current,
            timeout,
        ):
            raise RuntimeError("Logic did not navigate back to Instrument page 1")
        time.sleep(0.05)
        marker = instrument_page(controller.lcd)
        assert marker is not None

    found: list[dict[str, Any]] = []
    first_page = marker[0]
    if instrument_page(controller.lcd) is not None and first_page + pages - 1 > marker[1]:
        raise ValueError(f'Only {marker[1]} Instrument pages are available')
    for page in range(first_page, first_page + pages):
        if not _wait_stable_view(controller, lambda: _scan_header(controller, bridge_track), timeout):
            raise RuntimeError('Track identity lost while scanning; no catalog written')
        visible_page = instrument_page(controller.lcd)
        if visible_page is not None and visible_page[0] != page:
            raise RuntimeError('Page changed unexpectedly while scanning; no catalog written')
        parameters = [
            {"slot": slot, "name": lower}
            for slot, (_upper, lower) in enumerate(controller.lcd.strips, start=1)
            if lower
        ]
        found.append({"page": page, "parameters": parameters})
        if page == first_page + pages - 1:
            break
        before_names = controller.lcd.rows[1]
        current = (instrument_page(controller.lcd) or (page, pages))[0]
        send_all(controller.output, button_messages("cursor_right"))
        if not _wait_until(
            lambda: (
                (instrument_page(controller.lcd) or (current, 0))[0] == current + 1
                or (start_page is not None and _scan_header(controller, bridge_track)
                    and controller.lcd.rows[1] != before_names)
            ),
            timeout,
        ):
            raise RuntimeError(f"Logic did not return Mackie page {page + 1}")
        # Logic sends a page refresh as several SysEx fragments. Allow the
        # final parameter-name fragment to arrive after the marker changes.
        time.sleep(0.05)
    return found


def save_catalog(
    path: str | Path,
    *,
    track_id: str,
    logic_track: int,
    controller: int,
    pages: list[dict[str, Any]],
) -> None:
    """Merge one scanned track into a reusable YAML catalog."""

    destination = Path(path)
    data: dict[str, Any] = {}
    if destination.exists():
        loaded = yaml.safe_load(destination.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data = loaded
    tracks = data.setdefault("tracks", {})
    tracks[track_id] = {
        "logic_track": logic_track,
        "mackie_controller": controller,
        "pages": pages,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
