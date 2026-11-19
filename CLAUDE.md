# Hallingdal Renovasjon

HACS integration for Home Assistant: waste collection schedule from Hallingdal
Renovasjon IKS through the unofficial Norconsult ISY ProAktiv app API. The API's
observed behaviour is recorded in `docs/api.md`; read it before touching `api.py`.

## Layout

- `custom_components/hallingdal_renovasjon/`
  - `api.py`, `const.py` – HTTP client and constants, independent of Home Assistant
  - `coordinator.py` – polls every 6 hours, 90 days ahead; entities only read its data
  - `sensor.py`, `binary_sensor.py`, `calendar.py`, `entity.py` – entities per property
  - `config_flow.py` – address search, property choice, reconfigure, reauth
  - `__init__.py` – static paths, card loading, WebSocket command `hallingdal_renovasjon/status`
  - `frontend/hallingdal-renovasjon-card.js` – the dashboard card and its editor, one plain file
- `tests/` – pytest with `pytest-homeassistant-custom-component`

## Checks

Run all four before calling a change done; CI runs the same.

```bash
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/pytest -q
```

`scripts/lint` formats and autofixes. `scripts/develop` starts a local Home
Assistant on http://localhost:8123 using `config/`.

## Rules

- `api.py` and `const.py` must not import `homeassistant` (a test enforces it).
- The version lives in three places that must match: `manifest.json`,
  `const.py` (`VERSION`) and `pyproject.toml` (a test enforces it). The card and
  its images are cache-busted with `VERSION`, so frontend changes need a release
  bump to reach browsers.
- `translations/en.json`, `nb.json` and `nn.json` must have identical keys (a test
  enforces it). Do not add `strings.json`; it was removed on purpose.
- The card has its own strings for `nb`, `nn` and `en` in `STRINGS` and
  `FRACTIONS`; keep all three complete.
- No Node, npm or build step, in the project or in CI. The card stays a single
  hand-written file with no JavaScript test suite.
- Tests never talk to the live service. Mock HTTP with `MockApi` from
  `tests/conftest.py`.
- Home Assistant tests run in US/Pacific by default; use the `oslo_tz` or
  `setup_integration` fixture for Norwegian local time.
- Entity ids are set explicitly from the address and a Norwegian key
  (`sensor.<address>_restavfall`) so they do not depend on the UI language.
  Changing them breaks users' dashboards and automations.
- `calendar.py` reads only the coordinator's data; no API calls in `async_get_events`.
- TLS verification is never turned off. The WebSocket status command returns
  only a translation key, never raw error text, tokens or property ids.
- Never commit `merker/` (copyrighted source images) or anything under `config/`
  except `configuration.yaml`.

## Error handling

There are no user credentials, so reauth is only "try again", and
`ConfigEntryAuthFailed` stops polling until the user confirms it. Raise
`ApiAuthError` only for a real rejection (HTTP 401 with a fresh token, or a login
without a token). Server errors, including HTTP 500 after a re-login, are
`ApiResponseError` so the coordinator keeps retrying by itself.

## Commits

Conventional prefixes in English (`feat:`, `fix:`, `chore:`, `docs:`, `ci:`).
Releases are their own commit: `chore: release X.Y.Z`.
