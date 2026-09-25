"""Constants for the Counterparty Logos integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "counterparty_logos"
PLATFORMS: list[Platform] = [Platform.SENSOR]

CONF_BRANDFETCH_CLIENT_ID = "brandfetch_client_id"
CONF_LOGO_DEV_PUBLISHABLE_KEY = "logo_dev_publishable_key"
CONF_LOGO_DEV_SECRET_KEY = "logo_dev_secret_key"
CONF_IMAGE_PROVIDER = "image_provider"
CONF_NAME_ATTRIBUTES = "name_attributes"

PROVIDER_LOGO_DEV = "logo_dev"
PROVIDER_BRANDFETCH = "brandfetch"
PROVIDER_OVERRIDE = "override"

# Transaction dict keys that hold a counterparty/merchant name, in the formats
# produced by fints (applicant_name), PSD2/GoCardless-style integrations
# (counterparty, creditor_name, debtor_name) and Trade Republic (title).
DEFAULT_NAME_ATTRIBUTES = [
    "applicant_name",
    "counterparty",
    "creditor_name",
    "debtor_name",
    "title",
]

OVERRIDES_FILE = "counterparty_logos.yaml"
STORAGE_KEY = f"{DOMAIN}.cache"
STORAGE_VERSION = 1

# Unmatched names are searched again after this long; matches are kept until
# the cache is cleared explicitly.
NEGATIVE_CACHE_TTL = timedelta(days=30)
# Brandfetch allows 200 search requests per 5 minutes per IP.
SEARCH_DELAY_SECONDS = 1.6
SCAN_DEBOUNCE_SECONDS = 15
REQUEST_TIMEOUT = 15

LOGO_SIZE = 128
# Minimum Brandfetch qualityScore for a search hit to be accepted; filters out
# personal websites and parked domains matching private persons' names.
MIN_QUALITY = 0.35
# Hits whose name merely starts with the query need more confidence.
MIN_PREFIX_QUALITY = 0.6
MIN_PREFIX_QUERY_LENGTH = 5
# difflib ratio at which a result name counts as an exact name match.
EXACT_MATCH_RATIO = 0.9
EXACT_MATCH_BONUS = 0.2
DOMAIN_MATCH_BONUS = 0.1

SERVICE_LOOKUP = "lookup"
SERVICE_REFRESH = "refresh"
ATTR_NAME = "name"
ATTR_RETRY_UNMATCHED = "retry_unmatched"
ATTR_CLEAR_CACHE = "clear_cache"
