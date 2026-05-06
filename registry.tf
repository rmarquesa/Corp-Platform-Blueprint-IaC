module "harbor" {
  source         = "./modules/vm"
  name           = "harbor"
  node_name      = var.proxmox_node
  vm_id          = 220
  template_vm_id = proxmox_virtual_environment_vm.ubuntu_template.vm_id

  cpu_cores = 4
  memory_mb = 8192

  disk = {
    datastore_id = "local-lvm"
    size         = 50
  }

  network_bridge      = proxmox_sdn_vnet.private.id
  ip_address          = "10.10.0.30/${var.private_cidr_prefix}"
  gateway             = var.private_gateway
  dns_servers         = var.dns_servers
  ssh_public_keys     = [trimspace(file(var.ssh_public_key_path))]
  vendor_data_file_id = proxmox_virtual_environment_file.vendor_data.id
  tags                = ["harbor", "registry"]

  depends_on = [null_resource.sdn_apply]
}
