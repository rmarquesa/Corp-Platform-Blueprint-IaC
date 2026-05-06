locals {
  app_nodes = {
    k8s-app-1 = { vm_id = 207, ip = "10.10.0.16" }
    k8s-app-2 = { vm_id = 208, ip = "10.10.0.17" }
  }
}

module "workers_app" {
  for_each = local.app_nodes

  source         = "./modules/vm"
  name           = each.key
  node_name      = var.proxmox_node
  vm_id          = each.value.vm_id
  template_vm_id = proxmox_virtual_environment_vm.ubuntu_template.vm_id

  cpu_cores = 2
  memory_mb = 4096

  disk = {
    datastore_id = "ssd"
    size         = 20
  }

  network_bridge      = proxmox_sdn_vnet.private.id
  ip_address          = "${each.value.ip}/${var.private_cidr_prefix}"
  gateway             = var.private_gateway
  dns_servers         = var.dns_servers
  ssh_public_keys     = [trimspace(file(var.ssh_public_key_path))]
  vendor_data_file_id = proxmox_virtual_environment_file.vendor_data.id
  tags                = ["k8s", "app"]

  depends_on = [null_resource.sdn_apply]
}
