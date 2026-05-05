variable "name" {
  description = "VM name"
  type        = string
}

variable "node_name" {
  description = "Proxmox node name"
  type        = string
}

variable "vm_id" {
  description = "VM ID (100–999999)"
  type        = number
}

variable "template_vm_id" {
  description = "VM ID of the cloud-init template to clone"
  type        = number
}

variable "cpu_cores" {
  description = "Number of vCPU cores"
  type        = number
  default     = 2
}

variable "memory_mb" {
  description = "RAM in MiB"
  type        = number
  default     = 2048
}

variable "disk" {
  description = "Primary disk configuration"
  type = object({
    datastore_id = string
    size         = number
    interface    = optional(string, "scsi0")
    file_format  = optional(string, "raw")
    discard      = optional(string, "on")
    iothread     = optional(bool, true)
  })
  default = {
    datastore_id = "local-lvm"
    size         = 20
  }
}

variable "network_bridge" {
  description = "Network bridge (e.g. vmbr0)"
  type        = string
  default     = "vmbr0"
}

variable "vlan_id" {
  description = "VLAN tag (null = untagged)"
  type        = number
  default     = null
}

variable "ip_address" {
  description = "Static IP with prefix (e.g. 192.168.1.100/24), or 'dhcp'"
  type        = string
  default     = "dhcp"
}

variable "gateway" {
  description = "Default gateway (ignored when ip_address = 'dhcp')"
  type        = string
  default     = null
}

variable "dns_servers" {
  description = "List of DNS server IPs"
  type        = list(string)
  default     = ["1.1.1.1", "8.8.8.8"]
}

variable "cloud_init_user" {
  description = "cloud-init default username"
  type        = string
  default     = "ubuntu"
}

variable "ssh_public_keys" {
  description = "SSH public keys injected via cloud-init"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "List of tags to apply to the VM"
  type        = list(string)
  default     = []
}

variable "on_boot" {
  description = "Start VM automatically on node boot"
  type        = bool
  default     = true
}

variable "vendor_data_file_id" {
  description = "File ID of the cloud-init vendor-data snippet (additive, does not override SSH keys)"
  type        = string
  default     = null
}
