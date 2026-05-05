locals {
  k8s_nodes = {
    k8s-master-1 = { vm_id = 201, ip = "10.10.0.10" }
    k8s-master-2 = { vm_id = 202, ip = "10.10.0.11" }
    k8s-master-3 = { vm_id = 203, ip = "10.10.0.12" }
  }
}

module "k8s" {
  for_each = local.k8s_nodes

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

  network_bridge = proxmox_sdn_vnet.private.id
  ip_address     = "${each.value.ip}/${var.private_cidr_prefix}"
  gateway        = var.private_gateway
  dns_servers  = var.dns_servers

  ssh_public_keys     = [trimspace(file(var.ssh_public_key_path))]
  vendor_data_file_id = proxmox_virtual_environment_file.vendor_data.id
  tags                = ["k8s"]

  depends_on = [null_resource.sdn_apply]
}
