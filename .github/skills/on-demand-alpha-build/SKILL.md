---
name: on-demand-alpha-build
description: "Orchestrate an on-demand Azure IoT Operations CLI alpha release from a chosen azure-iot-operations-tests ref: refresh generated release inputs, create a PR, run integration tests after merge, then start the build and wheel-publish workflow."
---

# On-demand alpha build

Use this workflow for an alpha build requested from a development or release ref. This skill orchestrates the release;
it does not duplicate template-generation rules from `sync-aio-bicep-templates`.

This workflow is resumable across human review and approval. Do not wait or poll indefinitely. At each human gate, record
the PR or workflow URL, report the exact resume condition, and stop. On the next invocation, inspect the supplied URL
or run ID and continue from the first incomplete phase.

## Required inputs

Ask for these at the start. Do not infer or invent them:

- local path to the `azure-iot-operations-tests` repository (default may be
  `~/work/azure-iot-operations-tests` only when that path exists);
- exact tests-repository branch, tag, or commit to build from;
- any tests-repository PRs or commits whose changes are required in the build, or explicit confirmation that there
   are none. For an active PR, collect its source branch and exact source commit as well as its PR URL;
- release moniker expected in `Deployment/release.json`;
- desired PEP 440 alpha CLI version, such as `2.10.0a1`;
- CLI PR base branch; ask the requester to choose explicitly (typically `dev` or `preview`) and do not assume a
   default;
- integration-test scenarios for `.github/workflows/int_test.yml` (default: all scenarios); the workflow must be
   dispatched against the CLI PR base branch after the preparation PR is merged;
- integration-test resource group and optional runtime arguments, or confirmation to use workflow defaults;

Optional resume inputs:

- PR URL or number;
- integration-test workflow run URL or ID;
- release workflow run URL or ID.

## Safety boundaries

- Never commit, push, create a PR, trigger a workflow, approve an environment, or publish merely because preflight
  succeeded. Show the proposed action and obtain explicit confirmation immediately before each remote write.
- Never merge the generated PR. A human reviewer owns approval and merge.
- Never bypass the `production` environment approval in `release_workflow.yml`.
- At each human gate, print a ready-to-send status message containing the relevant GitHub URLs so the requester can
   share it through their available communication channel. Do not store internal channel URLs or individual approval
   contacts in this public repository. Resolve approvers from the protected GitHub environment or user input at runtime.
- Never create a GitHub release for an alpha build. Alpha versions are not public GitHub releases and do not enter
  the public Azure CLI extension index.
- Preserve unrelated local changes. Stop if any file that the template-sync workflow may edit is already modified.
- Treat the requested tests-repository ref as immutable input. Export it; do not switch or edit that source worktree.

## Phase 1: preflight and prepare the PR

1. Confirm the current repository is `azure-iot-ops-cli-extension`, the GitHub remote targets the expected repository,
   `gh auth status` succeeds, and the CLI PR base branch exists on the remote.
2. Run the full preflight from `sync-aio-bicep-templates` for the supplied tests-repository ref and release moniker,
   including its local-versus-remote commit comparison and dirty-file protection.
3. Resolve every required tests-repository PR or commit before compiling:
    - resolve the selected tests ref to an immutable commit;
    - resolve each required commit and verify it is an ancestor of the selected commit with
       `git merge-base --is-ancestor <required-commit> <selected-commit>`;
    - for a required PR, query its current status and source commit. An active or unmerged PR is not included merely
       because it targets the selected branch;
    - if a required PR is active and its commit is not an ancestor, stop and ask whether to build from that PR's exact
       source commit/ref or wait for it to merge. Never silently combine commits, create a merge commit, or continue
       from the target branch;
    - list the files changed by every required commit and report whether each belongs to the compiled transitive
       closure. If it is outside that closure, stop and explain that template generation cannot include its effect;
    - after compilation and approved redactions, compare the affected generated paths and confirm that each required
       change survives. A release-policy exclusion must name only the paths being removed; do not treat approval to
       exclude one feature, such as GDS Manager, as approval to remove an independent OPC UA condition.

    Include this source-inclusion evidence in the Phase 1 report and PR body. This guard prevents an active service-team
    PR from being mistaken for content already present on its target release branch.
4. Before compiling, print the installed Bicep version. The requester explicitly requires upgrading Bicep for alpha
   preparation, but `az bicep upgrade` changes a shared machine tool. Show the current version and ask for explicit
   confirmation immediately before running:

   ```shell
   cd <tests-repository>/Deployment
   az bicep upgrade
   az bicep version
   ```

   Record the old and new versions. Do not run this command during a resumed phase, and do not downgrade. After the
   upgrade, apply the sync skill's guard that rejects an installed compiler older than the compiler embedded in the
   current template.
5. Invoke the complete `sync-aio-bicep-templates` workflow using the supplied ref, moniker, and explicit alpha CLI
   version. Do not implement a shortened constants-only sync: the template, its hash, test expectations, release
   constants, and connector constant must all come from the same compile. Do not repeat its OPC UA connector query
   here: the sync workflow already extracts the tag key-agnostically from the unredacted instance compile, treats a
   missing value as blocking, and reconciles `OPCUA_CONNECTOR_VERSION`. Carry its reported tag into this workflow's
   summary and PR metadata.
6. Validate the requested CLI version with `packaging.version.Version` and require `is_prerelease` to be true. Compare
   it with `VERSION` history on the CLI base branch and open PRs because `gh release list` cannot prove an alpha
   version is unused. Stop on reuse or ambiguity.
7. Run all validation required by `sync-aio-bicep-templates`, then run the repository CI-equivalent tests relevant to
   every changed file. Do not proceed while any check fails.
8. Show the complete diff summary, behavioral-change report, required-PR/commit inclusion evidence, source provenance,
   Bicep versions, selected source ref and commit, alpha version, and connector tag. Ask for confirmation before
   creating a branch, commit, push, or PR.
9. From the latest remote CLI base branch, create a focused branch named
   `<alias>/alpha-<CLI_VERSION>`, commit with a conventional title, push it, and create a PR targeting the chosen base.
   Include the source ref/commit, release moniker, Bicep compiler version, alpha version, connector tag, behavioral
   changes, redactions or policy overrides, and validation results in the PR body. Request reviewers only when their
   exact GitHub handles were supplied.
10. Report the PR URL and print this ready-to-send review request, substituting real values, so the requester can
   share it through their available communication channel:

    ```text
    Alpha CLI <CLI_VERSION> preparation PR is ready: <PR_URL>
    Source: azure-iot-operations-tests <SOURCE_REF> @ <SOURCE_COMMIT>
    Validation: <SUMMARY>
    Please review and merge into <CLI_BASE_BRANCH>. Reply with the PR URL after merge to continue integration tests.
    ```

11. Stop at the review gate. Do not merge and do not trigger integration tests before GitHub reports that this exact
    PR was merged into the expected base branch.

## Phase 2: after the PR is merged, run integration tests

1. Resolve the supplied PR with `gh pr view` and verify all of the following:
   - state is `MERGED`;
   - `baseRefName` equals the requested CLI base branch;
   - the merge commit is reachable from the current remote base branch;
   - the merged `VERSION` equals the requested alpha version;
   - the merged source-derived constants and templates equal those reviewed in phase 1.
2. Update the local base branch without overwriting local work. Use a clean worktree or stop.
3. Show the exact dispatch inputs and ask for confirmation before triggering
   [`.github/workflows/int_test.yml`](https://github.com/Azure/azure-iot-ops-cli-extension/actions/workflows/int_test.yml)
   with `--ref <CLI_BASE_BRANCH>`. The ref must be the preparation PR's merged base branch, not the PR head branch or
   merge ref. Omit `test-scenarios` to run all scenarios; otherwise pass the user-supplied comma-separated list. Pass
   resource group and runtime inputs only when explicitly supplied.
4. Immediately record the resulting run URL and database ID. Because workflow dispatch does not reliably return the
   run ID, correlate only runs created after the dispatch timestamp, on the exact branch, event `workflow_dispatch`,
   workflow file, and authenticated actor. If zero or multiple runs match, stop and ask instead of selecting the
   newest run blindly.
5. `gh run watch <RUN_ID> --exit-status` may be used for the finite integration-test run. If the session ends first,
   report the run URL and resume from it later.
6. If tests fail or are cancelled, print the failing job URLs and stop. Do not start a release build.
7. When all jobs succeed, summarize scenarios and conclusions, then ask for confirmation before phase 3.

## Phase 3: build and publish the alpha wheel

1. Reconfirm that the integration-test run succeeded against the same merge commit and requested alpha version.
2. Show and confirm this release dispatch policy:
   - ref: the merged CLI base branch;
   - `continue-on-error=false`;
   - `github_release=false`;
   - `upload_wheel=true`.
3. Trigger `.github/workflows/release_workflow.yml` with those inputs. Correlate and record its run exactly as in
   phase 2; never select a run solely because it is newest.
4. Watch until the run either completes or reaches the `production` environment approval gate. Never approve it.
5. At the approval gate, report the workflow URL and print this ready-to-send approval request so the requester can
   share it through their available communication channel:

   ```text
   Alpha CLI <CLI_VERSION> release workflow is waiting for production approval: <RUN_URL>
   Integration tests passed: <INT_TEST_RUN_URL>
   Approval uploads the alpha wheel to the private storage channel; it does not create a GitHub release.
   Approvers: <APPROVER_HANDLES>
   ```

6. Stop at the approval gate. Resume only after a user supplies the run URL or ID and GitHub reports that approval was
   granted.
7. After approval, watch the same run to completion. Require the upload job to succeed. Report the run and artifact
   URLs available from GitHub, but do not claim the wheel is usable through an index unless that has been verified.
8. Do not run the public extension-index hand-off. Alpha versions are not published as GitHub releases and therefore
   do not have a public wheel URL for the index.

## Failure and cancellation behavior

- Never continue from a failed PR check, integration-test run, security check, build, linter, approval rejection, or
  upload.
- Never use `continue-on-error=true` for an alpha publication candidate.
- On cancellation, report the exact completed phase, immutable source commit, PR URL, merge commit, workflow run IDs,
  and safe resume command or input.
- Do not delete test resources automatically after a failure when `keep-on-failure` was requested; report the cleanup
  deadline and the cluster-cleanup workflow instead.

## Completion report

A successful run reports:

- tests-repository ref and resolved commit;
- Bicep version before and after the approved upgrade;
- release moniker, AIO version/train, CLI alpha version, and OPC UA connector tag;
- PR URL and merge commit;
- integration-test run URL and scenario conclusions;
- release workflow URL and upload conclusion;
- every manual handoff message printed at the review and approval gates;
- confirmation that no GitHub release or public-index update was performed.
