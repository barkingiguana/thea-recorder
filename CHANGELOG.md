# Changelog

## [0.16.0] — 2026-03-13

### Features
- feat: add keyboard, mouse, and annotation methods to Recorder for library-mode parity

### Other
- Merge pull request #31 from barkingiguana/feat/library-mode-parity


## [0.14.0] — 2026-03-12

### Features
- feat: bring all 5 SDKs to feature parity with reference client

### Other
- Merge pull request #25 from barkingiguana/feat/sdk-parity


## [0.13.0] — 2026-03-12

### Features
- feat: add recording annotation endpoints

### Other
- Merge pull request #23 from barkingiguana/feat/annotations


## [0.12.0] — 2026-03-12

### Features
- feat: add Go SDK error helpers and idempotent recording/composition

### Other
- Merge pull request #22 from barkingiguana/feat/go-sdk-helpers
- docs: update marketing site, SDK docs, and integration guide for v0.10.0


## [0.11.0] — 2026-03-12

### Features
- feat: add per-session event log and live dashboard

### Other
- Merge pull request #19 from barkingiguana/feat/event-log-and-dashboard


## [0.10.0] — 2026-03-12

### Features
- feat: add live MJPEG streaming, screenshots, and panel colour/opacity

### Other
- Merge pull request #18 from barkingiguana/feat/live-streaming-screenshots-panels
- docs: document display streaming, screenshots, and panel styling


## [0.9.2] — 2026-03-12

### Fixes
- fix: use default openbox config instead of /dev/null

### Other
- Merge pull request #17 from barkingiguana/fix/openbox-config


## [0.9.1] — 2026-03-11

### Fixes
- fix: correct GitHub repo URLs in pyproject.toml and marketing site

### Other
- Merge pull request #15 from barkingiguana/fix/triage-issues-9-14
- Merge pull request #8 from barkingiguana/simplify/collapse-extras
- simplify: collapse all extras into base package


## [0.9.0] — 2026-03-11

### Features
- feat: expose Director operations over HTTP API with CLI commands

### Other
- Merge pull request #7 from barkingiguana/feat/director-api
- Merge pull request #6 from barkingiguana/refactor/director-as-submodule
- Merge remote-tracking branch 'origin/main' into refactor/director-as-submodule
- refactor: fold thea-director into thea-recorder as thea.director submodule


## [0.8.0] — 2026-03-11

### Features
- feat: add [director] optional dependency and Recorder.director property

### Other
- Merge pull request #5 from barkingiguana/feat/director-optional-dep
- Merge pull request #4 from barkingiguana/infra/director-release-and-ci-fix
- infra: add thea-director to CI and release pipeline, fix e2e-apps exclusion


## [0.7.0] — 2026-03-11

### Features
- feat: add thea-director package for human-like display interaction
- feat: add display_env property and launch_app() to Recorder

### Other
- Merge pull request #3 from barkingiguana/feat/thea-director
- chore: update uv.lock
- test: add Docker-based e2e tests for Selenium, xterm, Gnumeric, and dogfood
- docs: add comprehensive guide on how X11 recording works
- infra: skip SDK publish when unchanged, generate categorised changelogs
