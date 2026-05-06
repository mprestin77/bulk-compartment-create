# OCI Compartment Terraform Example

This Terraform example creates the following OCI compartment layout:

- `/Prod/Team1` ... `/Prod/TeamN`
- `/Integ/Team1` ... `/Integ/TeamN`
- `/Dev/Team1` ... `/Dev/TeamN`

The top-level compartments are created first:

- `Prod`
- `Integ`
- `Dev`

Then Terraform creates `Team1` through `Team<compartment_count>` under each top-level environment compartment.

## Files

- `provider.tf` - Terraform and OCI provider configuration
- `variables.tf` - input variables
- `main.tf` - compartment resources
- `terraform.tfvars` - example variable values

## Variables

- `tenancy_ocid` - OCID of the OCI tenancy
- `compartment_count` - number of `Team` compartments to create under each environment
- `envs` - top-level environment compartments to create; default is `["Prod", "Integ", "Dev"]`

## IAM Policy

The OCI user group running this Terraform configuration should have:

```text
Allow group <group-name> to manage compartments in tenancy
```

## Example

Current example in `terraform.tfvars`:

```hcl
tenancy_ocid      = "your-tenancy-OCID"
compartment_count = 100
```

With `compartment_count = 100`, Terraform creates:

- `3` top-level compartments
- `300` second-level compartments
- `303` total compartments

## Usage

Run from this directory:

```bash
cd /Users/mprestin/scripts/compartments/tf
terraform init
terraform plan
terraform apply
```

If you want Terraform to ask for approval before creating resources:

```bash
terraform apply
```

If you want Terraform to apply without prompting:

```bash
terraform apply -auto-approve
```

## Parallelism

Terraform creates resources in parallel when dependencies allow it.

In this configuration:

- `Prod`, `Integ`, and `Dev` must be created first
- after a parent compartment exists, its `Team` child compartments can be created in parallel
- Terraform uses a default parallelism of `10`

To increase parallelism:

```bash
terraform apply -parallelism=20
```

## Notes

- `Team1` can exist under multiple parents, so `/Prod/Team1`, `/Integ/Team1`, and `/Dev/Team1` are valid
- `enable_delete = true` is set on the compartment resources
- OCI may still throttle requests even if Terraform parallelism is increased
