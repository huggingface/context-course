import os


def _redirect_fa3_repo():
    # Local compatibility shim:
    # the Hopper-specific FA3 wheel currently requires GLIBC_2.32 on this host,
    # so local runs can redirect that specific kernel lookup without modifying train.py.
    if os.environ.get("AUTOLAB_FORCE_FA3_REDIRECT") != "1":
        return
    try:
        import kernels
    except Exception:
        return

    original = kernels.get_kernel

    def patched(repo, *args, **kwargs):
        if repo == "varunneal/flash-attention-3":
            repo = "kernels-community/flash-attn3"
        return original(repo, *args, **kwargs)

    kernels.get_kernel = patched


_redirect_fa3_repo()
