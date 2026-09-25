# Counterparty Logos for Home Assistant

`counterparty_logos` is a Home Assistant custom integration that finds brand
logos for the counterparties in your bank transactions ("VISA EDEKA 2143" →
EDEKA logo), using [logo.dev](https://www.logo.dev) and
[Brandfetch](https://brandfetch.com).

It works with any integration that exposes a `transactions` list attribute,
for example [FinTS](https://github.com/pschmitt/homeassistant-fints)
(`applicant_name`), Trade Republic (`title`) or PSD2-style integrations
(`counterparty`, `creditor_name`, `debtor_name`).

## How it works

1. Every entity with a `transactions` attribute is scanned for counterparty
   names at startup, whenever its transactions change, and every 12 hours.
2. Each name is cleaned up into a search query: card scheme and payment
   processor prefixes (`VISA`, `SumUp *`, `PAYPAL *`), legal forms (`GmbH`,
   `Limited`, …), regional suffixes (`Germany`, `Deutschland`) and reference
   numbers are removed. Names containing a domain (`Klarna*reichelt.com`) use
   that domain directly.
3. The query is sent to the brand search APIs (logo.dev first if a secret key
   is configured, then Brandfetch). A hit is only accepted if its name or
   domain matches the query and its quality score is high enough, which
   filters out private persons and random look-alike brands.
4. The result, including "no match", is **cached persistently** per query, so
   every distinct counterparty costs one search request. Misses are retried
   after 30 days.
5. `sensor.counterparty_logos` exposes the resulting map of
   `name -> logo URL` in its `logos` attribute.

Logo images are **hotlinked**, never downloaded: both providers require that
on their free plans. Both fall back to a lettermark when they have no logo for
a domain, so a URL never renders as a broken image.

## Configuration

Add the integration from **Settings → Devices & services**. Credentials:

| Field | Needed for |
|---|---|
| logo.dev publishable key (`pk_…`) | logo.dev images |
| logo.dev secret key (`sk_…`) | logo.dev Search API (optional) |
| Brandfetch client ID | Brandfetch Brand Search API and Brandfetch images |

At least one search provider (logo.dev secret key or Brandfetch client ID) is
needed to match names automatically. Without one, only overrides are used.

Note: Brandfetch's usage guidelines restrict caching Brand Search results.
Review both providers' terms for your use case.

### Overrides

Create `counterparty_logos.yaml` in your Home Assistant config directory to
fix or suppress matches. Keys are matched case-insensitively as whole words
against the counterparty name; the longest matching key wins. A `null` value
suppresses the logo. The file is re-read on every scan.

```yaml
edeka: edeka.de
lebara: lebara.de
google pay: pay.google.com
levy restaurants: null
```

## Usage

### Dashboards

```js
const logos = states['sensor.counterparty_logos'].attributes.logos;
const url = logos[transaction.applicant_name.trim()];
```

For example with a `custom:mushroom-template-card`, set `picture` to the URL
when present.

### Actions

- `counterparty_logos.lookup`: resolve names to `{domain, source, url}`,
  searching uncached names. Returns a response, handy for notifications.
- `counterparty_logos.refresh`: rescan, optionally retrying unmatched names
  (`retry_unmatched`) or clearing the whole cache (`clear_cache`).

```yaml
action: counterparty_logos.lookup
data:
  name: VISA EDEKA 2143
response_variable: result
# result.logos["VISA EDEKA 2143"].url
```

## Installation

### HACS

Add this repository as a custom repository (category: Integration), install
it, and restart Home Assistant.

### Manual

Copy `custom_components/counterparty_logos` into your Home Assistant
`custom_components` directory and restart Home Assistant.
