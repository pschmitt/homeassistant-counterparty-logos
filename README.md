<p align="center">
  <a href="https://my.home-assistant.io/redirect/marketplace_repository/?owner=pschmitt&amp;repository=homeassistant-counterparty-logos&amp;category=integration"><img src="https://my.home-assistant.io/badges/marketplace_repository.svg" alt="Open this integration in Home Assistant Marketplace"></a>
</p>

<h1 align="center">Counterparty Logos for Home Assistant</h1>

<p align="center">Match bank transaction counterparties to brand logos for dashboards and notifications.</p>

The integration reads `transactions` attributes from banking and finance
integrations and resolves organization names through logo.dev and Brandfetch.

## Features

- **Transaction discovery:** Scan entity transaction lists for counterparty names from several common field formats.
- **Brand matching:** Normalize names and reject ambiguous matches; cache hits and misses persistently. See [Counterparty matching](docs/matching.md).
- **Overrides:** Specify domains or suppress individual names in `counterparty_logos.yaml`.
- **Dashboard data:** Expose name-to-logo URLs in a sensor attribute and provide lookup and refresh actions.

## Install

Use the Marketplace badge above on Home Assistant 2026.11 or later to add this
repository as a custom integration. On older versions, add it as a HACS
custom repository of type **Integration**. Install and restart Home Assistant.
The badge does not imply a public catalog listing. For manual installation,
copy `custom_components/counterparty_logos/` into Home Assistant's
`custom_components/` directory and restart.

## Quick start

1. Add **Counterparty Logos** under **Settings → Devices & services → Add integration**.
2. Enter a Brandfetch client ID or a logo.dev secret API key to enable searching.
3. Inspect `sensor.counterparty_logos` and use its `logos` map in a dashboard card.

## Documentation

| Topic | Description |
|-------|-------------|
| [Counterparty matching](docs/matching.md) | Providers, scoring, overrides, dashboard use and actions |

## License

[GPL-3.0](LICENSE).
