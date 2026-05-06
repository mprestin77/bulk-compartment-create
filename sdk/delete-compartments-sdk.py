#!/usr/bin/env python3
"""
Delete OCI compartments created by create-compartments-sdk.py.

By default, the script deletes matching Team compartments under:
  /Prod
  /Integ
  /Dev

It does not delete the parent environment compartments unless
--delete-parents is specified.
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import oci


LISTABLE_STATES = {"ACTIVE", "CREATING", "UPDATING", "DELETING"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Delete Team compartments under Prod, Integ, and Dev using the OCI Python SDK."
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Number of Team compartments per environment to target for deletion.",
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
        help="Number of parallel workers for child compartment deletion. Default: 10",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for each targeted compartment to reach DELETED state.",
    )
    parser.add_argument(
        "--delete-parents",
        action="store_true",
        help="After child deletion, delete empty parent compartments too.",
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
        help="Show what would be deleted without deleting anything.",
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
        if state_upper(compartment) not in LISTABLE_STATES:
            continue
        result[compartment.name] = compartment
    return result


def wait_until_deleted(identity_client, compartment_id):
    while True:
        compartment = identity_client.get_compartment(compartment_id).data
        state = state_upper(compartment)
        if state == "DELETED":
            return compartment
        if state == "FAILED":
            raise RuntimeError(f"Compartment {compartment.name} failed to delete.")
        time.sleep(2)


def team_name(team_prefix, index):
    return f"{team_prefix}{index}"


def delete_compartment(config, signer, compartment_id, label, wait_for_deleted):
    identity_client = create_client(oci.identity.IdentityClient, config, signer)
    identity_client.delete_compartment(compartment_id)
    if wait_for_deleted:
        wait_until_deleted(identity_client, compartment_id)
    return label


def parent_has_children(compartments, parent_id):
    for compartment in compartments:
        if getattr(compartment, "compartment_id", None) != parent_id:
            continue
        if state_upper(compartment) in LISTABLE_STATES:
            return True
    return False


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
    compartments = list_compartments(identity_client, tenancy_id)
    top_level = name_map_for_parent(compartments, tenancy_id)

    parent_targets = []
    child_work_items = []
    skipped_count = 0

    for env_name in envs:
        parent = top_level.get(env_name)
        if not parent:
            print(f"Parent compartment not found: {env_name}")
            continue
        parent_targets.append((env_name, parent.id))

        children = name_map_for_parent(compartments, parent.id)
        for index in range(args.start_index, args.start_index + args.count):
            child = children.get(team_name(args.team_prefix, index))
            if not child:
                print(f"Child compartment not found: {env_name}/{team_name(args.team_prefix, index)}")
                skipped_count += 1
                continue
            label = f"{env_name}/{child.name}"
            if args.dry_run:
                print(f"Would delete child compartment: {label}")
                continue
            child_work_items.append((child.id, label))

    deleted_count = 0

    if args.dry_run:
        if args.delete_parents:
            for env_name, _ in parent_targets:
                print(f"Would delete parent compartment after children are gone: {env_name}")
        print(f"Would delete {len(child_work_items)} child compartments. Skipped {skipped_count} missing compartments.")
        return 0

    if child_work_items:
        print(f"Deleting {len(child_work_items)} child compartments with {args.workers} workers...")
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    delete_compartment,
                    dict(config),
                    signer,
                    compartment_id,
                    label,
                    args.wait,
                ): label
                for compartment_id, label in child_work_items
            }
            for future in as_completed(futures):
                label = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    print(f"Failed to delete {label}: {exc}", file=sys.stderr)
                    return 1
                print(f"Deleted child compartment: {result}")
                deleted_count += 1

    parent_deleted_count = 0
    if args.delete_parents:
        if not args.wait and child_work_items:
            print(
                "--delete-parents without --wait is unsafe because child compartments may still be deleting.",
                file=sys.stderr,
            )
            return 1

        compartments = list_compartments(identity_client, tenancy_id)
        for env_name, parent_id in parent_targets:
            if parent_has_children(compartments, parent_id):
                print(f"Parent compartment not empty, skipping delete: {env_name}")
                continue
            try:
                delete_compartment(
                    dict(config),
                    signer,
                    parent_id,
                    env_name,
                    args.wait,
                )
            except Exception as exc:
                print(f"Failed to delete parent compartment {env_name}: {exc}", file=sys.stderr)
                return 1
            print(f"Deleted parent compartment: {env_name}")
            parent_deleted_count += 1

    print(
        f"Deleted {deleted_count} child compartments. "
        f"Deleted {parent_deleted_count} parent compartments. "
        f"Skipped {skipped_count} missing compartments."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
