# Desktop Test Skeleton (P0/P1)

## P0 (must-have smoke)
- `P0.desktop.auth.login_success`
- `P0.desktop.ipc.handshake_ready`
- `P0.desktop.navigation.components_open`
- `P0.desktop.components.primary_action_success`
- `P0.desktop.logout.clean_session`

## P1 (resilience/regression)
- `P1.desktop.components.permission_denied_shows_feedback`
- `P1.desktop.components.backend_error_500_shows_feedback`
- `P1.desktop.components.session_resume_after_restart`
- `P1.desktop.components.concurrent_surfaces_no_state_leak`

## Files
- `tests/desktop/test_desktop_components_p0_navigation_skeleton.py`
- `tests/desktop/test_desktop_components_p1_resilience_skeleton.py`
