# Webclient Test Skeleton (P0/P1)

## P0 (must-have smoke)
- `P0.web.auth.login_success`
- `P0.web.routing.components_page_open`
- `P0.web.components.primary_action_success`
- `P0.web.session.refresh_keeps_expected_context`
- `P0.web.auth.logout_clean_session`

## P1 (resilience/regression)
- `P1.web.components.permission_denied_feedback`
- `P1.web.components.backend_error_feedback`
- `P1.web.components.reload_no_state_leak`
- `P1.web.concurrent_tabs_no_context_overlap`

## Files
- `tests/unit/components.p0.skeleton.spec.ts`
- `tests/unit/components.p1.skeleton.spec.ts`
- `tests/e2e/components.p0.navigation.skeleton.spec.ts`
