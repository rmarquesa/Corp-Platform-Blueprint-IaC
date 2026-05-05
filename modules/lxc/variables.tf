variable "name" {
  description = "LXC hostname"
  type        = string
}

variable "description" {
  description = "Container description"
  type        = string
  default     = ""
}

variable "node_name" {
  description = "Proxmox node name"
  type        = string
}

variable "vm_id" {
  description = "Container ID (100–999999)"
  type        = number
}

variable "template_file_id" {
  description = "Template file ID (e.g. local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst)"
  type        = string
}

variable "os_type" {
  description = "OS type hint for the container"
  type        = string
  default     = "ubuntu"
}

variable "cpu_cores" {
  description = "Number of CPU cores"
  type        = number
  default     = 1
}

variable "memory_mb" {
  description = "RAM in MiB"
  type        = number
  default     = 512
}

variable "swap_mb" {
  description = "Swap in MiB"
  type        = number
  default     = 512
}

variable "disk" {
  description = "Root filesystem disk configuration"
  type = object({
    datastore_id = string
    size         = number
  })
  default = {
    datastore_id = "local-lvm"
    size         = 8
  }
}

variable "network_bridge" {
  description = "Network bridge"
  type        = string
  default     = "vmbr0"
}

variable "vlan_id" {
  description = "VLAN tag (null = untagged)"
  type        = number
  default     = null
}

variable "ip_address" {
  description = "Static IP with prefix (e.g. 192.168.1.200/24), or 'dhcp'"
  type        = string
  default     = "dhcp"
}

variable "gateway" {
  description = "Default gateway"
  type        = string
  default     = null
}

variable "dns_servers" {
  description = "List of DNS server IPs"
  type        = list(string)
  default     = ["1.1.1.1", "8.8.8.8"]
}

variable "ssh_public_keys" {
  description = "SSH public keys for the root user"
  type        = list(string)
  default     = []
}

variable "root_password" {
  description = "Root password (prefer SSH keys, set sensitive in calling module)"
  type        = string
  sensitive   = true
  default     = null
}

variable "unprivileged" {
  description = "Run as unprivileged container (recommended)"
  type        = bool
  default     = true
}

variable "tags" {
  description = "List of tags to apply"
  type        = list(string)
  default     = []
}

variable "on_boot" {
  description = "Start container automatically on node boot"
  type        = bool
  default     = true
}

variable "nesting" {
  description = "Enable nesting feature (required to run Docker inside the container)"
  type        = bool
  default     = false
}

variable "tun_device" {
  description = "Enable TUN device inside the container (required for Tailscale/WireGuard)"
  type        = bool
  default     = false
}

variable "proxmox_host" {
  description = "Proxmox host IP for SSH (needed to apply TUN config)"
  type        = string
  default     = null
}
