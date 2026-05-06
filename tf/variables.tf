variable "tenancy_ocid" {
  description = "OCID of the OCI tenancy."
  type        = string
}

variable "compartment_count" {
  description = "Number of Team compartments to create under each environment compartment."
  type        = number
  default     = 100
}

variable "envs" {
  description = "Top-level environment compartments to create."
  type        = list(string)
  default     = ["Prod", "Integ", "Dev"]
}
