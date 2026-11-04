# Hallingdal Renovasjon – API notes

Verified against the live service on 2026-11-04. The API is **unofficial** for our
purposes: it is the Norconsult *ISY ProAktiv* backend used by the
"Hallingdal Renovasjon" mobile app (`com.norconsult.tommeplan.hallingdal`).

- Base URL: `https://tommeplan.vkr.no:9002`
- Server: `Microsoft-HTTPAPI/2.0` (ASP.NET Web API + Swashbuckle)
- Swagger UI: <https://tommeplan.vkr.no:9002/swagger/ui/index> (answers, HTTP 200)
- Swagger specs: `/swagger/docs/v1` and `/swagger/docs/v2`
  (title *ISY.ProAktiv.RenovasjonServiceExternal API*)

## Paths: documented vs. legacy

Swagger documents the endpoints under `/api/v1/renovasjon/...` and
`/api/v2/renovasjon/...`. The Homey app (and presumably older app versions) use
the short `/api/...` paths. Both answer and return byte-identical payloads.

| Purpose        | Documented (used by this integration) | Legacy alias       | v2                       |
|----------------|---------------------------------------|--------------------|--------------------------|
| Login          | `POST /api/v1/renovasjon/login`       | `POST /api/login`  | exists                   |
| Property search| `GET /api/v1/renovasjon/eiendommer`   | `GET /api/eiendommer` | **404** (not in v2)   |
| Pickups        | `GET /api/v1/renovasjon/tomminger`    | `GET /api/tomminger`  | exists                |

Because Swagger is the source of truth, the integration uses the documented v1
paths. A token from either login path works on every path.

## 1. Login

```
POST /api/v1/renovasjon/login
Content-Type: application/json

{"applikasjonsId": "493dc350-a80a-4797-883b-56ae44fc7ff7", "oppdragsgiverId": "100"}
```

Swagger model `LoginInfoRequest` also has `username`, `domain` and `password`;
they are not needed. `oppdragsgiverId` is documented as a semicolon-separated
list.

Response: `200`, **empty body**, with headers

```
token: 3bbaa14d-....-....-....-............   (a GUID)
tokenexpiry: 0
```

`tokenexpiry: 0` carries no useful information (see *Token lifetime*).

An unknown `applikasjonsId` gives `500` and no `Token` header.

## 2. Property search

```
GET /api/v1/renovasjon/eiendommer?adresse=<query>
Token: <token>
```

Optional, undocumented-in-practice filters: `oppdragsgiverFilter`, `postnummerFilter`.

Response `200`, JSON array of `Eiendom`:

| Field       | Type (as sent) | Example                  | Notes                                   |
|-------------|----------------|--------------------------|-----------------------------------------|
| `id`        | string (GUID)  | `"2f6c…"`                | property id used for pickups            |
| `kommuneNr` | string         | `"3318"`                 | municipality number                     |
| `kommune`   | string         | `"Krødsherad (Nytt nr)"` | name with a `(Nytt nr)` suffix – don't show as-is |
| `gNr`       | string         | `"999"`                  | numeric, sent as string                 |
| `bNr`       | string         | `"1"`                    | numeric, sent as string                 |
| `fNr`       | string         | `"0"`                    | `"0"` when no festenummer               |
| `sNr`       | string         | `"0"`                    | section number; **not in the original spec** |
| `adresse`   | string         | `"Testveien 1"`          |                                         |
| `eier`      | string         | `""`                     | always empty in every response seen     |

Observations:

- Searching the full address of the test property returned exactly one hit.
- The search is a prefix/"smart" search: a street name without number returned
  all properties on that street.
- **veg/vei trap confirmed**: `…vegen 10` returned 0 hits for a street the
  register spells `…veien`. The config flow hints at searching the beginning of
  the street name.
- No result means `200` with `[]`.
- A broad query (a common street name) returned 154 hits across two of the
  Hallingdal municipalities (Gol, Flå). No hits outside the 7 municipalities
  were observed – the `oppdragsgiverId` seems to scope the search – but the
  integration still filters on `kommuneNr` as the spec requires.
- Sectioned properties: in the broad query, 81 hits had `sNr > 0`, and 8 groups
  shared identical `adresse` + `gNr`/`bNr`/`fNr` (differing only in `sNr` and
  `id`). These are de-duplicated in the config flow (first one wins).

## 3. Pickups

```
GET /api/v1/renovasjon/tomminger?eiendomId=<id>&datoFra=YYYY-MM-DD&datoTil=YYYY-MM-DD
Token: <token>
```

All three query parameters are required (missing one → `404` "No HTTP resource
was found"). An unknown `eiendomId` gives `200` with `[]`.

Response `200`, JSON array of `Tomming`. Fields actually present:

```json
{
  "dato": "2026-11-06T00:00:00",
  "frekvensType": 4,
  "frekvensIntervall": 3,
  "fraksjon": "Matavfall",
  "fraksjonId": "111106",
  "symbolId": 9
}
```

- `dato` is a local date at midnight, no timezone. Only the date part is used.
- **The API returns the fraction name (`fraksjon`)** in addition to the id.
- Swagger also lists `eiendomId`, `eiendomsnavn`, `kommunenummer`, `rutenavn`,
  `webPortalInfo`, `telefonummerSjafor`; none of them were present in the response.
- `frekvensType`/`frekvensIntervall` meaning is undocumented (open question;
  not used).
- The range appears inclusive and past dates are returned if asked for.
- 90 days ahead returned 13 entries for the test property.

### Fractions seen

| fraksjonId | `fraksjon` (from API)          | symbolId | Spec name                  |
|------------|--------------------------------|----------|----------------------------|
| `9999`     | Restavfall                     | 15       | Restavfall                 |
| `111106`   | Matavfall                      | 9        | Matavfall                  |
| `10095`    | Papp, papir og drikkekartong   | 12       | Papir og papp              |
| `3200`     | Plastemballasje                | 14       | Plastemballasje            |
| `2612`     | Glass- og metallemballasje     | 4        | Glass- og metallemballasje |

All five ids from the Homey code showed up; no others.

## 4. Fraction list endpoint

None. `/api/fraksjoner`, `/api/fraksjon`, `/api/v1/renovasjon/fraksjoner` and
`/api/v2/renovasjon/fraksjoner` all return `404`, and Swagger lists no such
endpoint. Since every pickup carries its own `fraksjon` name, the integration
uses that name and falls back to the static table in `const.py`, then to
`Fraksjon <id>`.

## Errors and token behaviour

| Situation                       | Result                         |
|---------------------------------|--------------------------------|
| Invalid / unknown token         | `500`, empty body              |
| No `Token` header               | `500`, empty body              |
| Bad `applikasjonsId` on login   | `500`, no `Token` header       |
| Unknown path / missing param    | `404`, JSON `{"message": ...}` |

So an expired token is indistinguishable from a server error – both are `500`.
The client re-logs in once on `500`/`401` and retries.

### Token lifetime

Measured by reusing one token at growing intervals (60 s, 4 min, 10 min, 15 min,
then 30–60 min steps up to ~6 h):

| Token age | Result |
|-----------|--------|
| 2 min     | 200    |
| 6 min     | 200    |
| 16 min    | 200    |

The token was still valid after 16 minutes of idle time when v0.1.0 was tagged;
the measurement continues and this table will be extended. The login response
header `tokenexpiry: 0` does not advertise an expiry. With a 6-hour polling
interval the integration therefore expects the token to have expired on most
polls, and handles that with one re-login (two extra requests per 6 h).

For realistic tests the reauth logic is exercised with a mocked `500` on the
first call (see `tests/test_api.py`), which is exactly what the live service
returns for an invalid token.

## Deviations from the original specification

- Endpoints: the documented `/api/v1/renovasjon/...` paths are used instead of
  the short `/api/...` aliases from the Homey code (identical responses).
- The API returns the fraction name (`fraksjon`), which is preferred over the
  static table. Paper is called "Papp, papir og drikkekartong" by the API.
- `sNr` (section number) exists and is parsed; `kommune` names carry a
  `(Nytt nr)` suffix, so the config flow uses its own municipality table.
- No fraction list endpoint exists.
- Tests use Home Assistant's `AiohttpClientMocker` instead of aioresponses,
  because aioresponses 0.7.9 (latest) is incompatible with aiohttp 3.14.
- Icons are defined in `icons.json` (current HA pattern) rather than in code.

## Open questions

- Meaning of `frekvensType` / `frekvensIntervall` / `symbolId` (not needed).
- Whether `oppdragsgiverFilter` / `postnummerFilter` would make the search more precise.
- Whether properties outside the 7 municipalities can ever be returned (not observed).
