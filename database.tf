locals {
  db_nodes = {
    db-1 = { vm_id = 210, ip = "10.10.0.20" }
    db-2 = { vm_id = 211, ip = "10.10.0.22" }
  }
}

module "db" {
  for_each = local.db_nodes

  source         = "./modules/vm"
  name           = each.key
  node_name      = var.proxmox_node
  vm_id          = each.value.vm_id
  template_vm_id = proxmox_virtual_environment_vm.ubuntu_template.vm_id

  cpu_cores = 2
  memory_mb = 4096

  disk = {
    datastore_id = "local-lvm"
    size         = 50
  }

  network_bridge       = proxmox_sdn_vnet.private.id
  ip_address           = "${each.value.ip}/${var.private_cidr_prefix}"
  gateway              = var.private_gateway
  dns_servers  = var.dns_servers
  ssh_public_keys      = [trimspace(file(var.ssh_public_key_path))]
  vendor_data_file_id  = proxmox_virtual_environment_file.vendor_data.id
  tags = ["db"]

  depends_on = [null_resource.sdn_apply]
}

module "db_arbiter" {
  source         = "./modules/vm"
  name           = "db-arbiter"
  node_name      = var.proxmox_node
  vm_id          = 212
  template_vm_id = proxmox_virtual_environment_vm.ubuntu_template.vm_id

  cpu_cores = 1
  memory_mb = 512

  disk = {
    datastore_id = "local-lvm"
    size         = 10
  }

  network_bridge      = proxmox_sdn_vnet.private.id
  ip_address          = "10.10.0.23/${var.private_cidr_prefix}"
  gateway             = var.private_gateway
  dns_servers  = var.dns_servers
  ssh_public_keys     = [trimspace(file(var.ssh_public_key_path))]
  vendor_data_file_id = proxmox_virtual_environment_file.vendor_data.id
  tags                = ["db", "etcd-arbiter"]

  depends_on = [null_resource.sdn_apply]
}
