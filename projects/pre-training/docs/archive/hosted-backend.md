# Historical Hosted Backend

Earlier revisions of this repo talked to a hosted Autolab service with
`/api/git/*` and `/api/patches` endpoints plus an `AUTOLAB_KEY`.

That backend path is retired in the active repo surface.

Current behavior:

- `scripts/refresh_master.py` restores from the local promoted master in
  `train_orig.py` and `research/live/`
- `scripts/submit_patch.py` records runs in `research/results.tsv` and promotes
  locally when a result beats current master
- no active setup flow requires `AUTOLAB`, `AUTOLAB_KEY`, or a hosted benchmark
  API

This file exists only to explain historical commits and older notes.
