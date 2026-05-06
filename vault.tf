module "vault" {
  source = "./modules/lxc"

  name      = "vault"
  node_name = var.proxmox_node
  vm_id     = 221

  template_file_id = proxmox_download_file.debian12_lxc.id
  os_type          = "debian"

  cpu_cores = 2
  memory_mb = 2048
  swap_mb   = 0

  disk = {
    datastore_id = "local-lvm"
    size         = 10
  }

  network_bridge = proxmox_sdn_vnet.private.id
  ip_address     = "10.10.0.31/${var.private_cidr_prefix}"
  gateway        = var.private_gateway
  dns_servers    = var.dns_servers

  ssh_public_keys = [trimspace(file(var.ssh_public_key_path))]
  unprivileged    = true

  tags = ["vault", "secrets"]

  depends_on = [null_resource.sdn_apply]
}
