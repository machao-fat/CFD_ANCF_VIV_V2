# New Codex start here

**Do not infer project state from historical filenames or old branches.**

Before changing anything, read in order:

1. `README.md`
2. `docs/PROJECT_CONTEXT.md`
3. `docs/PHYSICS_CONTRACT.md`
4. `docs/COUPLING_CONTRACT.md`
5. `docs/VERSION_PROVENANCE.md`
6. `docs/VALIDATION_LEDGER.md`
7. `docs/KNOWN_ISSUES.md`
8. `docs/ROADMAP.md`

Then run only:

```bash
git status
git log --oneline -10
```

Confirm the working tree is clean before starting. If documentation and code conflict,
do not choose one silently; report the conflict and freeze the affected contract.

The old Windows repository is forensic history. Access it only for a specifically
identified provenance dispute. Do not search it for a “newest” file and overwrite the
new baseline.

No production FSI may start until the ledger changes the bounded HH06 status from
`NOT PASS` using a new, source-identifiable qualification report.
