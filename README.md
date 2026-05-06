# bulk-compartment-create

This repository contains example tooling for creating and deleting large numbers of OCI compartments.

It is organized into two subdirectories:

- `tf/` - Terraform example for creating compartment structures such as `/Prod/Team1`, `/Integ/Team1`, and `/Dev/Team1`
- `sdk/` - Python SDK scripts for creating and deleting the same compartment structures with configurable parallelism

## Directory Layout

- `tf/`
  Terraform files for creating top-level environment compartments and second-level `Team` compartments.

- `sdk/`
  Python scripts for creating and deleting matching compartment structures using the OCI Python SDK.

## What These Examples Do

The examples in this repository work with a compartment layout like:

- `/Prod/Team1` ... `/Prod/TeamN`
- `/Integ/Team1` ... `/Integ/TeamN`
- `/Dev/Team1` ... `/Dev/TeamN`

The tooling is intended for testing, scaling exercises, and bulk compartment management scenarios.

## Authentication

Depending on the subdirectory and tool you use, authentication is done with:

- OCI config file authentication
- OCI instance principal authentication for the Python SDK scripts

## IAM Requirement

The practical OCI IAM policy needed for these examples is:

```text
Allow group <group-name> to manage compartments in tenancy
```

## More Information

See the README in each subdirectory for usage details:

- `tf/README.md`
- `sdk/README.md`
