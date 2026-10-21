# Admin P19

Export `AdminPage` for `/fund/admin`. One settings section is displayed at a time; section selection is persisted in `?section=roles|import|channels|integrations|ai|rules`. Navigation is horizontal and reuses the original Opora SVG set and shared controls.

The staff UI consumes the canonical staff directory, permission catalog, scope options, user search, invitation lifecycle and grant/revoke endpoints. Invitation actions show the concrete recipient/grants before an explicit send. Current versions and stable logical receipts are used; there is no independent staff store.

Notification templates/delivery are composed from their owner's existing UI. AI configuration reuses `AISettingsPanel`. Imports link to the existing mapping/dry-run/apply/journal workflow. Integration health uses real notification readiness; unconfigured Google Sheets and Добро.рф remain unavailable. Rule processing links to the canonical signals UI. General audit/config endpoints are not invented.

Validation: scoped TypeScript and a staff permission-scope/review interaction test. Root owns route mounting, the generated SDK and browser visual acceptance. Full local typecheck remains blocked by unrelated missing studio JS dependencies in this worktree.
