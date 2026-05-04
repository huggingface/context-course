# Hugging Face URL Workflows for llama.cpp

Use URL-only workflows first. Do not require `hf` or API clients just to find
GGUF files, choose a quant, or build a `llama-server` command.

## Core URLs

```text
Search:
https://huggingface.co/models?apps=llama.cpp&sort=trending

Search with text:
https://huggingface.co/models?search=<term>&apps=llama.cpp&sort=trending

Search with size bounds:
https://huggingface.co/models?search=<term>&apps=llama.cpp&num_parameters=min:0,max:24B&sort=trending

Repo local-app view:
https://huggingface.co/<repo>?local-app=llama.cpp

Repo tree API:
https://huggingface.co/api/models/<repo>/tree/main?recursive=true

Repo file tree:
https://huggingface.co/<repo>/tree/main
```

## Search for llama.cpp-compatible models

Start from the models page with `apps=llama.cpp`.

Use:

- `search=<term>` for model family names such as `Qwen`, `Gemma`, `Phi`, or
  `Mistral`
- `num_parameters=min:0,max:24B` or similar if the user has hardware limits
- `sort=trending` when the user wants popular repos right now

Do not start with random GGUF repos if the user has not chosen a model family
yet. Search first, shortlist second.

## Use the local-app page for the recommended quant

Open:

```text
https://huggingface.co/<repo>?local-app=llama.cpp
```

Extract, in order:

1. The exact `Use this model` snippet, if it is visible as text.
2. The `Hardware compatibility` section from the fetched page text or HTML:
   - quant label
   - file size
   - bit-depth grouping
3. Any extra launch flags shown in the snippet, such as `--jinja`.

Treat the HF local-app snippet as the source of truth when it is visible.

If the fetched page source does not expose `Hardware compatibility`, say that
the section was not text-visible and fall back to the tree API plus generic
guidance from `quantization.md`.

## Confirm exact files from the tree API

Open:

```text
https://huggingface.co/api/models/<repo>/tree/main?recursive=true
```

Treat the JSON response as the source of truth for repo inventory.

Keep entries where:

- `type` is `file`
- `path` ends with `.gguf`

Use these fields:

- `path` for the filename and subdirectory
- `size` for the byte size
- optionally `lfs.size` to confirm the LFS payload size

Separate files into:

- quantized single-file checkpoints, for example
  `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`
- projector weights, usually `mmproj-*.gguf`
- BF16 shard files, usually under `BF16/`
- everything else

Ignore unless the user asks:

- `README.md`
- imatrix or calibration blobs

Use `https://huggingface.co/<repo>/tree/main` only as a human fallback if the
API endpoint fails or the user wants the web view.

## Build the command

Preferred order:

1. Copy the exact HF snippet from the local-app page.
2. If the page gives a clean quant label, use shorthand selection:

```bash
llama-server -hf <repo>:<QUANT>
```

3. If you need an exact file from the tree API, use the file-specific form:

```bash
llama-server --hf-repo <repo> --hf-file <filename.gguf>
```

4. For CLI usage instead of a server, use:

```bash
llama-cli -hf <repo>:<QUANT>
```

Use the exact-file form when the repo uses custom labels or nonstandard naming
that could make `:<QUANT>` ambiguous.

## Notes

- Repo-specific quant labels matter. Do not rewrite `UD-Q4_K_M` to `Q4_K_M`
  unless the page itself does.
- `mmproj` files are projector weights for multimodal models, not the main
  language model checkpoint.
- If the HF hardware compatibility panel is missing because the user has no
  hardware profile configured, or because the fetched page source did not expose
  it, still use the tree API plus generic quant guidance from
  `quantization.md`.
- If the repo already has GGUFs, do not jump straight to conversion workflows.
