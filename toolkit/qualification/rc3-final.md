# RC3 fork qualification — 11 September 2026

This record separates a tested fork toolkit from upstream acceptance and production
deployment. Runs use existing agent sessions; no paid model calls were made.

## Recorded results

| Journey | Result and evidence |
| --- | --- |
| Review | Disposable fork PR #10, run `20260911T085939Z-833997f93b3d`: independent build passed in 90.6 seconds; the existing agent completed a development-exposed rereview of a docstring clarification. No actionable findings. This is operational qualification, not an accuracy measurement. |
| Publication | [34582174716](https://github.com/williamjblair/formal-conjectures/actions/runs/34582174716) posted through the designated workflow. A repeat reused archive `24af3dcbb90d492fb47125b228e11b87790f3c67`, the same request, and [the same bot comment](https://github.com/williamjblair/formal-conjectures/pull/10#issuecomment-5616044240). |
| Historical inspection | After the disposable PR head changed from `d568eaccbcca931fec1cd67bf4e6d3cdd340639f` to `b74958bfbe93947c178456162230e8b091333da8`, CLI inspection returned `current_applicability: historical`, original `outcome: pass`, and exit 0. |
| Cancelled/displaced publication | Explicit cancellation [34581523236](https://github.com/williamjblair/formal-conjectures/actions/runs/34581523236) and a displaced pending request [34580919118](https://github.com/williamjblair/formal-conjectures/actions/runs/34580919118) were retained as cancelled. The original review outcome was unchanged. |
| Invalid archive and retry | [34581010386](https://github.com/williamjblair/formal-conjectures/actions/runs/34581010386) rejected a mismatching manifest digest with an error receipt. Retrying with the correct digest completed as historical; cancellation and error receipts remain in operation history. |
| Fresh macOS initialization | Native `init` generated the exact workspace at source `c5bd5601217cbcb889e1adc2f4987dfaa854dcb1`. The operator filled `Submission.lean`, explicitly committed/pushed candidate `8b52fd8011473eb25292bb7b373f4562ee2aadc4`, and [34584245487](https://github.com/williamjblair/formal-conjectures/actions/runs/34584245487) verified it with CLI exit 0. |
| Valid hosted proof | [34581337253](https://github.com/williamjblair/formal-conjectures/actions/runs/34581337253): `pass`, typed reason `verified`, CLI exit 0. |
| Unfinished hosted proof | [34581287108](https://github.com/williamjblair/formal-conjectures/actions/runs/34581287108): `fail`, typed reason `disallowed_axiom`, CLI exit 1. |
| Failure before verification | [34581383146](https://github.com/williamjblair/formal-conjectures/actions/runs/34581383146): nonexistent candidate commit; `error`, policy `not_evaluated`, CLI exit 3. |
| Linux trust controls | [34580504177](https://github.com/williamjblair/formal-conjectures/actions/runs/34580504177) passed [eight retained controls](rc3-linux.json): valid proof, unfinished proof, imported assumption, changed executor, changed target, killed verifier subprocess, missing result and submission symlink. AF_UNIX restriction was probed in the same successful driver. Infrastructure failures retained `not_evaluated`. |
| Native exporter | [34580506688](https://github.com/williamjblair/formal-conjectures/actions/runs/34580506688) passed all ten fixtures, external-write/AF_UNIX sandbox controls and 100/100 FC100 exports (zero failures). Its artifact retains typed Comparator results. |
| Poisoned-build isolation | The [real Docker/Lean regression](rc3-isolation.json) passed: invalid candidate rejected before and after scratch Lake tampering; a valid candidate built twice in fresh containers. Image `sha256:e6750e0d24e5a27c4ff5c7c77f970cb48e3d161cd3b681ffbd0f2364d4766805` is the layout adapter over the qualified production image. |
| Exact exporter PR head | [34586409681](https://github.com/williamjblair/formal-conjectures/actions/runs/34586409681) passed independently at #5337 head `bb87dfb49125af24ba72ddfe5be894a9f4753f87`: all ten fixtures, sandbox checks and 100/100 FC100 exports, zero failures. |
| Distribution | [34580509249](https://github.com/williamjblair/formal-conjectures/actions/runs/34580509249) passed wheel-from-sdist and clean installation on macOS/Linux. [34585250020](https://github.com/williamjblair/formal-conjectures/actions/runs/34585250020) then passed clean macOS/Linux installation and live fork find/show at client `191665a19`. The later client also passed local wheel construction, clean `uvx`, RC2-to-RC3 upgrade, help/doctor, explicit fork browsing with three Erdős 92 statements and provenance, and uninstall. |
| Human pilot | William approved the [retained five-case packet](rc3-pilot.md) qualitatively. Two original coverage gaps remain; no per-case scores, missed-issue counts or effort estimates were supplied. |
| Board | [34582305572](https://github.com/williamjblair/open-formal-workflows/actions/runs/34582305572) regenerated and deployed the existing board. Its shared reader pin remains compatible; the board's queue covers upstream FC, not disposable fork PRs. |
| Fork website | [34584385037](https://github.com/williamjblair/formal-conjectures/actions/runs/34584385037) passed the full build and Pages deployment at `d32245fc1b9e54676cd2ef0633287fcbbccb3f00`. The deployed catalog matches the CI artifact byte-for-byte: 5,264 declarations, 3,105,385 bytes. [Browser and CLI checks](rc3-website.json) passed for statements, source links, hovers, variants, conditional proofs, historical operator evidence and the copied CLI command. |
| Website-only preview | The same site's published snapshot built without Lean in an isolated directory. Catalog and manifest bytes were preserved. The browser loaded published rendering and source links; absent optional feeds remained explicit without hiding the statement. This was a local preview check, not another deployment. |

The hosted executor and designated publisher use
`1a7a17cb5767a677b67478c22a3107efe46414a8`, tagged
`toolkit-qualification-20260911`. Their configuration does not change automatically
when the client is upgraded. Hosted proof targets use source
`c5bd5601217cbcb889e1adc2f4987dfaa854dcb1`; valid and unfinished public candidates are
`d5dfffdced120a6bb0cff89636c4f1e724da4989` and
`e9db832930440343c1ef446406d88c7bef6d0f86`, respectively.

The installed client fixes were tested through `191665a19` and the evaluation
harness through `a526e224c`: Linux dispatch imports, explicit
unevaluated policy for missing/malformed hosted results, and invalid optional work
entries that previously aborted site generation, and copied website commands that now
select the page's catalog explicitly. 122 toolkit tests, 123 script
tests, 8 website Python tests and 22 browser-script tests passed. Focused deliveries
retain their changes in #4899, #5386, #5387 and #5388. An initial local website test lacked Beautiful
Soup; installing the same dependency versions as CI resolved that environment error.
Isolation qualification first used the wrong image layout, then exceeded its
60-second emulated check. Both attempts remain retained. The successful run used the
existing qualification adapter and an explicit 180-second bound; normal review tools
remain bounded at 60 seconds. The harness now records container exit 124 as a timeout.

The earlier full site build [34580511357](https://github.com/williamjblair/formal-conjectures/actions/runs/34580511357) was superseded by the final handoff correction and cancelled before deployment. Its completed Lean build is not counted as a completed site qualification.

Disposable fork PR #10 was closed after qualification without merging; its
commits, advisory comment and receipts remain available.

Original attempts remain under `.conjectures/qualification/final-20260911/` and
`.conjectures/runs/`. Earlier disposable-PR attempts used an incompatible Lean 4.27
snapshot and correctly remained incomplete. They were not converted into passing
reviews. Public exports omit raw snapshots, source documents and private operator
artifacts, and retain redaction hashes.

## Qualified tool revisions

| Tool | Revision |
| --- | --- |
| Generator | `e611b55d7097b9de973cbe0cef0f0cfad66dbe92` |
| Comparator | `deec4b96fc443f9d5c4dbf3dcfb148a95be76f21` |
| Landrun | `811cfff51ceaf3d9843708aa6d22e9b84ccac8b4` |
| Nanoda | `05055695879dfebb6628a67da88ceca6cd6b0421` |

The workflow artifacts retain the compatible exporter/toolchain pins and binary
digests. The killed-process control tests result transport after a real subprocess
termination; it does not claim the Comparator binary itself crashed. FC100 export
success is not proof verification or downstream catalog admission.

The superseded fork model workflows (`advisory-external-pr-review.yml`,
`live-ai-advisory-pr-review.yml` and `review-loop.yml`) remain disabled. The supported
Actions review wrapper only prepares inputs. No paid model calls or upstream
automation activation occurred.

## Publication follow-up

- [RC3 assets](https://github.com/williamjblair/formal-conjectures/releases/tag/toolkit-v0.2.0rc3) are published from `61e2f0e31713d0209ff35ca20cdf63ab11eb6ef3`. [Release job 34585786052](https://github.com/williamjblair/formal-conjectures/actions/runs/34585786052) passed on macOS/Linux. Both published checksums, release-URL trial/fresh install, RC2-to-RC3 upgrade, documented browsing examples and uninstall passed. The tag retains the record as it stood at release creation; this follow-up records publication acceptance.

The [live Green 72 page](https://williamjblair.github.io/formal-conjectures/theorem/?name=Green72.green_72)
shows both the passing and earlier incomplete review as historical operator reports.
Its mathematical status remains open. The copied command selects this fork explicitly.
Erdős 92 retains distinct strong, weak and test entries; Erdős 427 names its unproven
proof condition. The upstream board feed is available, but the page correctly refuses
to join its PRs to the fork repository. A normal browser reload initially retained
the previous deployment; a cache-bypassing reload loaded the qualified revision.
Both snapshots displayed their own source revision.

A final visual check found that the long CLI command overflowed the page.
`ead0c8b079dc85a75d8582c5d48801bf8c7f5c7c` constrains the command to its own
horizontal scroll area and allows revision text to wrap. A browser CSS check reduced
the page width from 1,312 px to the 1,170 px viewport while preserving all command
text. The change is also on #5388. Its [full deployment follow-up](https://github.com/williamjblair/formal-conjectures/actions/runs/34593897162)
is still running; the earlier functional qualification remains retained.

## Remaining acceptance and experimental work

- Finish the CSS follow-up deployment and check its actual published layout.
- Production default browsing and upstream queue/evidence handoff require #5375
  and #5388 acceptance and deployment, followed by an independent reader handoff.
  The fork is an explicitly selected source. Operator browser checks do not stand
  in for that independent acceptance.
- Replay each dependent PR's own changes after its prerequisites merge. Adopt
  accepted generator/Comparator revisions only after rerunning affected checks.
- Harbor remains an experimental follow-up: a fully qualified solver/verifier image
  trial is outstanding. The installed Harbor is 0.22.0; available FC review images
  do not contain the qualified proof executor. The retained missing-tools trial
  is not successful proof grading. This does not block the core CLI release.
- #5461 still needs real queue-to-main artifact reuse, deployment and cache-write
  qualification. #5468's hosted targeted path passed; its reduced PR coverage
  requires maintainer acceptance. Neither is enabled upstream by this release.
