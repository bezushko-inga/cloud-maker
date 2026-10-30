from pathlib import Path
import libvirt
import time


def resource_cleanup():
    connection = libvirt.open("qemu:///system")
    if connection is None:
        raise RuntimeError("Failed to connect to libvirt")

    disk_dir = Path("/var/lib/libvirt/images/cloud-maker")

    try:
        disks = list(disk_dir.glob("*.qcow2"))
        seeds = list(disk_dir.glob("*-seed.iso"))

        names = {disk.stem for disk in disks}
        names.update(seed.name.removesuffix("-seed.iso") for seed in seeds)

        if not names:
            print("Already cleaned")
            return

        print("Virtual machines to delete:")
        for name in sorted(names):
            print(name)

        if input("Delete all resources? [y/n]: ").lower() != "y":
            return

        for name in sorted(names):
            disk = disk_dir / f"{name}.qcow2"
            seed = disk_dir / f"{name}-seed.iso"

            try:
                domain = connection.lookupByName(name)
            except libvirt.libvirtError as e:
                if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
                    raise
                domain = None

            if domain is not None:
                if domain.isActive():
                    domain.shutdown()

                    for _ in range(30):
                        if not domain.isActive():
                            break
                        time.sleep(2)

                domain.undefine()

            disk.unlink(missing_ok=True)
            seed.unlink(missing_ok=True)

            print(f"{name} deleted")

    finally:
        connection.close()


if __name__ == "__main__":
    resource_cleanup()
