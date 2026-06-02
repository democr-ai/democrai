# Developer Checklists

## PR Checklist

- [ ] Manifest and module structure are valid
- [ ] Action names are namespaced
- [ ] No direct `core.*` imports from module code
- [ ] Permissions declared and enforced
- [ ] Locales added for user-facing strings
- [ ] Dynamic updates use typed effects
- [ ] Tool and agent outputs are serializable
- [ ] Tests cover critical paths

## Release Checklist

- [ ] Module loads in clean runtime
- [ ] AuthZ behavior verified with least-privileged role
- [ ] External access approvals tested
- [ ] No silent fallback on critical flows
- [ ] Documentation updated
