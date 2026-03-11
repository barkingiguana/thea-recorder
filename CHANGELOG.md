# Changelog

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
