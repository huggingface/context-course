# Security Policy

## Secrets

Keep all credentials out of the repository.

- Store local operator env settings in `~/.autolab/credentials`.
- Authenticate the Hugging Face CLI out of band with `hf auth login`.
- Treat `HF_TOKEN` and any private infrastructure details as secrets.

Do not paste secrets into:

- git history
- public issues
- pull requests
- `research/notes.md`
- Trackio reports or shared screenshots

## Sensitive Local State

These paths are local operator state and should not be committed:

- `~/.autolab/credentials`
- `.runtime/`

`research/live/master.json`, `research/live/master_detail.json`, and
`research/live/dag.json` are tracked repo state for the current promoted local
master. Regenerate them with `uv run scripts/refresh_master.py --fetch-dag` if
needed.

## Reporting A Security Issue

If the issue involves credentials or private infrastructure access:

- do not open a public issue with the full details
- contact the maintainers directly through a private channel

If you accidentally exposed a token:

1. revoke it
2. rotate it
3. scrub the local copies
4. notify the maintainers privately if the token reached shared infrastructure
