# Admin P19

Export `AdminPage` for `/fund/admin`. One settings section is displayed at a time; section selection is persisted in `?section=roles|import|channels|integrations|ai|rules|audit`. Desktop navigation uses compact text tabs; mobile uses the shared custom settings-section combobox. Staff grant lists are collapsed under their active count while identity, contact and MFA stay visible. Scope labels and explicit revoke confirmation remain available after expansion.

The staff UI consumes the canonical staff directory, permission catalog, scope options, user search, invitation lifecycle and grant/revoke endpoints. Invitation actions show the concrete recipient/grants before an explicit send. Current versions and stable logical receipts are used; there is no independent staff store.

Notification templates/delivery are composed from their owner's existing UI. AI configuration reuses `AISettingsPanel`. Imports link to the existing mapping/dry-run/apply/journal workflow. Integration health uses real notification readiness; unconfigured Google Sheets and Добро.рф remain unavailable. Rule processing links to the canonical signals UI. The audit tab reads the canonical AuditEvent metadata projection through `/coord/admin/audit`; general integration config endpoints are not invented.

Validation: scoped TypeScript and three focused staff permission-scope/review, section-selection and collapsed-grant interaction tests. Root owns route mounting, the generated SDK and browser visual acceptance. Full local typecheck remains blocked by unrelated missing studio JS dependencies in this worktree.

Audit uses a bounded 30-event page with exact-command and Moscow-date filters, scope/filter-bound opaque cursors, Russian action descriptions and expandable technical IDs. Desktop rows become compact mobile cards. Safe backend projection/ACL/pagination have six PostgreSQL tests; two UI tests verify metadata, fallback details, exact cursor pagination and read-only filter application.
