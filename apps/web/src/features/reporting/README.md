# Reports P19

Export `ReportsPage` for `/fund/reports`. Tabs use `tab=letters` and `tab=weekly`. The coordinator shell owns navigation; this feature adds no sidebar.

The page requests only server-listed scopes and canonical metric definitions. It creates immutable report snapshots, edits/reviews each narrative section, explicitly refreshes facts, confirms the report and downloads real private CSV/PDF/DOCX assets. Unknown child attendance stays unknown. AI narrative is visibly unavailable; manual text remains usable. Добро.рф shows the actual internal mapping preview and stays unavailable until its adapter is agreed.

Letters, certificates and gratitude use the profile owner's recognition/document workflow, not a second store. Weekly settings use the reporting schedule API; the worker and notice source recheck current owner/recipient authorization before delivery.

Validation: reporting module 8 PostgreSQL tests on the dedicated fictitious `opora_reporting_test` database; 3 UI boundary tests. Final 2-page PDF and 2-page DOCX were rendered with bundled Poppler/LibreOffice and all pages visually inspected at `/private/tmp/opora-reporting-evidence`. Root owns live browser visual acceptance.
