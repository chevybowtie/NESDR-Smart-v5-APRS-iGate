Features:
* explore reverse beacon network (https://reversebeacon.net/)
* explore ADS-B 

Migration plan to split protocol tools into sub-packages:
1. Finalize WSPR feature set and merge `feature/WSPR` into `develop` for the APRS+WSPR interim release.
2. Create a new `feature/multi-tool` branch dedicated to the packaging refactor.
3. Extract shared primitives (config, logging, SDR capture, CLI helpers) into a `neo_core` module.
4. Rename the existing CLI package to `neo_aprs` and update entry points/tests to import from `neo_core`.
5. Carve WSPR logic into `neo_wspr` and point its CLI to the shared core as well.
6. Update `pyproject.toml` with extras (`.[aprs]`, `.[wspr]`, `.[all]`) and adjust packaging metadata.
7. Refresh docs/onboarding to describe the multi-tool layout while keeping a unified `neo-rx` top-level CLI.
8. Run full CI, update release tooling, and prepare migration notes before merging back to `develop`.
