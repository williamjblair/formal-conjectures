# Thin Formal Conjectures consumer example

`review-config.example.json` shows the conclusion-free, content-addressed input shape consumed by the engine. Values are
placeholders, not a runnable or retained review packet. A real config and every referenced source remain in Formal
Conjectures and are regenerated for each exact PR head.

`consumer-workflow.example.yml` documents the small interface the FC workflow should retain after integration. It invokes
the existing `.agents/skills/formal-conjectures-review/SKILL.md` and repository `AGENTS.md`; the bot does not replace
either with its own methodology. It is an interface example, not an active workflow: the engine package must first be
pinned to an immutable commit and the existing FC deterministic/model/publication jobs updated to invoke that pin.
