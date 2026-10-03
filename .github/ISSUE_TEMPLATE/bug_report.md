---
name: Bug report
about: Something in the lab doesn't work as documented
labels: bug
---

## Summary
<!-- One sentence: what failed? -->

## Environment
- Host OS / kernel: <!-- `lsb_release -d; uname -r` -->
- containerlab version: <!-- `containerlab version` -->
- Images: <!-- `docker images | grep -Ei 'c8000v|n9kv|xrv9k'` -->
- `make env` output:
- Host RAM / vCPU: <!-- `free -g; nproc` -->

## Stage that failed
<!-- deploy / wait / bootstrap / configure / validate / change / audit / apis -->

## Output
```
<!-- paste the relevant part; remove anything sensitive -->
```

## What I already tried
<!-- see docs/TROUBLESHOOTING.md -->
