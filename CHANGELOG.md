# Changelog

All notable changes are documented here. This project follows Semantic Versioning.

## [Unreleased]

- Added the React/Vite operator UI, typed backend projections and action responses,
  and resumable first-run onboarding over existing sales records.
- Removed the old operator templates/scripts; root opens Home, old bookmarks
  redirect with query state, and unknown pages retain genuine 404 behavior.
- Consolidated frontend source into the main Git repository and planning artifacts
  under `docs/plans/`; retained the original approved UI images and visual baselines.
- Updated native startup guides for Node.js 22 and the React build; documented
  screenshot coverage, unsupported backend fields, and HTTP failure handling.
- Added frontend/API-contract and all four browser regression suites to CI.
- Standardized application, CI, and Docker environments on Python 3.12 for OpenHands support.
- Constrained the tested OpenHands, Browser Use, and Pydantic AI compatibility set to prevent pip
  resolver backtracking during clean installation.

## [0.1.0] - 2026-09-06

- Initial open-source release of the sales, marketing, research, and operations control plane.
- Bundled G1 campaign, G2 media, and G3 publishing engines.
- Added safe first-run configuration, provider diagnostics, tests, CI, and deployment guidance.
