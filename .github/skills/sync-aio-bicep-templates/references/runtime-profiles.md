# Runtime-profile synchronization

Use with the parent skill for a CLI package that supports GA and preview runtimes independently.
This is a scope-specific extension of the existing generation workflow, not a second generator.

## 1. Inputs and write boundaries

Resolve these from the request and existing release handoff; ask only for missing decisions:

- Local deployment repository and an explicit source ref **for each selected profile**.
- Scope: `stable`, `preview`, or both. Shared enablement changes require their own explicit scope and source ref.
- Source release moniker and profile release identifier. Keep them separate: source metadata can contain a numeric
   `YYMM` release or a prefixed string while the handoff identifies preview separately. Preserve the exact source
   moniker; do not strip its prefix or silently convert it to `YYMM-preview`. Read the metadata rather than parsing
   the branch name into a release or guessing a runtime version. If no moniker was supplied, report the discovered
   value instead of treating an inferred branch suffix as a conflicting input.
- Approved public-content exclusions, deliberate train overrides, and connector/backfill compatibility inputs.
- GDS Manager exclusion is mandatory for both selected GA and preview instance templates, as defined in the
   parent skill. Earlier internal-preview retention approval is superseded; no new approval is needed to exclude it.
- Reviewed IoT Operations management API version for each selected profile, from the release handoff or confirmed
   API contract. Do not infer it from the release moniker, runtime version, or the newest available API constant.
- Approved preview notice/agreement URL in `--use-preview` help and the create long summary. Reuse the existing
   approved help during a refresh; never invent legal text or a URL.

Use the following layout for this repository:

| Scope | Generated assignment | Destination |
| --- | --- | --- |
| Shared foundation | `TEMPLATE_BLUEPRINT_ENABLEMENT` | `azext_edge/edge/providers/orchestration/template.py` |
| GA instance | `TEMPLATE_BLUEPRINT_INSTANCE` | `azext_edge/edge/providers/orchestration/template.py` |
| Preview instance | `TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW` | `azext_edge/edge/providers/orchestration/template_preview.py` |

The preview module imports `TemplateBlueprint` from `.template`; do not duplicate the class, helpers, or shared
foundation. Do not synthesize preview by copying the GA dictionary and changing its version/train.

An instance-only sync must preserve the other profile and shared enablement. A preview-only sync must also preserve
`AIO_RELEASE`, `VERSION`, package maturity metadata, and GA-specific constants such as `OPCUA_CONNECTOR_VERSION`.
Record their starting contents or parsed assignments and assert they have not changed at the end. Changes already
present in the worktree belong to the user: compare with the **pre-run worktree**, not just `HEAD`.

Inspect status for every planned destination, catalog, and test. Do not overwrite or stage existing edits. Dry-run
generation in temporary storage can continue while these files are dirty; integration must be narrowly reviewed
against their current contents. Never reset, stash, switch branches, commit, or publish as part of this skill.

## 2. Pin and generate each source independently

Apply parent preflight sections 1.1-1.10 per selected ref. In particular:

1. Compare the local ref with the remote; do not silently fetch, use a stale ref, or substitute the current checkout.
2. Resolve one commit and use it for the entire export, including imported Bicep/types, release metadata, and loaded
   YAML/JSON/text. A different GA ref is not a substitute for a missing preview dependency file.
3. Require `str(release.json['release'])` to match the source moniker. Validate the profile identifier separately;
   never compare a preview-only source release against the unchanged global `AIO_RELEASE`.
4. Export into separate `stable`, `preview`, and/or `shared` temporary subdirectories. Keep each optimizer run in
   its own directory because JSON mode always writes `optimized.json`.
5. Record the Bicep compiler version and enforce the no-toolchain-downgrade rule against the selected existing
   blueprint. For a first preview addition, compare against the shared/GA baseline. Do not install tooling silently.
6. Compile the selected instance using parent section 2: optimizer JSON mode, then `repr()` and Black. Render its
   dictionary into the corresponding `TemplateBlueprint` assignment only after review.

For a preview-only run, compile its enablement template **for comparison**, not replacement. Compare versions,
trains, resources, conditions, trust/configuration defaults, API contracts, and auto-upgrade settings with the
bundled shared foundation. Report differences; never introduce preview-specific CM/Secret Store deployments or
change `az iot ops init`. Any incompatibility with the shared foundation blocks activation until reviewed.
Compiled deployment defaults are not proof of a supported installed-dependency range.

Resolve transitive provenance with parent section 3. Record independently:

- selected `source_ref` and full resolved `source_commit` for the profile;
- justified blueprint `commit_id`, including an explicit override if transitive files require it;
- unredacted and final compiler hashes, tool version, and approved source edits.

Neither a branch name nor a `preview.N` suffix proves the actual train. Preserve the compiled train. An
`integration` build remains `integration` and needs an exact version/train/intended-channel association; do not
silently relabel it `preview` or `stable`. Shipped-train overrides require approval, an edit to exported Bicep,
and a fresh compile. Preserve source `autoUpgradeMinorVersion` inputs and flag anything other than the reviewed
manual-upgrade policy for AIO and shared dependencies.

## 3. Review before integration

Use the selected profile's previous blueprint as the baseline. For a first preview addition, use the GA instance
blueprint only as a **comparison baseline**, label the artifact as new, and report the cross-profile differences.
Do not treat the GA comparison as authorization to copy GA defaults or migrations.

Split routine changes from behavioral changes exactly as in parent section 3. Show every changed object path with
old/new values, including added/removed resources, new feature defaults, API versions, and conditions. Audit the
shared enablement comparison separately. Keep internal loaded-file blobs in temporary storage; report their paths,
readers, and intended substitutions rather than copying them into a public blueprint or publication payload.

Inspect scalar substitutions for public suitability too: replacing a loaded-file reader with its current literal
can still ship a development registry or an unapproved setting. Do not substitute a public registry or an older
connector tag on your own. Report the exact source value and request a scoped release-owner decision when needed.
A generated preview API version also requires a compatibility review of existing clients/update payloads; it does
not by itself authorize client regeneration, API fallback, or silently dropping unsupported fields.

Apply public-content exclusions and behavior-preserving loaded-file substitutions to the exported source only,
then recompile. Use the exclusions already approved through the release handoff and ask about newly unclassified
settings; do not ask for the same settled decision repeatedly. Apply the mandatory GDS Manager exclusion to each
selected profile's exported source, removing its inputs and readers rather than merely disabling its default.
Record this approved behavioral override separately from behavior-preserving substitutions. Preserve the pre-redaction output as
`opt_instance_unredacted.json` **inside that profile's temporary directory**. Resolve each literal from that same
profile/ref, not the other profile's YAML or the previous release's constant.

Present the behavioral report and obtain confirmation before writing a new generated preview module or replacing
an existing blueprint. A request to add a template is not blanket approval of all upstream behavioral changes.
When no behavioral review has happened, report `generated for review`, not `integrated` or `release-ready`.

## 4. Catalog and release metadata

After the generated content is approved:

1. Integrate only the selected complete assignment/module, preserving unrelated code and current user edits.
2. Construct that channel's `RuntimeProfile` using the generated blueprint, profile release identifier, exact ref,
   and resolved commit. Its connector version must come from that profile's reviewed source/literal substitutions;
   never update the global GA connector constant to accommodate preview.
3. In `runtime_catalog.py`, register the reviewed preview as `PREVIEW_PROFILE` only when its shared-foundation and
   runtime/API assumptions are reviewed. If still pending, leave it `None` and state that the generated blueprint
   is staged but not selectable. Do not create a dummy profile to bypass validation.
4. Treat `--use-preview` as the explicit opt-in and terms acceptance. Keep the approved notice and terms URL in
   that option's help and the create long summary, not in deployment output or runtime-profile metadata. Do not
   restore a consent prompt, TTY check, create-only `--yes`, or separate `--accept-terms` parameter. Preserve
   confirmation options on other commands. Registration also exposes update/upgrade inputs, so help text is not
   a substitute for runtime/API review.
5. Maintain exact historical `QUALIFICATION_IDENTITIES` and `SHARED_DEPENDENCY_REQUIREMENTS` only from reviewed
   handoff data. A generated target does not prove historical upgrades or every newer dependency compatible.
6. Review whether connector backfills and new resources are compatible with existing instances. Create defaults
   are not update/upgrade migrations, and a target connector tag is not automatically valid for all older runtimes
   in the channel. Report missing policies rather than stamping the latest tag indiscriminately.

### Maintain release-specific management APIs

Maintain the management API selection on every new release and same-release refresh:

1. Compare the selected profile's `iotops_api_version` in `runtime_catalog.py` with the approved release API input.
   Reuse or add the corresponding `IoTOpsMgmtApiVersion` constant in `azext_edge/edge/util/az_client.py`, and select
   it in that profile. Preserve existing constants, the nonselected profile, and the GA default during preview-only
   work. Providers must consume profile metadata, not duplicate release-specific API strings.
2. Report the management API separately from the `apiVersion` values in the compiled deployment resources.
   A user may intentionally keep an older, pinned qualification blueprint while selecting a newer management API.
   Record the approved difference and its validation status; do not silently change the source ref, refresh the
   blueprint, or hand-edit generated output to make the dates match. An API-only change does not authorize a
   template regeneration. Missing compatibility evidence remains visible in the handoff.
3. Check the selected API's operation paths, request/response shapes, and generated-client support. The existing
   model-less client can pass an explicit API version and preserve JSON fields, but that does not prove service
   compatibility or add missing preview-only operation groups. Report unsupported operations and seek scoped
   client-generation approval; never fall back silently to GA for preview mutations.
4. Update independent API expectations in `test_runtime_profiles_unit.py`, `resources/test_instances_unit.py`,
   and `test_upgrade2_unit.py`. Cover GA and preview request API versions, re-reading through the selected API
   before read-modify-write, preview field preservation, and registry/connector backfill requests. Preserve fixed
   synthetic upgrade versions and GA expectations. Test any newly supported child operations separately.
5. Run those modules and `azext_edge/tests/utility/test_az_client_unit.py` after the changes, then the section 5
   suites. Report offline request/serialization tests separately from live runtime/API qualification; do not claim
   that mocked field preservation proves server-side child-resource preservation.

`--use-preview` is a normal runtime-selection parameter, not a Preview-tagged CLI interface. Leave that distinction
and the `init` interface intact. Component `--feature ...mode=Preview` and package `--allow-preview` are unrelated.

The parent **CLI version/train policy does not apply to a multi-profile sync**. Package maturity is independent of
the selected runtime's maturity/train. Preserve `VERSION` for template preparation unless an explicit package
release change is requested. For a packaging request, use one agreed CLI version for both runtime profiles and
check reuse under the existing release process. Do not promote/demote the wheel because preview is bundled.

### Maintain release-tracking tests

Test maintenance is part of every selected-profile refresh, including a new release cycle and a same-release
re-sync. Once the source changes are reviewed, identify and update affected expectations in the same change as
the blueprint/catalog; do not ask the user to locate stale assertions or hand-edit them later.

1. For preview, inspect `azext_edge/tests/edge/orchestration/test_template_preview_unit.py` on every refresh.
   Compare its pinned AIO version, actual train, API versions, connector tags/registries, resource keys/counts,
   phase membership, feature expressions, parameter defaults and catalog/backfill assertions with the approved
   source and final compile. Update only expectations whose corresponding inputs intentionally changed.
2. Keep that file's `qualification_profile` release/ref labels aligned with the selected release/ref for clarity.
   These labels do not select the artifact or prove provenance; `source_commit="test-commit"` may remain synthetic.
   Production catalog provenance must still use the exact resolved source SHA.
3. Follow references to the selected blueprint/profile and changed release values in the orchestration tests,
   especially `test_runtime_activation_unit.py`, `test_runtime_profiles_unit.py`, `test_runtime_commands_unit.py`
   and `test_get_versions_unit.py`. Distinguish expectations for the actual bundled artifact from deliberately
   synthetic versions, historical upgrade baselines and boundary cases. Never bulk-replace old version strings
   or advance a historical fixture merely because a new release has the same-looking value.
4. Keep artifact expectations independent: take new expected literals from the reviewed source/final compile,
   not from the object under test at test runtime. Do not replace pinned assertions with self-comparisons, weaken
   them, or skip failing cases to make a refresh green. Reuse existing fixtures and expectation sets where suitable;
   preserve GA/shared expectations during preview-only work.
5. Reconcile added/removed resources and changed defaults with phase, custom-name, feature-preservation and
   catalog-wiring tests. An unexpected failure is a reason to investigate the source or implementation, not
   permission to change the expected result. Obtain the existing behavioral approval for newly discovered changes.
6. Run the focused checks below immediately after the related edits, then the broader section 5 suites. Include
   the reviewed old/new expectations and validation results in the handoff. Do not report a completed sync while
   these tests fail or have not run; report a blocked/incomplete sync instead.

For a preview refresh, run from the CLI repository root with the configured development interpreter:

```shell
python -m pytest -q \
  azext_edge/tests/edge/orchestration/test_template_preview_unit.py \
  azext_edge/tests/edge/orchestration/test_runtime_activation_unit.py \
  azext_edge/tests/edge/orchestration/test_runtime_profiles_unit.py \
  azext_edge/tests/edge/orchestration/test_runtime_commands_unit.py \
  azext_edge/tests/edge/orchestration/test_get_versions_unit.py
```

## 5. Validate selected outputs and isolation

Adapt parent section 5's AST checks to an explicit mapping of **selected outputs**; its legacy loop assumes exactly
two assignments in one file and must not be used unchanged for preview. For preview-only validation the mapping is:

- `template_preview.py:TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW` -> `<preview-temp>/opt_instance.json`.

For GA/shared runs add only their selected assignments and corresponding per-ref JSON paths. Require exactly one
assignment for each expected symbol, extract `content` with AST/literal evaluation (never import generated modules
for equality checks), and assert equality with its own final compile. Missing/duplicate assignments are failures,
not skipped checks. Compare protected assignments with their pre-run snapshots instead of unrelated fresh outputs.

For every selected output independently:

- Check exact generated dictionary equality and no surviving `$fxv` strings/references.
- Check both keys and string values in every selected final blueprint for surviving GDS Manager inputs, resources,
  configuration, and readers. Use the source-specific symbol inventory and a case-insensitive scan; any survivor
  blocks integration. Update assertions and module provenance that previously expected GDS retention.
- Check all substituted literals against its unredacted compile and loaded source files; enumerate every reader.
  Missing unredacted evidence is blocking when redactions occurred, not merely an informational warning.
- Check profile identity/release/provenance, connector tag, schema and API inputs, and manual-upgrade settings.
- For preview, check the existing runtime version policy (patch zero and dotted numeric `preview.N`). Stop on a
  mismatch; never rewrite a source version to force it to pass.
- Verify the nonselected instance and shared enablement are unchanged. For preview-only sync also check global
  release/package metadata and GA runtime constants are unchanged.
- Test selected-profile create preparation, feature/default preservation, custom instance names (including newly
  added children), and all phase resource sets. Use profile-specific resource expectations; do not append preview
  resource keys to the GA canonical set just to make the tests pass.
- Ensure profile copies do not mutate shared data. Check both profiles in one process in either selection order.
- Keep offline help/version reporting and the normal create-only selector tests green.

Run the parent template/targets/work/upgrade unit suites plus runtime profile/discovery/command/dependency and
version-reporting tests. Add tests for the actual new artifact, including catalog wiring if activated. Lint all
changed Python files and run `git diff --check`. No live tests or workflow dispatch without explicit authorization.

Report mechanical generation/test success separately from runtime qualification and public-release readiness.
A missing reviewed preview profile must remain visible rather than being replaced with synthetic test fixtures
in production. Verify flag-only preview creation is noninteractive and does not print a separate consent notice.

## 6. Handoff without publication

For template-only work, report each profile's release, actual version/train, source SHA, blueprint provenance,
compiler hash, connector version, management API and deployment API versions, shared-foundation differences,
behavioral decisions, and activation status. Include any intentional API mismatch and unverified client/service
compatibility rather than describing the profile as release-ready.
Keep review output in the conversation; do not create a separate implementation-plan document.

If a versions-wiki payload is requested, adapt parent section 6 per profile: components come from that profile's
source, dependencies from the unchanged shared blueprint, and both rows reference the same CLI package. Include
the intended runtime channel separately from the actual train. Use visible placeholders for dates and supported
upgrade baselines; do not infer them from matching versions or a successful compile. Retain integration builds as
qualification/draft inputs, not public-preview release claims.

The public index handoff in parent section 7 applies only to an explicitly requested **package release**, once per
package, not once per runtime template. Adding a preview template does not create a second wheel or index entry.
Do not publish, update the wiki/index, push, create a PR, or dispatch any workflow during synchronization.

Retain temporary artifacts through review/recompile/validation, then clean them up when the run is completed or
abandoned. Report any retained review directory while paused; never remove unrelated temporary or source files.