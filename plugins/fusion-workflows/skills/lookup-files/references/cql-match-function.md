# CQL match() Function Reference

The `match()` function in CrowdStrike Query Language (CQL) lets you enrich event
data by joining it with lookup files stored in Falcon Next-Gen SIEM.

## Basic Syntax

```
match(file="<filename>", column=<key_column>, field=<event_field>, include=<output_column>)
```

| Parameter | Description |
|-----------|-------------|
| `file` | Name of the lookup file (as uploaded via `create_lookup.py`) |
| `column` | Column in the lookup file to match against |
| `field` | Event field to match with the lookup column |
| `include` | Column(s) from the lookup file to add to the event |
| `strict` | If `true`, only return events that have a match (default: `false`) |

## Examples

### IP Blocklist Matching

Given a lookup file `ip-blocklist.csv`:
```csv
ip,category,source
10.0.0.1,c2,threat-intel
192.168.1.100,scanner,internal-scan
```

Query to enrich events with blocklist data:
```
match(file="ip-blocklist.csv", column=ip, field=src_ip, include=category, include=source)
```

### Filter to Only Matched Events

Use `strict=true` to exclude events without a lookup match:
```
match(file="ip-blocklist.csv", column=ip, field=src_ip, include=category, strict=true)
```

### User Risk Score Enrichment

Given a lookup file `user-risk.csv`:
```csv
username,risk_score,department
jdoe,85,engineering
asmith,45,finance
```

Enrich authentication events with risk scores:
```
match(file="user-risk.csv", column=username, field=UserName, include=risk_score, include=department)
| risk_score > 70
```

### Asset Inventory Lookup

Given `asset-inventory.csv`:
```csv
hostname,owner,criticality,location
srv-web-01,platform-team,high,us-east
srv-db-01,data-team,critical,us-west
```

Enrich host events:
```
match(file="asset-inventory.csv", column=hostname, field=ComputerName, include=owner, include=criticality)
| criticality="critical"
```

## Multiple Includes

Add multiple columns from the lookup file by repeating `include`:
```
match(file="lookup.csv", column=key, field=event_field, include=col1, include=col2, include=col3)
```

## Common Gotchas

| Issue | Fix |
|-------|-----|
| No matches returned | Column names are case-sensitive — verify with `get_lookup.py` |
| Missing include columns | Each `include` must match a header in the CSV exactly |
| Lookup file not found | Upload with `create_lookup.py` (no search domain). A file scoped to a search view (`search_domain`) is invisible to `match()`. |
| Partial matches not working | `match()` does exact matching only — normalize data before upload |
| Performance degradation | Large lookup files (>100K rows) may slow queries — consider filtering |
