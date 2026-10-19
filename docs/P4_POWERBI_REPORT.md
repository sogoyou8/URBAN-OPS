# Urban Ops P4 — 4-page Power BI report project

## Deliverables

- Generator: `scripts/build_pbip.py` — builds an editable PBIP project from P4 CSV exports, never from invented production data.
- Four report pages, 22 native visuals, nine TMDL import tables, 17 DAX measures, seven model relationships.
- `scripts/audit_history.py` reports gap coverage, sample age and trend-readiness; a **single capture has undefined coverage**, not 100%.
- CI: `.github/workflows/p4-analytics.yml` downloads real P3 release assets, validates checksums, rebuilds SQLite marts, exports data, then packages `urban-ops-p4-4pages-PBIP.zip` into GitHub Actions Artifacts.

## Open the report in Power BI Desktop (Windows)

1. GitHub > Actions > **P4 real analytics and Power BI export** > latest successful run > Artifacts > `urban-ops-p4-real-4pages-PBIP`.
2. Extract the downloaded ZIP, then extract the nested PBIP ZIP. The result includes a folder `UrbanOps` containing `UrbanOps.pbip`, `UrbanOps.Report`, `UrbanOps.SemanticModel` and `data`.
3. Open `UrbanOps.pbip` in current Power BI Desktop. In Power Query parameters, set `DataFolder` to the absolute location of the extracted `UrbanOps/data` directory, and Refresh.
4. Verify data types, relationships, error-free visuals, and four pages. Save to `.pbip` / `.pbix` using Power BI Desktop after visual verification.

## Model limitations

- The `.pbip` **is code-generated and has not been opened in Power BI Desktop on Windows** from the authoring environment; rendering/Power Query compatibility remains to be validated there. The tests validate file layout and field references only, not Desktop rendering.
- Power BI is a data visualization report, not the later Urban Ops operational web cockpit.
- Time windows and last collection timestamp must be checked against `data/manifest.json` and `COLLECTOR_COVERAGE.json`.
- No ridership, trajectory, availability duration, or predictive accuracy is inferred.
- Longitude/latitude scatter is a coordinate plot, not a GIS map or vehicle positions.
- GitHub Actions best-effort schedule has not yet demonstrated reliable recurrent triggering; archive growth must be verified before P5.

## Validation gates before marking P4 complete

- [x] Static import model and visual schema references built and locally tested.
- [x] Real P3 archive can be replayed to P4 marts (prior GitHub Actions run).
- [ ] New PBIP workflow result successful with **real** snapshot data.
- [ ] User opens in Power BI Desktop, refreshes, checks visuals, saves the finished `.pbix` or `.pbip`.
- [ ] Multiple real captures accumulated and coverage monitored.