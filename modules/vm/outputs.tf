output "vm_id" {
  description = "ID of the created VM"
  value       = proxmox_virtual_environment_vm.this.vm_id
}

output "name" {
  description = "Name of the created VM"
  value       = proxmox_virtual_environment_vm.this.name
}

output "ipv4_addresses" {
  description = "IPv4 addresses reported by the QEMU agent"
  value       = proxmox_virtual_environment_vm.this.ipv4_addresses
}
