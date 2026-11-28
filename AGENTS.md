# Agent rules

- Run tests and verifications through `scripts/record_test_run.py --by <your-agent-label> --label <suite>` and commit the
  resulting `test-evidence/` files with the work. Non-pytest checks (QA video review, load or quality review) go in with
  `--manual --result pass|fail --notes ... --artifact ...`. Never edit `test-evidence/` by hand. See `test-evidence/README.md`.
- Do not run the full backend suite on the 16 GB laptop unless the task is designed for it; one heavy process at a time.
