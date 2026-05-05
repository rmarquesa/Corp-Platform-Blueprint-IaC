variable "proxmox_endpoint" {
  description = "Proxmox API endpoint (e.g. https://192.168.1.60:8006/)"
  type        = string
  default     = "https://192.168.1.60:8006/"
}

variable "proxmox_api_token" {
  description = "Proxmox API token in the form user@realm!tokenid=uuid"
  type        = string
  sensitive   = true
}

variable "proxmox_host" {
  description = "IP do host Proxmox para SSH"
  type        = string
  default     = "192.168.1.60"
}

variable "proxmox_ssh_password" {
  description = "Password do root do host Proxmox para SSH"
  type        = string
  sensitive   = true
}

variable "proxmox_insecure" {
  description = "Skip TLS certificate verification (set false in production)"
  type        = bool
  default     = true
}

variable "proxmox_node" {
  description = "Name of the Proxmox node where resources will be created"
  type        = string
  default     = "pve"
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key file injected into VMs via cloud-init"
  type        = string
  default     = "~/.ssh/rmarquesa.pub"
}

variable "private_network" {
  description = "Network address for the private subnet (e.g. 10.10.0.0)"
  type        = string
  default     = "10.10.0.0"
}

variable "private_gateway" {
  description = "Gateway IP for the private network"
  type        = string
  default     = "10.10.0.1"
}

variable "private_cidr_prefix" {
  description = "CIDR prefix length for the private network"
  type        = number
  default     = 24
}

variable "dns_servers" {
  description = "DNS servers pushed to all VMs and LXC containers via cloud-init"
  type        = list(string)
  default     = ["10.10.0.5", "1.1.1.1"]
}
