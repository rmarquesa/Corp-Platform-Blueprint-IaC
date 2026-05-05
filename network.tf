resource "proxmox_sdn_zone_simple" "private" {
  id = "privzone"
}

resource "proxmox_sdn_vnet" "private" {
  id   = "privnet"
  zone = proxmox_sdn_zone_simple.private.id
}

resource "proxmox_sdn_subnet" "private" {
  vnet    = proxmox_sdn_vnet.private.id
  cidr    = "${var.private_network}/${var.private_cidr_prefix}"
  gateway = var.private_gateway
  snat    = true
}

resource "null_resource" "sdn_apply" {
  depends_on = [proxmox_sdn_subnet.private]

  provisioner "local-exec" {
    command = <<-EOT
      curl -sk -X PUT \
        -H "Authorization: PVEAPIToken=${var.proxmox_api_token}" \
        "${var.proxmox_endpoint}api2/json/cluster/sdn"
    EOT
  }
}
