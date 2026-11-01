# Agent instructions

## Project

This Home Assistant integration resolves counterparties from transaction attributes to brand logos and exposes the matches as a sensor. It supports logo.dev, Brandfetch, and local overrides.

## Working in this repository

- Read `README.md` before changing provider lookup, matching, caching, or override behavior; it documents provider constraints and how results are used.
- Keep ambiguous or low-quality matches from being presented as confirmed brands, and keep user credentials in Home Assistant's config flow.

## Validation

- Run `uvx ruff check .` and `uvx ruff format --check .` for Python changes.
- CI runs Hassfest and the shared Ruff checks; it currently has no test job.
- The shared Ruff action is maintained in [`pschmitt/ci-workflows`](https://github.com/pschmitt/ci-workflows).
