"""Constants for the Hallingdal Renovasjon integration.

This module must stay free of Home Assistant imports: ``api.py`` depends on it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

DOMAIN: Final = "hallingdal_renovasjon"
LOGGER: Final = logging.getLogger(__package__)

# Keep in sync with manifest.json (checked by tests).
VERSION: Final = "0.3.0"
REPO_URL: Final = "https://github.com/slevigen/hallingdal_renovasjon"
IMAGES_URL: Final = f"/{DOMAIN}/images"  # fraction pictures served by the integration
CARD_URL: Final = f"/{DOMAIN}/hallingdal-renovasjon-card.js"  # Lovelace card, auto-loaded
USER_AGENT: Final = f"HomeAssistant-HallingdalRenovasjon/{VERSION} (+{REPO_URL})"

UPDATE_INTERVAL: Final = timedelta(hours=6)
LOOKAHEAD: Final = timedelta(days=90)
REQUEST_TIMEOUT: Final = 15  # seconds, per HTTP call

CONF_PROPERTY_ID: Final = "eiendom_id"
CONF_ADDRESS: Final = "address"
CONF_MUNICIPALITY_NUMBER: Final = "kommune_nr"


@dataclass(frozen=True)
class Fraction:
    """A known waste fraction for a provider."""

    key: str  # stable key, used in unique_id, entity_id and translation_key
    name: str  # Norwegian fallback name if the API sends none


@dataclass(frozen=True)
class Provider:
    """Everything that differs between Norconsult ISY ProAktiv providers."""

    name: str
    base_url: str
    application_id: str  # applikasjonsId
    client_id: str  # oppdragsgiverId
    municipalities: dict[str, str]  # kommuneNr -> name
    fractions: dict[str, Fraction]  # fraksjonId -> Fraction
    configuration_url: str


HALLINGDAL: Final = Provider(
    name="Hallingdal Renovasjon IKS",
    base_url="https://tommeplan.vkr.no:9002",
    application_id="493dc350-a80a-4797-883b-56ae44fc7ff7",
    client_id="100",
    municipalities={
        "3318": "Krødsherad",
        "3320": "Flå",
        "3322": "Nesbyen",
        "3324": "Gol",
        "3326": "Hemsedal",
        "3328": "Ål",
        "3330": "Hol",
    },
    fractions={
        "9999": Fraction("restavfall", "Restavfall"),
        "111106": Fraction("matavfall", "Matavfall"),
        "10095": Fraction("papir", "Papir og papp"),
        "3200": Fraction("plast", "Plastemballasje"),
        "2612": Fraction("glass_metall", "Glass- og metallemballasje"),
    },
    configuration_url="https://www.hallingdalrenovasjon.no/husholdninger/toemmekalender/",
)
