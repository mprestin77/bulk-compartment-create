# OCI Compartment SDK Scripts

This directory contains Python scripts that create and delete OCI compartments in this layout:

- `/Prod/Team1` ... `/Prod/TeamN`
- `/Integ/Team1` ... `/Integ/TeamN`
- `/Dev/Team1` ... `/Dev/TeamN`

The scripts work with these top-level environment compartments:

- `Prod`
- `Integ`
- `Dev`

## Files

- `create-compartments-sdk.py` - create or reuse environment compartments and create child compartments in parallel
- `delete-compartments-sdk.py` - delete matching child compartments in parallel and optionally delete parent compartments

## Requirements

- Python 3
- OCI Python SDK
- OCI config file by default at `~/.oci/config`, or an OCI instance with instance principal enabled
- IAM permissions to inspect, create, and delete compartments in the tenancy

## IAM Policy

The OCI user group running these scripts should have:

```text
Allow group <group-name> to manage compartments in tenancy
```

## Authentication

By default, both scripts use the OCI config file.

To use instance principal authentication:

```bash
python3 create-compartments-sdk.py --count 100 --instance-principal
python3 delete-compartments-sdk.py --count 100 --instance-principal
```

## Create Script

`create-compartments-sdk.py` creates or reuses `Prod`, `Integ`, and `Dev`, then creates missing child compartments such as `Team1`, `Team2`, and so on.

Main options:

- `--count` - required; number of Team compartments to create under each environment
- `--envs` - comma-separated parent compartments; default is `Prod,Integ,Dev`
- `--team-prefix` - child name prefix; default is `Team`
- `--start-index` - starting number for generated child names; default is `1`
- `--workers` - number of parallel workers; default is `10`
- `--wait` - wait until each created child compartment becomes `ACTIVE`
- `--dry-run` - show what would be created without creating anything
- `--region` - override region
- `--profile` - OCI config profile; default is `DEFAULT`
- `--config-file` - OCI config file path

Examples:

```bash
python3 create-compartments-sdk.py --count 100 --dry-run
python3 create-compartments-sdk.py --count 100
python3 create-compartments-sdk.py --count 100 --workers 20
python3 create-compartments-sdk.py --count 100 --workers 10 --wait
python3 create-compartments-sdk.py --count 50 --team-prefix AppTeam --start-index 101
```

Create behavior:

- existing parent compartments are reused
- existing child compartments are skipped
- missing child compartments are created in parallel
- parent compartments are always waited on until they become `ACTIVE`
- child compartments are waited on only when `--wait` is used

## Delete Script

`delete-compartments-sdk.py` deletes matching child compartments such as `Team1`, `Team2`, and so on under `Prod`, `Integ`, and `Dev`.

By default, it deletes only child compartments. It deletes parent compartments only when `--delete-parents` is specified.

Main options:

- `--count` - required; number of Team compartments per environment to target for deletion
- `--envs` - comma-separated parent compartments; default is `Prod,Integ,Dev`
- `--team-prefix` - child name prefix; default is `Team`
- `--start-index` - starting number for generated child names; default is `1`
- `--workers` - number of parallel workers; default is `10`
- `--wait` - wait until each targeted child compartment reaches `DELETED`
- `--delete-parents` - delete parent compartments after child compartments are gone
- `--dry-run` - show what would be deleted without deleting anything
- `--region` - override region
- `--profile` - OCI config profile; default is `DEFAULT`
- `--config-file` - OCI config file path

Examples:

```bash
python3 delete-compartments-sdk.py --count 100 --dry-run
python3 delete-compartments-sdk.py --count 100 --workers 10
python3 delete-compartments-sdk.py --count 100 --workers 10 --wait
python3 delete-compartments-sdk.py --count 100 --workers 10 --wait --delete-parents
```

Delete behavior:

- matching child compartments are deleted in parallel
- missing child compartments are skipped
- parent compartments are not deleted unless `--delete-parents` is specified
- `--delete-parents` should be used together with `--wait`
- `--wait` means wait for lifecycle state `DELETED`, not for the 90-day retention period to expire

## Parallelism

Both scripts use a thread pool for child compartment operations.

- default worker count is `10`
- increase parallelism with `--workers`
- OCI may still throttle requests even if you increase the worker count

## Notes

- `Team1` can exist under multiple parents, so `/Prod/Team1`, `/Integ/Team1`, and `/Dev/Team1` are all valid
- compartment create and delete operations are asynchronous in OCI
- for create operations, `--wait` means wait for `ACTIVE`
- for delete operations, `--wait` means wait for `DELETED`
