---
name: sync-aio-bicep-templates
description: Generate and safely integrate updated template.py blueprints from the azure-iot-operations-tests deployment repository and an explicit release ref.
---

# Synchronize AIO Bicep templates

Use this workflow when a teammate asks to generate `template.py` for a new AIO release.

## Required inputs

- Local path to the `azure-iot-operations-tests` deployment repository.
- Explicit release branch, tag, or commit. Release branches are named for the product series and the moniker, so
  the series segment changes when the product's minor version changes; take the ref exactly as given rather than
  assuming a series.
- AIO release moniker, such as the four-digit `YYMM` identifier for the release.
- Explicit CLI version policy when it cannot be derived safely.

Do not require the user to know repository implementation details after these inputs are supplied.

## 1. Preflight

1. Confirm the current repository is `azure-iot-ops-cli-extension`.
2. Normalize a `\\wsl.localhost\Ubuntu\...` source path to `/...` when needed.
3. Confirm the source path is a Git repository and the explicit ref resolves.
4. Confirm the local checkout of that ref is **current**. Resolve the ref locally, resolve the same ref on its
   remote with `git ls-remote <remote> <ref>`, and compare the two commit IDs. Stop and ask when they differ.
   A release branch keeps receiving commits after its templates are first generated, so a stale clone regenerates
   an earlier state and silently reverts values that already shipped — and because the regenerated output is
   internally consistent, every later check in this workflow still passes. Nothing else here can detect it.
   Report both commit IDs and let the user decide; do not fetch or update their repository on their behalf. If the
   remote cannot be reached, say the check did not run rather than treating the clone as current.
5. Confirm these source files exist at that ref:
   - `Deployment/azure-iot-operations-enablement.bicep`
   - `Deployment/azure-iot-operations-instance.bicep`
   - `Deployment/release.json`
   - `AioExtension/helm/aio/values.yaml`
6. Inspect `git status` in the CLI repository.
7. Do not overwrite existing changes in:
   - `azext_edge/edge/providers/orchestration/template.py`
   - `azext_edge/edge/providers/orchestration/common.py`
   - `azext_edge/tests/edge/orchestration/test_template_unit.py`
   - `azext_edge/tests/edge/orchestration/test_targets_unit.py`
   - `azext_edge/tests/edge/orchestration/test_work_unit.py`
   - `azext_edge/constants.py`
8. Confirm `az bicep` and Python are available, that Black runs as `<python> -m black --version`, and that
   `import yaml` succeeds in that same interpreter — sections 5 and 6 both parse YAML with it. A `black` executable
   on `PATH` is not sufficient, because section 2 invokes it as a module.
9. Print the Bicep version and record it for the section 3 report. Do **not** install an older Bicep to match
   `metadata._generator.version` in the current `template.py`. That value records the compiler used for the
   *previous* release, so matching it pins every release to an ageing compiler and yields a template that differs
   from one built with the toolchain the team actually ships; section 3 already treats `metadata._generator` as a
   routine change. Compare the two only to catch a regression: if the installed Bicep is **older** than the embedded
   version, stop and ask, because recompiling with it rewrites `_generator.version` backwards. Never change the
   machine's Bicep installation as a side effect of this workflow — it is shared with everything else on the system.
10. Parse `Deployment/release.json` from the selected ref and confirm its `release` value equals the supplied release
    moniker. Fail on a mismatch rather than combining metadata from different releases. The value is stored as an
    integer and the moniker is a string, so coerce before comparing. Compare it against the **supplied moniker**,
    never against `AIO_RELEASE`: that constant still holds the *previous* release until section 4 updates it, so
    comparing against it here fails every genuinely new release and lets only a re-sync through.
11. Note whether `AIO_RELEASE` in `azext_edge/constants.py` already equals the supplied moniker. If it does, this is
    a **re-sync** of a release that has already been generated at least once, not a new release. Say so explicitly
    and carry that fact into the `VERSION` policy in section 4, which treats the two cases differently.

## 2. Export and compile

Use temporary storage and export the requested Git ref without switching or modifying the source worktree. Ignore
untracked or modified source-worktree files.

Compile both templates:

```shell
az bicep build \
  --file <exported-source>/Deployment/azure-iot-operations-enablement.bicep \
  --outfile <temp>/enablement.json

az bicep build \
  --file <exported-source>/Deployment/azure-iot-operations-instance.bicep \
  --outfile <temp>/instance.json
```

Run the repository's existing optimizer in JSON mode from the temporary directory so it does not create output in
the CLI worktree. Do not use its Python-output mode: that legacy path invokes Black as a single executable string and
does not work reliably.

```shell
cd <temp>
<python> <cli-repo>/tools/template_optimizer.py <temp>/enablement.json json
mv optimized.json opt_enablement.json
<python> -c \
  "import json, pathlib; pathlib.Path('enablement.py').write_text(repr(json.loads(pathlib.Path('opt_enablement.json').read_text())))"
<python> -m black enablement.py --line-length=120 --target-version=py39

<python> <cli-repo>/tools/template_optimizer.py <temp>/instance.json json
mv optimized.json opt_instance.json
<python> -c \
  "import json, pathlib; pathlib.Path('instance.py').write_text(repr(json.loads(pathlib.Path('opt_instance.json').read_text())))"
<python> -m black instance.py --line-length=120 --target-version=py39
```

The optimizer always writes `./optimized.json` in the working directory, so rename it immediately after each run:
the second run overwrites the first otherwise, and section 5 reads these exact filenames.

JSON mode still runs the optimizer's JSON serialization round-trip assertions. The conversion to Python is covered
by section 5, which reparses the final assignments and requires exact dictionary equality with the optimized JSON.

Always remove temporary files at the end. Keep the exported source and its compiled output until section 5 passes:
section 4 edits that source and returns here to recompile it. When a redaction is applied, keep the first
unredacted compile as well, named exactly `opt_instance_unredacted.json` in the same directory. Section 5 reads
that literal path to prove each substituted literal is current, and silently skips the check if it is absent, so a
different name costs you the one assertion that catches a pin that has gone stale.

Render the Python with `repr()` and Black exactly as above. Do not substitute `pprint`, `json.dumps`, or another
formatter: they wrap long strings into implicitly concatenated fragments such as `"Number of AIO " "Broker "`, which
is semantically identical but rewrites hundreds of unrelated lines and buries the real release change in the diff.
The symptom is a diff far larger than the release warrants, so section 5 asks you to confirm it by looking at the
diff rather than by running a check.

## 3. Compare before editing

Parse the current blueprint assignments from `template.py` without importing that module:

- `TEMPLATE_BLUEPRINT_ENABLEMENT`
- `TEMPLATE_BLUEPRINT_INSTANCE`

Use Python AST and `ast.literal_eval`; do not import `template.py` and do not use broad regex replacement.

Determine provenance explicitly for each template:

1. Enumerate all transitively referenced local source files, including Bicep imports, local modules, and files read
   by `loadJsonContent`, `loadYamlContent`, or `loadTextContent`. Match every import form, not just the one a given
   file happens to use — `import * as <alias> from './x.bicep'`, `import {A, B} from './x.bicep'`, and
   `module <name> './x.bicep'` all introduce a dependency. Recurse into each file found, because an imported file
   may import or load others. Resolve every path relative to the importing file, not to the top-level template.
2. Derive the latest commit at the selected ref that changed the top-level Bicep file.
3. Compare every referenced file at that top-level commit with the same file at the selected ref. Treat a missing
   file as a difference.
4. If no referenced file differs, use the top-level Bicep commit as `commit_id`.
5. If any referenced file differs, report the files and commits that changed and ask for an explicit `commit_id`
   override rather than guessing.

Show the selected source-ref commit as additional context.

Separate the report into:

- **Routine release changes**
  - template commit IDs;
  - `metadata._generator`;
  - `variables.VERSIONS`;
  - `variables.TRAINS`.
- **Behavioral changes**
  - every other changed path.

For every behavioral difference, show its template name, full object path, old value, and new value. Include additions
and removals. Pay particular attention to:

- resources such as `certManagerExtension`;
- `variables.defaultAioConfigurationSettings`;
- `configurationSettings`;
- parameters and default values;
- definitions;
- dependencies and conditions;
- API versions and resource properties;
- `$fxv#N` variables, which Bicep emits whenever the source uses `loadTextContent`, `loadJsonContent`, or
  `loadYamlContent`. Each one inlines an entire source file. One such variable has embedded the internal AIO Helm
  values file — dozens of configuration sections, roughly 15 KB, including an internal registry hostname and billing
  configuration — none of which belongs in this public extension;
- parameters, variables, resources, or configuration settings that the release owner confirms must not ship in the
  public extension.

Do not hide behavioral changes behind a summary. A past release demonstrated that version bumps can also introduce
important configuration changes.

Present the report before modifying files. Ask the user to confirm when behavioral changes exist.

## 4. Update after review

After confirmation, produce the final blueprints in this order:

1. apply the redactions below, **and any release-policy override agreed below**, to the **exported Bicep source**;
2. re-run section 2 to recompile and re-optimize that edited source;
3. replace only the two complete blueprint assignments in `template.py` with the result, preserving unrelated code.

Do not embed the blueprints first and edit them afterwards. Format generated assignments with Black at line
length 120.

Every deliberate difference from upstream goes in at step 1, as an edit to the exported source, for the same reason
redactions do: the compiler emits `metadata._generator.templateHash` over whatever it compiled, so an override
applied after compilation leaves a hash that describes content nobody can reproduce, and section 5's equality check
fails with no honest way to satisfy it. Editing the source instead keeps the hash self-consistent and keeps that
check meaningful.

#### Mid-release changes go through the whole workflow

A release rarely lands in one pass. A backend fix ships, a component is re-tagged, or the train is promoted, and
someone needs to move a single value in an already generated `template.py`. Reaching into the file and editing
that one value is the single most damaging thing that can be done here, and it is easy to do because the diff
looks small and reviews cleanly.

It is damaging because `template.py` is generated output, so every value in it belongs to the same compile. Editing
one leaves the rest frozen at the previous generation: the other values the newer source moved stay stale, and
`metadata._generator.templateHash` still describes the older content, so the file no longer matches its own hash.
Nothing downstream notices. The unit tests compare the constants against each other, not against the source, so
they stay green while the file drifts further from the release it claims to describe.

Make any mid-release change by **re-running this entire workflow at the newer source ref**. It costs one more run
and produces a self-consistent file in which every derived value moved together. If a value must deliberately not
follow the source, that is a release-policy override: apply it at step 1 as a source edit and record it in
section 6, so it survives the next regeneration instead of being silently reintroduced.

The symptom to look for when auditing an existing release: content that changed while `metadata._generator` did
not. That combination is only possible if someone edited generated output by hand.

### Source redactions

`template.py` is normally byte-identical to the compiled Bicep, and that is the invariant this skill maintains.
Redactions are a deliberate, bounded exception to it: the goal is a template that deploys identically, not one that
matches the compiler byte for byte. Apply a redaction only when it is provably behavior-preserving and there is a
reason the generated form must not ship publicly. Prefer fixing the cause upstream — a connector version passed as a
parameter rather than read with `loadYamlContent` would restore byte-identical sync and make this section
unnecessary.

Regeneration is faithful to the compiled Bicep, so any redaction made for a previous release is silently reverted
unless it is re-applied.

Apply redactions by editing the **exported Bicep source copy** and recompiling it through section 2, not by editing
the generated Python dictionary. Both routes produce the same `resources`, `parameters`, and `variables`, but
`metadata._generator.templateHash` is emitted by the compiler: hand-editing the dictionary leaves a hash describing
the pre-redaction content, so the shipped template claims a hash that nothing can reproduce. Recompiling from edited
source keeps the hash self-consistent and lets a reviewer re-derive the exact artifact. The exported copy is
temporary, so editing it never touches the user's source worktree.

When removing a `param`, also remove its `@description` decorator. Deleting the `param` line alone leaves an orphaned
decorator and the compile fails with `BCP166: Duplicate "description" decorator`.

Re-apply each redaction below and report what was removed:

- **Embedded source files (`$fxv#N`).** Bicep inlines the entire file for `loadTextContent`, `loadJsonContent`, or
  `loadYamlContent`. Locate them in the exported source with
  `grep -n 'loadTextContent\|loadJsonContent\|loadYamlContent'`, then trace each declared variable to its readers
  with a second `grep` on the variable name. Delete the declaration and rewrite every reader to use the concrete
  value it resolved to, taking that value from the loaded file at the selected ref.

  The compiled form is a chain rather than a single variable: `$fxv#N` holds the file contents, a named variable
  aliases it as `[variables('$fxv#N')]`, and a further variable reads one field off that alias. Removing only the
  first leaves the rest dangling, so follow the chain to its end. A connector version read as
  `advancedConfig.?connectors.?version ?? <alias>.connectors.image.tag` becomes
  `advancedConfig.?connectors.?version ?? '<tag>'`, compiling to
  `[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'connectors'), 'version'), '<tag>')]`.

  This is a property of the Bicep source, not of the version value: every compile of a release whose Bicep loads a
  file regenerates the blob no matter what the loaded values are. Expect to redo this every release until upstream
  stops loading the file.

  Re-resolve every substituted literal on each release and never carry the previous one forward. Upstream derives
  these values from the loaded file, so a stale literal still compiles, still passes every test, and silently
  deploys the previous release's component. Read the value at the selected ref, report the old and new values, and
  confirm with the user.

  A substituted literal is often duplicated in the CLI's own source, because the same value is both compiled into
  the template and kept as a constant the CLI reads at runtime. Treat those as one derived value with two write
  sites: whenever you re-resolve the literal here, update the matching constant in the same change, from the same
  ref. Letting them diverge is easy to miss — each is individually valid, so nothing fails — and the result is a
  template that deploys one version while the CLI reasons about another. The constants section below gives the
  procedure for finding them at the current ref rather than a list to memorize; section 5 checks that each
  substituted literal is still current.
- **Settings that must not ship publicly.** Remove parameters, variables, resources, and configuration settings that
  the release owner confirms are not for public consumption, together with everything referencing them. Do not try
  to infer these from the Bicep alone — nothing in the source marks them, so they cannot be detected by inspection.
  Ask the user to confirm the list for each release, and report anything newly added since the previous release so
  they can rule on it. Removing a parameter without also removing its readers leaves a reference to a parameter that
  no longer exists: after deleting one, `grep` its name and remove every remaining occurrence, including entries in
  `defaultAioConfigurationSettings`.

  Confine that `grep` to the compiled closure — the two top-level templates and the files they transitively import.
  The deployment repository also contains sibling templates that this workflow never compiles, and a redacted name
  routinely appears in them. Editing those changes nothing in `template.py`, so leave them alone and say you did;
  a repository-wide `grep` invites a reviewer to "finish the job" in files that are out of scope.

Never satisfy an `$fxv#N` reference by keeping the blob. Before collapsing one, enumerate **every** reference to it
in the compiled JSON and confirm each one resolves to a value you can inline.

The number of readers is not fixed and must not be assumed. A release may read a single field off the loaded file or
several, and that count changes between releases: a later release can add reads of further fields to the same alias
with no other visible change. Enumerate the readers present at the selected ref and substitute all of them. Never
carry over the shape seen last release, and never stop at the first reader. Under-substituting is the dangerous
outcome, because a single leftover reference keeps the entire blob alive in the shipped template.

The substitution is provably behavior-preserving when, after it, **no** reference to the blob or to any variable that
merely aliases it survives anywhere in the compiled output. Confirm that by re-counting references in the recompiled
JSON rather than by reasoning about the source; section 5 asserts it independently. Variables at the end of a chain
do survive, holding the inlined literals, and are normally read by several resources — those are not the links being
deleted.

Stop and ask instead of redacting when a reference does not reduce to a concrete value: the loaded object is passed
somewhere whole, is indexed by an expression rather than a literal field name, or is used in a way whose result
depends on the file's structure rather than on one scalar within it.

### Constants and test expectations

Also update, from the same generated output:

- `EXTENSION_CONFIGS` in `azext_edge/tests/edge/orchestration/test_template_unit.py` from generated
  `variables.VERSIONS` and `variables.TRAINS`;
- `AIO_RELEASE` in `azext_edge/constants.py` from the supplied release moniker.

Then reconcile `azext_edge/edge/providers/orchestration/common.py`. It holds constants that restate values this
workflow already computes, so they go stale on exactly the releases where they matter.

Know precisely what the existing tests do and do not protect here, because the gap is where releases go wrong.
Some constants are guarded against the template — `test_opcua_connector_version_matches_template_tag` in
`azext_edge/tests/edge/orchestration/test_upgrade2_unit.py` asserts the connector constant equals the tag the
template stamps, so bumping one without the other fails. That guard is real, and it is not the one you need.
**Nothing compares either value against the source**, so when the source moves and neither is updated, both stay
equal to each other, the guard stays green, and the release ships a component tag the branch stopped specifying.
Only the section 5 literal-currency check sees this. Treat a passing test suite as no evidence that these
constants are current.

Do not work from a memorized list of names — the set changes as features are added. Find them at the current ref:
read the constants near the top-level assignments in that file and keep the ones whose value is a version or tag
that this release moved. Two independent origins exist, and each is checked differently:

- **Constants that restate a value in the generated template**, such as a minimum instance version gating an
  upgrade behavior. These must equal the corresponding generated value, normally `variables.VERSIONS.iotOperations`.
  Compare against the freshly generated dictionary, not against the previous `template.py`.
- **Constants that restate a literal substituted during redaction**, such as a component image tag. These must equal
  the literal actually written into the template in this run, which is the coupling the redaction section describes.

For each, print the current value, the value derived from the selected ref, and the origin, then ask the user to
confirm before editing. Propose; never silently rewrite. When a constant's value cannot be tied to a generated value
or a substituted literal, leave it alone and say so — not every constant in that file tracks the release.

Report any constant that was already stale before this run as a pre-existing drift, separately from the changes this
release requires, so the user can decide whether fixing it belongs in this change.

When the instance template adds or removes a top-level entry under `resources`, three test files assert that resource
key set and all three must end green:

- `EXPECTED_INSTANCE_RESOURCE_KEYS` in `azext_edge/tests/edge/orchestration/test_template_unit.py`. This is the
  canonical list; update it first.
- the `expected_resources` sets for the `RESOURCES` and `None` phases in the `test_instance_phases` parametrize in
  `azext_edge/tests/edge/orchestration/test_targets_unit.py`. These are hand-maintained and must be updated too.
  Updating only `test_template_unit.py` leaves exactly these two parameter cases failing.
- `resource_keys` in `get_expected_keys_for` in `azext_edge/tests/edge/orchestration/test_work_unit.py`. Inspect this
  one before editing. Where it is assigned from `EXPECTED_INSTANCE_RESOURCE_KEYS` it tracks the canonical list
  automatically and needs no change. Where it instead builds its own literal set — historically
  `instance_keys.union({...})` — do not just add the new key to that literal. Replace the whole expression with
  `set(EXPECTED_INSTANCE_RESOURCE_KEYS)`, importing that name alongside the existing
  `EXPECTED_EXTENSION_RESOURCE_KEYS` import, so the file derives from the canonical list and stops needing a manual
  edit every release. Adding the key to the literal is also correct and passes, but leaves the duplicate in place to
  go stale again next release; this file is the one that most often breaks, so remove the duplication instead.

Determine phase membership deterministically rather than guessing. `get_ops_instance_template` in
`azext_edge/edge/providers/orchestration/targets.py` treats the `EXT` and `INSTANCE` phases as allowlists driven by
`PHASE_KEY_MAP`: `del_if_not_in` removes every resource not named there. The `RESOURCES` and `None` phases perform no
deletion and therefore carry the full blueprint. So a new resource key that is not added to `PHASE_KEY_MAP` belongs
only to the `RESOURCES` and `None` sets.

A release that changes `PHASE_KEY_MAP` itself is a separate case, and two further hand-maintained places must follow
it: the `EXT` and `INSTANCE` parameter cases in `test_targets_unit.py`, and the `ext_keys` and `instance_keys`
literals in `get_expected_keys_for` in `test_work_unit.py`. Neither is affected by a `resources`-only change.

Never treat `test_template_unit.py` passing as evidence the sync is complete; it asserts only the canonical list,
which the other files consume or duplicate independently.

When adding a key to a set that already lists related keys, insert it in the same position in every set rather than
appending it to one and inserting it in another. Set literals are order-insensitive to Python, so this changes
nothing at runtime, but a consistent position keeps the review diff to one added line per set.

#### Release train

`variables.TRAINS` is generated from the source like any other value, and for a new release moniker it is taken as
generated. It is, however, the one generated value the CLI deliberately ships differently from upstream: a release
branch commonly stays on a pre-release train while the CLI publishes that same release as generally available. That
promotion is a CLI-side decision recorded only in this repository — nothing in the source branch reflects it, so
regeneration reverts it.

When section 1 identified the run as a re-sync, compare each generated train against the train currently embedded in
`template.py`. If any differs, stop and ask which to ship rather than copying. Both directions are plausible:
upstream may have genuinely advanced, or the embedded value may be a promotion that must be preserved. Copying
blindly can demote an already published template to a pre-release train, and because the result is internally
consistent, every later check in this workflow still passes.

If the user keeps the embedded train, apply it as a **source edit**: change the corresponding entry in the `TRAINS`
declaration in the exported Bicep and recompile through section 2, exactly as step 1 of this section requires. Do not
patch the compiled JSON or the embedded dictionary — the template hash would then describe content that was never
compiled, and section 5's equality check would fail with no honest way to satisfy it. Record the override in the
section 6 release-policy overrides with the upstream value, the shipped value, and the decision.

Do not hard-code train names or assume an ordering between them: read the names present in the generated output, and
ask when their relative maturity is not obvious.

#### CLI version

Apply this CLI `VERSION` policy, computing every change from semantic version components, never string or float
arithmetic. Never reuse an already published version; verify against `gh release list` before proposing one. That
check sees only published releases, and prerelease versions are not published — so it confirms a stable version is
free but can never rule out reuse of a prerelease. For those, reason from `constants.py` history instead.

- **Re-sync of an already generated release** — section 1 found `AIO_RELEASE` already equal to the supplied moniker.
  When no train being shipped has changed — including when an upstream difference was overridden back to the
  embedded value above — preserve the current `VERSION` and propose no change. This takes precedence over the rules
  below, which describe how a release *advances*: applying them to a moniker that has already been generated
  advances the version a second time for the same release, so repeating a run keeps producing a new version and the
  workflow stops being idempotent. If that release is already published and its templates genuinely must change,
  that is a patch decision — ask for an explicit version rather than deriving one.

  When a re-sync *does* ship a changed train, this rule does not apply: the release has moved on, and the
  train-dependent rules below describe that move. Apply them to the current `VERSION`. A re-sync that adopts a more
  mature train is the ordinary promotion case — a prerelease version on a now-stable train should be promoted, not
  preserved. If the train moved the other way, or the correct result is otherwise ambiguous, ask for an explicit
  version.
- **Any `integration` train: bump the minor of the last stable version and start its `a1` prerelease.**
  `2.7.0` becomes `2.8.0a1`, `2.8.0` becomes `2.9.0a1`. Derive the base from the last stable version, not from the
  current value, so an integration release never ships under a stable number.

  When `VERSION` already sits on that base, the base is in use and this rule alone cannot settle the result: the
  repository has shipped template-sync releases that advanced the prerelease counter and others that left `VERSION`
  untouched. The discriminator is not derivable — a sync has kept a prerelease version that had already been built
  and published to the private channel, so "already built" does not decide it either. Ask for an explicit version,
  and make the ask useful: give the current value, the counter it would advance to, whether a release build has
  already run at the current value, and both precedents. Never silently propose the unchanged value as if the rule
  had decided it — that ships two AIO releases under one CLI version, and the `gh release list` check above cannot
  catch it. When the answer is genuinely a toss-up, lean toward advancing: an unnecessary advance costs one unused
  integer, while reusing a consumed version puts two different artifacts under one version, silently.
- `stable` train with a prerelease version: promote to its base version, for example `2.8.0a2` to `2.8.0`.
- `stable` train with an already stable version: ask for an explicit version because the AIO release moniker does not
  establish whether the CLI version should remain unchanged or advance.

Only perform a bare next-minor bump to a stable version (`2.8.0` to `2.9.0`) when explicitly requested.

Print all proposed constant changes before editing.

## 5. Validate

After editing:

1. Run these structural checks. They are written out in full so validation does not depend on remembering them, and
   are deliberately limited to the assertions a reviewer cannot make by reading the diff. Run them with the working
   directory set to the **CLI repository root**: every repository path below is relative, so running from the step 2
   scratch directory silently reads nothing. Substitute the two step 2 paths at the top; everything else is derived.

   Three assertions, each catching a defect no other step catches:

   - **Equality with the fresh compile** — catches a hand-edited dictionary, and proves
     `metadata._generator.templateHash` came from a real compile of the shipped content rather than being carried
     forward. Never satisfy it by copying a hash across.
   - **No surviving `$fxv`** — catches a loaded-file reader that was missed, which leaks the whole file into
     shipped output. Equality cannot catch this, because a skipped redaction is present on both sides.
   - **Each substituted literal still matches the source** — catches a pin that went stale while the source moved
     on. Equality cannot catch this either, and neither can the unit tests, for the same reason.

   The unit tests are not a substitute for any of this: a template that still embeds the loaded-file blob, pins a
   stale literal, and carries a hash forward passes the full orchestration suite unchanged.

   Nothing here checks for a reference to a parameter or variable that no longer exists. It does not need to.
   Redactions are source edits that are then recompiled, and `az bicep build` rejects a surviving reader outright
   with `BCP057: The name "<x>" does not exist in the current context`. That guarantee holds only while redactions
   stay source edits — if you ever find yourself editing compiled JSON directly, you have left the workflow, and
   this is one of the protections you have given up.

   ```python
   import ast, json, pathlib, re, yaml

   TEMP = pathlib.Path("<temp>")              # step 2 compile output
   SRC = pathlib.Path("<exported-source>")    # step 2 export

   gen = {n: json.loads((TEMP / f"opt_{n.lower()}.json").read_text()) for n in ("ENABLEMENT", "INSTANCE")}
   tpl = pathlib.Path("azext_edge/edge/providers/orchestration/template.py")
   emb = {}
   for node in ast.parse(tpl.read_text()).body:  # parse, never import
       if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "").startswith("TEMPLATE_BLUEPRINT_"):
           kw = {k.arg: k.value for k in node.value.keywords}
           emb[node.targets[0].id.replace("TEMPLATE_BLUEPRINT_", "")] = ast.literal_eval(kw["content"])

   fails = []
   def check(ok, msg):
       print(("  ok   " if ok else "  FAIL ") + msg)
       fails.append(msg) if not ok else None

   def strings(o):
       if isinstance(o, dict):
           for k, v in o.items():
               yield str(k)
               yield from strings(v)
       elif isinstance(o, list):
           for i in o:
               yield from strings(i)
       elif isinstance(o, str):
           yield o

   for name, content in emb.items():
       check(content == gen.get(name), f"{name} equals the freshly compiled dictionary")
       check(not any("$fxv" in s for s in strings(content)), f"{name} has no $fxv artifact")

   # every literal substituted for a value that used to be read from the loaded file is still current
   unred = TEMP / "opt_instance_unredacted.json"
   if unred.exists():
       raw = json.loads(unred.read_text())
       vals = yaml.safe_load((SRC / "AioExtension/helm/aio/values.yaml").read_text())
       shipped = set(strings(emb["INSTANCE"]))
       aliases = [k for k, v in raw.get("variables", {}).items()
                  if isinstance(v, str) and re.fullmatch(r"\[variables\('\$fxv#\d+'\)\]", v)]
       reads = 0
       for alias in aliases:
           for dotted in {m for s in strings(raw)
                          for m in re.findall(re.escape(alias) + r"'\)((?:\.[A-Za-z0-9_]+)+)", s)}:
               reads += 1
               node = vals
               for part in dotted.strip(".").split("."):
                   node = node.get(part) if isinstance(node, dict) else None
               lit = str(node)
               # match as a quoted token inside an ARM expression, or as a whole string; a bare substring
               # test passes against any short value and silently stops checking anything
               check(node is not None and any(s == lit or f"'{lit}'" in s for s in shipped),
                     f"literal substituted for {alias}{dotted} is current ({node})")
       # the count is the point: it is how many reads this release actually had, not how many it had last time
       print(f"  INFO {reads} substituted literal(s) across {len(aliases)} loaded-file alias(es)")
   else:
       print("  INFO no opt_instance_unredacted.json - substituted-literal currency NOT checked. Correct only if "
             "this release applied no redaction; otherwise section 2 kept it under the wrong name - fix and rerun")

   if fails:
       raise SystemExit(f"{len(fails)} check(s) failed")  # a string argument would exit 1 even on success
   print("all checks passed")
   ```

   Treat any `FAIL` as blocking. Do not weaken a check to make it pass. Investigate every `INFO`: those are the
   places the checks cannot decide alone. In particular, compare the reported count of substituted literals against
   the number of readers you actually redacted in section 4. The count is read from the pre-redaction compile, so it
   is the ground-truth number of reads at the selected ref and does not move with your edits: a reported count
   higher than the number you redacted means a reader was missed, which is the failure the `$fxv` check is there to
   catch. Any mismatch in either direction means the two disagree about this release and must be resolved.

   The block deliberately checks only what cannot be established by reading. Confirm the rest by inspection:

   - **The generated assignments contain no implicitly concatenated strings.** `repr()` plus Black never emits them.
     A diff far larger than this release warrants is the symptom; look at the diff rather than the file.
   - **`AIO_RELEASE` equals `release` in `release.json` at the selected ref.** Section 1 established this before any
     edits; confirm the edit preserved it.
   - **`VERSION` is not already published.** Check the proposed value against `gh release list` for this repository,
     with the limits described in section 4: it decides only stable versions, it cannot see prerelease reuse, and it
     is not a failure when a re-sync deliberately preserves an already published version.
   - **The resource key expectations are complete.** The test command in item 2 below runs the files that
     assert them, so let those tests decide instead of re-deriving the sets here. They fail with the exact missing
     or extra key.
   - **Each release-tracking constant in `common.py` matches its origin.** Section 4 derived these; confirm the file
     now agrees with the generated template and with the literals substituted during redaction.
2. Run:

   ```shell
   python -m pytest -q \
     azext_edge/tests/edge/orchestration/test_template_unit.py \
     azext_edge/tests/edge/orchestration/test_targets_unit.py \
     azext_edge/tests/edge/orchestration/test_work_unit.py \
     azext_edge/tests/edge/orchestration/test_upgrade2_unit.py
   python -m flake8 \
     azext_edge/edge/providers/orchestration/template.py \
     azext_edge/edge/providers/orchestration/common.py \
     azext_edge/tests/edge/orchestration/test_template_unit.py \
     azext_edge/tests/edge/orchestration/test_targets_unit.py \
     azext_edge/tests/edge/orchestration/test_work_unit.py \
     azext_edge/constants.py
   git diff --check
   ```

   Run every file listed even when only `test_template_unit.py` was edited. `test_template_unit.py` alone passing
   is not evidence the sync is complete: `test_targets_unit.py` and `test_work_unit.py` assert the instance
   resource key set independently, and `test_upgrade2_unit.py` holds the only mechanical guard tying a constant
   reconciled in section 4 to the tag the template stamps — a redaction literal and its matching constant can
   drift apart with every other check still green.

   All of them must be green before the sync is reported as successful. A failure of the form
   `assert N == M` on `len(template["resources"])`, or a set-equality failure naming an extra or missing resource,
   means the step 4 key-set update is incomplete: apply it, then re-run. A failure comparing a constant against a
   template tag means the section 4 constant reconciliation is incomplete. Do not report success, hand the branch
   back, or move on to step 6 while any of them fails.

3. Show the final diff summary, detected versions/trains, and behavioral changes.
4. Print the Bicep sources the templates were generated from and a ready-to-run verification block, so a developer
   can confirm the result independently. Give the resolved commit for each file, not just the branch. Because step 2
   deletes its temporary files, make the block self-contained: recompile, then inspect. Substitute the real exported
   path and file names rather than printing placeholders.

   ```shell
   # Run from a scratch directory. `az bicep build --outfile <relative-path>` resolves the output path against the
   # current working directory, not against --file, so running this inside the source repository silently drops
   # build artifacts into a worktree this skill must not modify. Use any scratch directory, or absolute --outfile
   # paths; the path below is only an example.
   mkdir -p /tmp/aio-verify && cd /tmp/aio-verify

   # Sources
   #   instance:   <source-repo>/Deployment/azure-iot-operations-instance.bicep   @ <instance-commit>
   #   enablement: <source-repo>/Deployment/azure-iot-operations-enablement.bicep @ <enablement-commit>
   #   values:     <source-repo>/AioExtension/helm/aio/values.yaml

   az bicep build --file <source-repo>/Deployment/azure-iot-operations-instance.bicep   --outfile temp-instance.json
   az bicep build --file <source-repo>/Deployment/azure-iot-operations-enablement.bicep --outfile temp-enablement.json

   echo "===== INSTANCE (azure-iot-operations-instance.bicep) ====="
   jq '{ _generator: .metadata._generator, VERSIONS: .variables.VERSIONS, TRAINS: .variables.TRAINS }' temp-instance.json

  # ---- OPC UA connectors image tag -> common.OPCUA_CONNECTOR_VERSION ----
  # Key-agnostic: the tag lives under a Bicep-mangled loadJsonContent variable ($fxv#N),
  # so search all objects for connectors.image.tag instead of hard-coding the key name.
  echo
  echo "===== OPC UA CONNECTOR VERSION (-> OPCUA_CONNECTOR_VERSION in common.py) ====="
  jq -r 'first(.. | objects | select(.connectors?.image?.tag) | .connectors.image.tag) // "NOT FOUND"' temp-instance.json

   echo
   echo "===== ENABLEMENT (azure-iot-operations-enablement.bicep) ====="
   jq '{ _generator: .metadata._generator, VERSIONS: .variables.VERSIONS, TRAINS: .variables.TRAINS }' temp-enablement.json
   ```

   State which values the developer should expect to match `template.py`, and call out that a redacted template's
   `templateHash` matches only a compile of the **redacted** source, so the command above reproduces the instance
   hash only when the step 4 source edits are re-applied. Report the unredacted hash alongside it to avoid a false
   alarm.

   Treat the hash as a checksum on the source edits, because that is what it is. When the ref is right and the
   redactions are exactly right, it reproduces **exactly** — a correct run regenerates a previously shipped
   template bit for bit, hash included. So a hash mismatch is a signal worth chasing, not noise to wave through:
   it usually means the selected ref is not the one the shipped template came from, or a redaction differs.

   There are two situations where a mismatch is expected and benign, and it is worth knowing which one you are in:

   - The optimizer strips content the compiler had already hashed — parameter descriptions, and `allowedValues` on
     some parameters. Two sources differing only inside a stripped region produce an identical `template.py` under
     different hashes, so a hash is not re-derivable from `template.py` alone; you need the source.
   - The shipped template was **hand-patched after it was generated**, so its hash describes the older content and
     no longer matches the file it sits in. Section 4 explains why that must never be how a change is made.

### What validation cannot cover

The section 5 checks make the mechanical parts of this workflow repeatable, but they prove internal consistency, not
correctness of intent. These remain judgment, and a clean run is not a substitute for them:

- **Which settings must not ship publicly.** Nothing in the source marks them. The checks can only confirm that a
  removal already decided on was applied completely, never that the right things were removed. Always confirm the
  list with the release owner.
- **Whether an upstream change is safe to adopt.** Section 3 exists because a version bump can carry configuration
  changes. The checks compare what was generated against what was embedded; they cannot tell you that a changed
  default is acceptable.
- **Partial resource key expectations.** A hand-maintained set that holds most of the blueprint must be complete,
  but legitimate per-phase subsets exist and cannot be told apart from a stale partial by inspection. The three test
  files settle it; never skip them. The durable fix for a large hand-maintained set is to derive it from
  `EXPECTED_INSTANCE_RESOURCE_KEYS` so it tracks the canonical list automatically.
- **What a newly added resource requires elsewhere in the CLI.** Getting a new top-level `resources` entry into every
  test expectation makes the suite green, but the resource is also *handled* by code those tests do not exercise.
  A new child of the instance is the case that has actually broken a release: the CLI rewrites instance-child
  resource names when the user supplies an instance name, and that rewriting is an explicit per-resource list in
  `azext_edge/edge/providers/orchestration/targets.py`, not a rule derived from the template. A child missing from
  that list keeps its generated name, so the deployment references a parent that does not exist. Nothing local
  catches it: every check here and the whole unit suite pass, and it fails only against a live cluster.

  So whenever the generated instance template gains a resource whose type is a child of the instance, report it as
  requiring follow-up outside this workflow's scope and name that list as the place to look. Decide this from the
  resource's type in the freshly generated output, not from a remembered list of children — the point is to catch
  the child that has not been seen before. The same trigger may also require the upgrade path to account for the new
  resource on instances created before it existed. Flag both; leave the decision to the owners of that code.
- **Anything asserted only outside these files.** Section 5 checks what it can reach; the full suite may still fail
  for unrelated reasons.

Report a clean run as what it is — every mechanical check passed — rather than as proof the release is
correct.

## 6. Generate the IoT Operations versions wiki payload

After all template edits and validation succeed, print a ready-to-paste Markdown update for the
[IoT Operations versions wiki](https://github.com/Azure/azure-iot-ops-cli-extension/wiki/IoT-Operations-versions).
Do not edit or push the wiki.

Print both:

1. the new row for the appropriate **Version Matrix by AIO Release** table;
2. the complete detailed release section.

### Collect release values

Use the validated post-update embedded templates for release-facing AIO and dependency extension values:

- AIO version:
  `TEMPLATE_BLUEPRINT_INSTANCE.content.variables.VERSIONS.iotOperations`;
- AIO train:
  `TEMPLATE_BLUEPRINT_INSTANCE.content.variables.TRAINS.iotOperations`;
- Cert Manager version/train:
  `TEMPLATE_BLUEPRINT_ENABLEMENT.content.variables.VERSIONS.certManager` and
  `TEMPLATE_BLUEPRINT_ENABLEMENT.content.variables.TRAINS.certManager`;
- Key Vault Secret Store version/train:
  `TEMPLATE_BLUEPRINT_ENABLEMENT.content.variables.VERSIONS.secretStore` and
  `TEMPLATE_BLUEPRINT_ENABLEMENT.content.variables.TRAINS.secretStore`;
- compatible CLI version: final `VERSION` in `azext_edge/constants.py`.

Cross-check embedded template values against the generated ARM dictionaries. If a final embedded value intentionally
differs from the generated upstream value because of release policy, keep the final embedded value in the wiki
payload and prominently report the discrepancy.

Read core component versions from `AioExtension/helm/aio/values.yaml` exported from the same selected ref:

| Wiki component | YAML path |
| --- | --- |
| Mqtt Broker | `mqttBroker.image.tag` |
| Data Flows | `dataFlows.image.tag` |
| Connectors | `connectors.image.tag` |
| Akri | `akri.image.tag` |
| Schema Registry | `schemaRegistry.image.tag` |
| Device Registry | `adr.image.tag` |
| AIO Observability | `aioObservabilityOperator.image.tag` |

Parse YAML structurally with `yaml.safe_load`; do not select version-like strings with broad grep. Require every path
to resolve to a non-empty scalar. Use `yaml.compose` node marks, or another path-aware YAML parser, to obtain the exact
source line for each value.

Derive the AIO series from the semantic AIO version by replacing the patch component with `x`, so
`<major>.<minor>.<patch>` becomes `<major>.<minor>.x`. Do not use the release moniker to infer the product version,
and do not assume the series is unchanged from the previous release — a release can move the product's minor
version, which changes both the series and the name of the source release branch.

Construct these proposed public links:

- AIO release:
  `https://github.com/Azure/azure-iot-operations/releases/tag/v<AIO_VERSION>`;
- CLI release:
  `https://github.com/Azure/azure-iot-ops-cli-extension/releases/tag/v<CLI_VERSION>`.

The links may not exist yet during release preparation; label them as proposed in the surrounding report.

When the final `VERSION` is a prerelease, the CLI release link and the compatible-CLI-version row will never
resolve as generated: prerelease versions are not published as GitHub releases and the wiki carries only stable CLI
versions. Print the payload as a draft, and say that its CLI version and CLI release link are placeholders to be
replaced when the release is promoted to a stable version.

### Manual placeholders

Do not guess information that is not authoritative in the selected templates or release metadata. Use these exact,
visible placeholders:

- `<RELEASE_DATE>`;
- `<UPGRADE_FROM_AIO>`;
- `<CLI_RELEASE_DATE>`.

### Print the version-matrix row

Print:

```markdown
| [<RELEASE_MONIKER>](#<RELEASE_MONIKER>) | <RELEASE_DATE> | <AIO_VERSION> | <UPGRADE_FROM_AIO> | <CLI_VERSION> |
```

Also state which existing series table (`AIO <major>.<minor>.x Series`) should receive the row.

### Print the detailed release section

Match the wiki's existing format:

```markdown
### [<RELEASE_MONIKER>](https://github.com/Azure/azure-iot-operations/releases/tag/v<AIO_VERSION>)

**AIO Version:** <AIO_VERSION> **|** **Release Date:** <RELEASE_DATE> **|** **Release Train:** <AIO_TRAIN>

⏫ **Upgrade From (AIO):** <UPGRADE_FROM_AIO>

**Core Components**
| Component | Version |
|-----------|---------|
| Mqtt Broker | <MQTT_BROKER_VERSION> |
| Data Flows | <DATA_FLOWS_VERSION> |
| Connectors | <CONNECTORS_VERSION> |
| Akri | <AKRI_VERSION> |
| Schema Registry | <SCHEMA_REGISTRY_VERSION> |
| Device Registry | <DEVICE_REGISTRY_VERSION> |
| AIO Observability | <AIO_OBSERVABILITY_VERSION> |

**Dependency Extensions**
| Extension | Version | Train |
|-----------|---------|-------|
| Cert Manager | <CERT_MANAGER_VERSION> | <CERT_MANAGER_TRAIN> |
| Key Vault Secret Store | <SECRET_STORE_VERSION> | <SECRET_STORE_TRAIN> |

**Compatible CLI Versions**
| CLI Version | Release Date | Notes |
|-------------|--------------|-------|
| <CLI_VERSION> | <CLI_RELEASE_DATE> | [Release](https://github.com/Azure/azure-iot-ops-cli-extension/releases/tag/v<CLI_VERSION>) |
```

### Print source provenance

After the paste-ready Markdown, print a separate **Source provenance** table. This table is for review and does not
need to be pasted into the wiki.

Include one row for every populated field:

```markdown
| Field | Value | Source |
|-------|-------|--------|
| AIO version | `<AIO_VERSION>` | `<selected-ref>:Deployment/azure-iot-operations-instance.bicep:<line>`; compiled path `variables.VERSIONS.iotOperations`; final `azext_edge/edge/providers/orchestration/template.py:<line>` |
```

Source requirements:

- identify the selected ref and resolved commit;
- calculate line numbers from files exported from that ref, not the current source worktree;
- cite `Deployment/release.json:<line>` for the release moniker;
- cite the source Bicep declaration line, compiled JSON object path, and final `template.py:<line>` for AIO and
  dependency extension values;
- cite `AioExtension/helm/aio/values.yaml:<line>` for each core component;
- cite `azext_edge/constants.py:<line>` for the CLI version;
- use Python AST node positions to locate final Python values instead of broad text matching;
- fail if a source path is absent, duplicated ambiguously, or cannot be tied to an exact line.

When generated upstream and final embedded values differ, add a **Release-policy overrides** section showing:

- field;
- upstream value and source;
- final embedded value and source;
- the user-approved policy decision.

## 7. Hand off the extension index update

Finish by printing — never running — the commands that prepare this release's entry in the public Azure CLI
extension index. Until that index change is merged, `az extension add --name azure-iot-ops` cannot resolve the new
version, so the release is not yet consumable even after it is tagged. The commands only edit a local file and stage
a branch; the release becomes consumable when the resulting pull request is merged.

Print this hand-off on every successful run whose final `VERSION` is stable, as a forward reference.

A prerelease `VERSION` never reaches this step. Those builds are not published as a GitHub release and never enter
the public index, so no wheel URL will ever resolve for them. On a prerelease run, say that instead of printing the
commands, and note that the public index step applies only once the release is promoted to a stable version.

### State that it is not actionable yet

This workflow prepares templates *before* the release exists. The wheel is built and attached to the GitHub release
later. Say so plainly: the URL below returns 404 until the CLI release PR is merged and the GitHub release is
published, and the user should return to these commands at that point. Do not present the command as runnable now,
and do not check whether the asset exists.

Note also that this repository automates only the **private** index, in
`.github/workflows/update_private_index.yml`. The public index PR is the manual counterpart and has no automation.

### Derive the wheel URL

Do not ask for the URL and do not type a version by hand. Use the final `VERSION` from `azext_edge/constants.py` —
the same value section 6 collects as the compatible CLI version — and substitute it into:

```text
https://github.com/Azure/azure-iot-ops-cli-extension/releases/download/v<CLI_VERSION>/azure_iot_ops-<CLI_VERSION>-py3-none-any.whl
```

The tag carries a leading `v`; the wheel filename does not. Substitute the same version into both.

### Print the commands

Print the already-configured path first. It is the common case, because `azdev` and its virtualenv normally survive
from the previous release. Each path must be complete on its own, so include the `cd` and the activation rather than
describing them in prose.

```shell
cd <path-to-existing-azure-cli-extensions-clone>
source <path-to-existing-azdev-venv>/bin/activate

git switch main && git pull
git switch -c <alias>/azure-iot-ops-cli-<CLI_VERSION>

azdev extension update-index \
  https://github.com/Azure/azure-iot-ops-cli-extension/releases/download/v<CLI_VERSION>/azure_iot_ops-<CLI_VERSION>-py3-none-any.whl

git status
```

Then print the first-time setup, needed only on a machine that has never done this:

```shell
git clone https://github.com/Azure/azure-cli-extensions.git
cd azure-cli-extensions

python -m venv <venv-name>
source <venv-name>/bin/activate
pip install azdev

# Register this clone as the extensions repo, and install the CLI from the edge build
azdev setup -c EDGE -r .

# Use this form instead when a local azure-cli clone already exists.
# Keep -r . either way: -c selects the CLI, -r registers the extensions repo, and
# update-index fails to find index.json if the extensions repo was never registered.
azdev setup -c <path-to-azure-cli-clone> -r .
```

State that the fresh-machine path then continues with the commands from the first block, starting at
`git switch main`, without repeating the clone or the setup.

Use a placeholder for the branch prefix rather than any specific username.

### Explain what to expect

- `azdev extension update-index` rewrites `src/index.json` in place; it does not commit or open a PR.
- `git status` after the command shows exactly which files changed, which the user should review before committing.
- The resulting PR follows the convention `[Release] Update index.json for extension [azure-iot-ops-<CLI_VERSION>]`.
- Point at prior examples with a release-agnostic search rather than naming one PR:
  `https://github.com/Azure/azure-cli-extensions/pulls?q=is%3Apr+azure-iot-ops+in%3Atitle`.

Everything in this section is an output artifact. Print the commands together with the surrounding explanation, and
never execute any of them: do not clone `azure-cli-extensions`, create a virtualenv, install `azdev`, create a
branch, run `azdev`, or open the index pull request.

Never commit, push, publish, switch the CLI branch, trigger a release workflow, or modify files outside the declared
scope.
