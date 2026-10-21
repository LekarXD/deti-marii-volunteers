# Visual acceptance evidence

G1 visual proof is recorded in actual browser contexts by the integrator. Use the
reference commit in `docs/implementation/active-reference.json`; compare the same
screen/state and record reference + resulting screenshots. Required widths are
390, 768, 1050 and 1440 CSS px, plus 200% zoom, keyboard navigation and reduced
motion. Check logo/menu share the desktop line, top selection on mobile, no
sidebar, no horizontal page overflow, actual field/empty/error/conflict states,
and reload/deep links retaining the same entity.

Images alone do not prove server writes, ACL or delivery. Attach the independent
HTTP result and exact revision separately. Do not regenerate golden screenshots
to silence unexplained design differences. Browser tokens and personal data must
not be included in screenshots or traces. Use invented fixture people only.
