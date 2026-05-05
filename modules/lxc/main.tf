resource "proxmox_virtual_environment_container" "this" {
  description = var.description
  node_name   = var.node_name
  vm_id       = var.vm_id
  tags        = var.tags

  initialization {
    hostname = var.name

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
      keys     = var.ssh_public_keys
      password = var.root_password
    }
  }

  cpu {
    cores = var.cpu_cores
  }

  memory {
    dedicated = var.memory_mb
    swap      = var.swap_mb
  }

  disk {
    datastore_id = var.disk.datastore_id
    size         = var.disk.size
  }

  network_interface {
    name    = "eth0"
    bridge  = var.network_bridge
    vlan_id = var.vlan_id
  }

  operating_system {
    template_file_id = var.template_file_id
    type             = var.os_type
  }

  dynamic "features" {
    for_each = var.nesting ? [1] : []
    content {
      nesting = true
    }
  }

  unprivileged  = var.unprivileged
  start_on_boot = var.on_boot
  started       = true
}

# TUN device is not exposed via the provider API — must be injected into the LXC config file directly.
# Required for Tailscale (WireGuard needs /dev/net/tun inside the container).
resource "null_resource" "tun_device" {
  count = var.tun_device && var.proxmox_host != null ? 1 : 0

  triggers = {
    container_id = proxmox_virtual_environment_container.this.vm_id
  }

  provisioner "local-exec" {
    command = <<-EOT
      ssh -o StrictHostKeyChecking=no root@${var.proxmox_host} "
        grep -q 'dev/net/tun' /etc/pve/lxc/${var.vm_id}.conf || (
          echo 'lxc.cgroup2.devices.allow: c 10:200 rwm' >> /etc/pve/lxc/${var.vm_id}.conf &&
          echo 'lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file' >> /etc/pve/lxc/${var.vm_id}.conf &&
          pct reboot ${var.vm_id}
        )
      "
    EOT
  }

  depends_on = [proxmox_virtual_environment_container.this]
}
