# Ops release pipeline

Use [Ops release pipeline 165](https://dev.azure.com/azureiotdevxp/aziotcli/_build?definitionId=165)
to build, test and optionally publish one `azure-iot-ops` wheel.

> **Not live yet:** Upload wheel only, Draft and Release need the approved
> automation PR merged and pipeline 165's default branch set to `dev`.

## Modes

Every mode first runs the same gates: build, unit tests, security scans,
command lint, index compatibility and integration tests. You do not need a
separate Validate run before uploading or releasing.

| Mode | Result | Approval |
| --- | --- | --- |
| **Validate** (default) | Gates only. Not a dry run: integration creates real Azure test resources. Publishes nothing. | None |
| **Upload wheel only** | Uploads only the verified wheel to `https://azedgecli.blob.core.windows.net/drop/{wheel filename}`. No GitHub release, draft, tag, index PR or GitHub token. | None |
| **Draft** | Stages the wheel and SBOM in an unpublished GitHub draft release. | Required |
| **Release** | Publishes the GitHub release and tag. | Required |

## Run it

1. Open pipeline **165** and select **Run pipeline**.
2. **Branch/tag** (automation): `dev`.
3. **Release branch** (product code): keep the default `dev`. Upload, Draft
   and Release reject any other automation or product branch.
4. **Mode**: choose from the table above.
5. **Region (Public cloud only)**: one region; default West US 2.
6. **Skip integration tests**: leave unchecked. Checking it is an explicit
   waiver that skips only integration; it is recorded in the candidate and
   receipt.
7. **Create index PR**: leave unchecked unless you chose **Release** and want
   an Azure CLI extensions index PR. Other modes reject it. The index team
   reviews and merges that PR; the pipeline never merges it.
8. Select **Run**.
9. Draft/Release only: when the publish stage waits, the configured approver
   approves the check on protected variable group `aziotops_release_publish`.
   The requester may self-approve. Upload never waits for approval.
10. When the run finishes, open its **Artifacts** and download its logs (below).

Integration queues pipeline **164** child runs for every default release
scenario on Stable and Preview with Python 3.13, using Public test connection
`sc-iot-ops-cli-public-it`. Test resources must pass cleanup; logs are in
those child runs.

## Find the output

| Artifact | Contents |
| --- | --- |
| `release-candidate` | The wheel, `SBOM.zip` and `candidate.json` (commits, SHA-256s, region, any waiver). |
| `release-tooling` | The frozen publication script. |
| `release-security-<attempt>` | Security scan evidence. |
| `release-index-compatibility-<attempt>` | Index compatibility report. |
| `release-integration-<cohort>-<attempt>` | The pipeline 164 child run for that cohort. |

For Upload, Draft or Release, choose **... > Download logs** on the run to get
`release.json`, attached by **Retain publication receipt in task logs**. Release
jobs publish no pipeline artifacts. The Upload receipt records the blob URL,
SHA-256, length, candidate provenance and status `uploaded` or `already-present`.

## Upload rules and retries

- Upload never overwrites. If the blob already exists with identical bytes
  (same SHA-256 and length), the run succeeds as `already-present`.
  Different bytes fail the run.
- After fixing an authentication or network failure, rerun the failed
  **Upload** job. It reuses the same verified candidate.

## Credentials

- Upload uses WIF service connection `sc-cli-release-storage` (create/read on
  `azedgecli/drop`). It has no approval check, SAS or stored key.
- GitHub credentials live only in `aziotops_release_publish`, which only
  Draft and Release use.

See [Contributing](../CONTRIBUTING.md) and
[integration tests](integration-tests.md) for development and test setup.
