#!/usr/bin/env python3
"""
Create OCI compartments in the layout:
  /Prod/Team1 ... /Prod/TeamN
  /Integ/Team1 ... /Integ/TeamN
  /Dev/Team1 ... /Dev/TeamN

The script creates or reuses the top-level environment compartments, then
creates missing Team compartments under each parent using parallel workers.
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import oci


ACTIVE_STATES = {"ACTIVE", "CREATING", "UPDATING"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create Team compartments under Prod, Integ, and Dev using the OCI Python SDK."
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Number of Team compartments to create under each environment compartment.",
    )
    parser.add_argument(
        "--envs",
        default="Prod,Integ,Dev",
        help="Comma-separated top-level environment compartment names. Default: Prod,Integ,Dev",
    )
    parser.add_argument(
        "--team-prefix",
        default="Team",
        help="Prefix for second-level compartment names. Default: Team",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="Starting Team index. Default: 1",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Number of parallel workers for child compartment creation. Default: 10",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for each created compartment to become ACTIVE.",
    )
    parser.add_argument(
        "--region",
        help="OCI region. Defaults to the region from OCI config or the current instance region.",
    )
    parser.add_argument(
        "-p",
        "--profile",
        default="DEFAULT",
        help="OCI config profile name. Default: DEFAULT",
    )
    parser.add_argument(
        "-c",
        "--config-file",
        default=oci.config.DEFAULT_LOCATION,
        help=f"OCI config path. Default: {oci.config.DEFAULT_LOCATION}",
    )
    parser.add_argument(
        "--instance-principal",
        action="store_true",
        help="Use OCI instance principal authentication instead of the OCI config file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without creating compartments.",
    )
    return parser.parse_args()


def create_client(client_class, config, signer=None):
    if signer is None:
        return client_class(config)
    return client_class(config, signer=signer)


def load_auth(args):
    if args.instance_principal:
        try:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize instance principal authentication: {exc}") from exc
        config = {
            "region": args.region or signer.region,
            "tenancy": signer.tenancy_id,
        }
        return config, signer

    try:
        config = oci.config.from_file(args.config_file, args.profile)
    except Exception as exc:
        raise RuntimeError(f"Failed to load OCI config: {exc}") from exc

    if args.region:
        config["region"] = args.region
    return config, None


def paged(callable_obj, *args, **kwargs):
    return oci.pagination.list_call_get_all_results(callable_obj, *args, **kwargs).data


def state_upper(compartment):
    return (getattr(compartment, "lifecycle_state", "") or "").upper()


def list_compartments(identity_client, tenancy_id):
    compartments = paged(
        identity_client.list_compartments,
        tenancy_id,
        compartment_id_in_subtree=True,
        access_level="ACCESSIBLE",
    )
    compartments.append(identity_client.get_compartment(tenancy_id).data)
    return compartments


def name_map_for_parent(compartments, parent_id):
    result = {}
    for compartment in compartments:
        if getattr(compartment, "compartment_id", None) != parent_id:
            continue
        if state_upper(compartment) not in ACTIVE_STATES:
            continue
        result[compartment.name] = compartment
    return result


def wait_until_active(identity_client, compartment_id):
    while True:
        compartment = identity_client.get_compartment(compartment_id).data
        state = state_upper(compartment)
        if state == "ACTIVE":
            return compartment
        if state == "FAILED":
            raise RuntimeError(f"Compartment {compartment.name} failed to become ACTIVE.")
        time.sleep(2)


def ensure_parent_compartment(identity_client, tenancy_id, env_name, dry_run):
    compartments = list_compartments(identity_client, tenancy_id)
    existing = name_map_for_parent(compartments, tenancy_id).get(env_name)
    if existing:
        print(f"Parent compartment exists: {env_name}")
        return existing

    if dry_run:
        print(f"Would create parent compartment: {env_name}")
        return None

    details = oci.identity.models.CreateCompartmentDetails(
        compartment_id=tenancy_id,
        name=env_name,
        description=f"{env_name} environment",
    )
    created = identity_client.create_compartment(details).data
    print(f"Creating parent compartment: {env_name}")
    return wait_until_active(identity_client, created.id)


def team_name(team_prefix, index):
    return f"{team_prefix}{index}"


def create_child_compartment(config, signer, parent_id, env_name, child_name, wait_for_active):
    identity_client = create_client(oci.identity.IdentityClient, config, signer)
    details = oci.identity.models.CreateCompartmentDetails(
        compartment_id=parent_id,
        name=child_name,
        description=f"Second-level compartment {child_name} under {env_name}",
    )
    created = identity_client.create_compartment(details).data
    if wait_for_active:
        wait_until_active(identity_client, created.id)
    return f"{env_name}/{child_name}"


def main():
    args = parse_args()

    if args.count <= 0:
        print("--count must be greater than zero.", file=sys.stderr)
        return 1
    if args.start_index <= 0:
        print("--start-index must be greater than zero.", file=sys.stderr)
        return 1
    if args.workers <= 0:
        print("--workers must be greater than zero.", file=sys.stderr)
        return 1

    envs = [item.strip() for item in args.envs.split(",") if item.strip()]
    if not envs:
        print("At least one environment name is required.", file=sys.stderr)
        return 1

    try:
        config, signer = load_auth(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    tenancy_id = config["tenancy"]
    identity_client = create_client(oci.identity.IdentityClient, config, signer)

    created_count = 0
    skipped_count = 0
    work_items = []

    for env_name in envs:
        try:
            parent = ensure_parent_compartment(identity_client, tenancy_id, env_name, args.dry_run)
        except Exception as exc:
            print(f"Failed to ensure parent compartment {env_name}: {exc}", file=sys.stderr)
            return 1

        if args.dry_run:
            existing_children = {}
            parent_id = f"<new:{env_name}>"
        else:
            parent_id = parent.id
            compartments = list_compartments(identity_client, tenancy_id)
            existing_children = name_map_for_parent(compartments, parent_id)

        for index in range(args.start_index, args.start_index + args.count):
            child = team_name(args.team_prefix, index)
            if child in existing_children:
                print(f"Child compartment exists: {env_name}/{child}")
                skipped_count += 1
                continue
            if args.dry_run:
                print(f"Would create child compartment: {env_name}/{child}")
                created_count += 1
                continue
            work_items.append((parent_id, env_name, child))

    if args.dry_run:
        print(f"Would create {created_count} compartments. Skipped {skipped_count} existing compartments.")
        return 0

    if not work_items:
        print(f"Created 0 compartments. Skipped {skipped_count} existing compartments.")
        return 0

    print(f"Creating {len(work_items)} child compartments with {args.workers} workers...")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                create_child_compartment,
                dict(config),
                signer,
                parent_id,
                env_name,
                child_name,
                args.wait,
            ): (env_name, child_name)
            for parent_id, env_name, child_name in work_items
        }
        for future in as_completed(futures):
            env_name, child_name = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                print(f"Failed to create {env_name}/{child_name}: {exc}", file=sys.stderr)
                return 1
            print(f"Created child compartment: {result}")
            created_count += 1

    print(f"Created {created_count} compartments. Skipped {skipped_count} existing compartments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
