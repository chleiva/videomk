# Agent rules

- Run tests and verifications through `scripts/record_test_run.py --by <your-agent-label> --label <suite>` and commit the
  resulting `test-evidence/` files with the work. Non-pytest checks (QA video review, load or quality review) go in with
  `--manual --result pass|fail --notes ... --artifact ...`. Never edit `test-evidence/` by hand. See `test-evidence/README.md`.
- Do not run the full backend suite on the 16 GB laptop unless the task is designed for it; one heavy process at a time.

## Spend rules for QA and any AI/API call (owner rule, 28 Nov 2026, R182)

- Prefer deterministic checks: unit tests, recorded fixtures (saved plans, saved model outputs), local rendering of stills, geometry and score
  checks, `cdk synth`/`diff`. Test logic that does not need a model WITHOUT a model.
- LLM, speech, image/video-model and render calls are paid. Before any live call, state the expected cost in your brief or plan. Hard caps:
  one agent may spend at most USD 1.00 of live model/render cost unless the lead set a higher cap in writing; stop at the cap and report.
- At most 1-2 real videos per verification, never A/B batches of many plans on QA. Reuse existing QA videos and saved plans (scratchpad,
  tests/fixtures) before making new ones. Re-run only the case that changed.
- No parallel fan-out of paid calls (do not start several paid generations at once for a repeat check). No retry loops on paid calls.
- Record the actual spend (cost_usd + c_render + c_stt + c_vidup, plus Polly/Bedrock if called directly) in your final report and in the
  `--manual` evidence note. Weekly QA ceiling: about USD 25 in total, set by the lead.
- If something needs more than the cap (a quality study, a model comparison), ask the lead first; the lead asks the owner.
