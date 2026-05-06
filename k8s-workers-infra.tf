locals {
  infra_nodes = {
    k8s-infra-1 = { vm_id = 204, ip = "10.10.0.13" }
    k8s-infra-2 = { vm_id = 205, ip = "10.10.0.14" }
    k8s-infra-3 = { vm_id = 206, ip = "10.10.0.15" }
  }
}

module "workers_infra" {
  for_each = local.infra_nodes

  source         = "./modules/vm"
  name           = each.key
  node_name      = var.proxmox_node
  vm_id          = each.value.vm_id
  template_vm_id = proxmox_virtual_environment_vm.ubuntu_template.vm_id

  cpu_cores = 4
  memory_mb = 8192

  disk = {
    datastore_id = "ssd"
    size         = 40
  }

  network_bridge      = proxmox_sdn_vnet.private.id
  ip_address          = "${each.value.ip}/${var.private_cidr_prefix}"
  gateway             = var.private_gateway
  dns_servers         = var.dns_servers
  ssh_public_keys     = [trimspace(file(var.ssh_public_key_path))]
  vendor_data_file_id = proxmox_virtual_environment_file.vendor_data.id
  tags                = ["k8s", "infra"]

  depends_on = [null_resource.sdn_apply]
}
