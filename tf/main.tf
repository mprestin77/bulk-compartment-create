locals {
  child_compartments = flatten([
    for env in var.envs : [
      for i in range(1, var.compartment_count + 1) : {
        key         = "${env}-Team${i}"
        env         = env
        name        = "Team${i}"
        description = "Second-level compartment Team${i} under ${env}"
      }
    ]
  ])
}

resource "oci_identity_compartment" "env" {
  for_each = toset(var.envs)

  compartment_id = var.tenancy_ocid
  name           = each.value
  description    = "${each.value} environment"
  enable_delete  = true
}

resource "oci_identity_compartment" "child" {
  for_each = {
    for item in local.child_compartments : item.key => item
  }

  compartment_id = oci_identity_compartment.env[each.value.env].id
  name           = each.value.name
  description    = each.value.description
  enable_delete  = true
}
