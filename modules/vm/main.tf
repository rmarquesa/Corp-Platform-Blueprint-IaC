resource "proxmox_virtual_environment_vm" "this" {
  name          = var.name
  node_name     = var.node_name
  vm_id         = var.vm_id
  tags          = var.tags
  scsi_hardware = "virtio-scsi-single"

  clone {
    vm_id = var.template_vm_id
    full  = true
  }

  cpu {
    cores = var.cpu_cores
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = var.memory_mb
  }

  disk {
    datastore_id = var.disk.datastore_id
    size         = var.disk.size
    interface    = var.disk.interface
    file_format  = var.disk.file_format
    discard      = var.disk.discard
    iothread     = var.disk.iothread
  }

  network_device {
    bridge  = var.network_bridge
    model   = "virtio"
    vlan_id = var.vlan_id
  }

  initialization {
    ip_config {
      ipv4 {
        address = var.ip_address
        gateway = var.gateway
      }
    }

    dns {
      servers = var.dns_servers
    }

    user_account {
      username = var.cloud_init_user
      keys     = var.ssh_public_keys
    }

    vendor_data_file_id = var.vendor_data_file_id
  }

  operating_system {
    type = "l26"
  }

  on_boot = var.on_boot

}
