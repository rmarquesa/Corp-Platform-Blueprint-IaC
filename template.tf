resource "null_resource" "enable_snippets" {
  provisioner "local-exec" {
    command = <<-EOT
      curl -sk -X PUT \
        -H "Authorization: PVEAPIToken=${var.proxmox_api_token}" \
        -d "content=vztmpl,backup,iso,snippets" \
        "${var.proxmox_endpoint}api2/json/storage/local"
    EOT
  }
}

resource "proxmox_virtual_environment_file" "vendor_data" {
  depends_on   = [null_resource.enable_snippets]
  content_type = "snippets"
  datastore_id = "local"
  node_name    = var.proxmox_node

  source_raw {
    file_name = "vm-vendor-data.yaml"
    data      = <<-EOF
      #cloud-config
      packages:
        - qemu-guest-agent
        - curl
        - ca-certificates
      runcmd:
        - systemctl enable qemu-guest-agent
        - systemctl start qemu-guest-agent
      EOF
  }
}

resource "proxmox_download_file" "ubuntu_2404" {
  content_type = "iso"
  datastore_id = "local"
  node_name    = var.proxmox_node
  url          = "https://cloud-images.ubuntu.com/releases/noble/release/ubuntu-24.04-server-cloudimg-amd64.img"
  file_name    = "ubuntu-24.04-server-cloudimg-amd64.img"

  lifecycle {
    prevent_destroy = true
  }
}

resource "proxmox_virtual_environment_vm" "ubuntu_template" {
  name      = "ubuntu-2404-template"
  node_name = var.proxmox_node
  vm_id     = 9000
  template  = true

  cpu {
    cores = 2
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = 2048
  }

  disk {
    datastore_id = "ssd"
    file_id      = proxmox_download_file.ubuntu_2404.id
    interface    = "scsi0"
    file_format  = "raw"
    discard      = "on"
    iothread     = true
    size         = 10
  }

  network_device {
    bridge = "vmbr0"
    model  = "virtio"
  }

  initialization {
    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }
  }

  operating_system {
    type = "l26"
  }

  lifecycle {
    ignore_changes  = all
    prevent_destroy = true
  }
}
