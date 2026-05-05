resource "proxmox_download_file" "debian12_lxc" {
  content_type = "vztmpl"
  datastore_id = "local"
  node_name    = var.proxmox_node
  url          = "http://download.proxmox.com/images/system/debian-12-standard_12.12-1_amd64.tar.zst"
  file_name    = "debian-12-standard_12.12-1_amd64.tar.zst"

  lifecycle {
    prevent_destroy = true
  }
}

module "tailscale" {
  source = "./modules/lxc"

  name        = "tailscale"
  node_name   = var.proxmox_node
  vm_id       = 230

  template_file_id = proxmox_download_file.debian12_lxc.id
  os_type          = "debian"

  cpu_cores = 1
  memory_mb = 256
  swap_mb   = 0

  disk = {
    datastore_id = "local-lvm"
    size         = 4
  }

  network_bridge = proxmox_sdn_vnet.private.id
  ip_address     = "10.10.0.40/${var.private_cidr_prefix}"
  gateway        = var.private_gateway
  dns_servers  = var.dns_servers

  ssh_public_keys = [trimspace(file(var.ssh_public_key_path))]
  unprivileged    = true

  tun_device   = true
  proxmox_host = var.proxmox_host

  tags = ["tailscale", "vpn"]

  depends_on = [null_resource.sdn_apply]
}
