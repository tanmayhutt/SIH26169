# Contributing

Welcome. Before changing anything, read in this order:

1. `26169.pdf`, the problem statement.
2. `docs/KNOWLEDGE_TRANSFER.md`, the problem and our solution explained completely.
3. `docs/HANDOVER.md`, how to set up, run, verify, release and deploy.
4. `CLAUDE.md`, the rules every contributor and AI agent follows here.

## Getting access

Ask the project owner for: collaborator access to this repository; your SSH public key on the
server (only if you will deploy); the login for the project site.

## Working on a change

1. `git pull`, then create a branch: `git checkout -b <short-topic>`.
2. Make the change. Settings belong in `fsoc_tracker/engine/config.py`; anything the user sees in
   the desktop app or web app (panel fields, tiles, texts) in `fsoc_tracker/ui_shared.py`.
3. Verify (details in `docs/HANDOVER.md` section 8):
   - `python -m pytest` passes.
   - For perception, estimation or control changes: the regression batch before and after, and
     `python tools/compare_batches.py <before> <after>` reports no run worse.
   - `python webapp/smoke.py` passes.
4. Update the records the change affects: `web/progress.json`, `PROGRESS.md`, `COMPLIANCE.md`,
   `docs/HANDOVER.md`, `docs/KNOWLEDGE_TRANSFER.md`, and the PDFs (`python docs/build_pdfs.py`).
5. Commit with your own git identity and a short message; push the branch; open a pull request.
   The template lists the checks.

## Hard rules

- Build to the PDF. Never tune the system to a video or scenario one of us made; fix only general
  defects and prove them on the whole scenario pack.
- Never look at or copy other SIH26169 teams' code.
- Report measured numbers only; document limits, never hide them.
- The desktop executable must keep working offline with no account.
- Never commit `results/`, local notes, passwords, tokens or keys.

## Releasing

Only after `main` is green: run the "Build desktop application" workflow, then
`bash webapp/publish_builds.sh` and `bash webapp/deploy.sh` (needs server access). See
`docs/HANDOVER.md` section 9.
