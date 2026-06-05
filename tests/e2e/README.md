# End-to-end tests

These talk to a **real** vCenter / NSX and are excluded from the default test run.

## Run locally

```sh
export VSC_E2E=1
export VSC_VSPHERE_SERVER=vc.example.com
export VSC_VSPHERE_USERNAME=administrator@vsphere.local
export VSC_VSPHERE_PASSWORD=...
export VSC_VSPHERE_INSECURE=1          # lab / self-signed cert

# optional NSX
export VSC_NSX_SERVER=nsx.example.com
export VSC_NSX_USERNAME=admin
export VSC_NSX_PASSWORD=...
export VSC_NSX_INSECURE=1

uv run pytest tests/e2e -v
```

Each test self-skips if its backend's credentials are absent, and the whole suite
self-skips unless `VSC_E2E` is truthy. In CI they run only via the manually
triggered **e2e** workflow (`workflow_dispatch`) when the corresponding repository
secrets are configured.
