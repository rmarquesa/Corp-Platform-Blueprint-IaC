output "vm_id" {
  description = "ID of the created container"
  value       = proxmox_virtual_environment_container.this.vm_id
}

output "name" {
  description = "Hostname of the created container"
  value       = proxmox_virtual_environment_container.this.initialization[0].hostname
}
