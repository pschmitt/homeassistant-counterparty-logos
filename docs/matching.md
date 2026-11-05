# Counterparty matching

The integration scans entities with a `transactions` attribute at startup,
on transaction changes and every 12 hours. It reads names from fields such
as FinTS `applicant_name`, Trade Republic `title`, and PSD2-style
`counterparty`, `creditor_name` or `debtor_name`.

Search queries remove payment prefixes (`VISA`, `SumUp *`, `PAYPAL *`), legal
forms, regional suffixes and reference numbers. A domain embedded in a name
can be used directly. The integration searches logo.dev when a secret API key
is configured, then Brandfetch. It accepts matches only when names/domains
and quality scores are sufficient to avoid assigning unrelated brands to
private persons. Results and misses are cached per query; misses are retried
after 30 days.

Enter a logo.dev publishable key for its images, an optional logo.dev secret
key for search, or a Brandfetch client ID for search and images. Automatic
matching requires at least one search provider; otherwise only manual
overrides are available. Images are hotlinked rather than downloaded under
the providers' free-plan requirements. Check each provider's usage and caching
terms for your deployment.

## Overrides

Create `counterparty_logos.yaml` in your Home Assistant configuration. Keys
match whole words case-insensitively; the longest match wins. Use `null` to
suppress a logo. The file is re-read on each scan:

```yaml
edeka: edeka.de
lebara: lebara.de
google pay: pay.google.com
levy restaurants: null
```

## Dashboard and actions

`sensor.counterparty_logos` exposes a `logos` attribute mapping counterparty
names to logo URLs. For a custom card, look up a transaction name in that map:

```js
const logos = states['sensor.counterparty_logos'].attributes.logos;
const url = logos[transaction.applicant_name.trim()];
```

Use `counterparty_logos.lookup` to resolve an uncached name and return its
domain, source and URL, or `counterparty_logos.refresh` to rescan, retry
unmatched names or clear the cache.
