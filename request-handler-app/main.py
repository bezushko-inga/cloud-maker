from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pathlib import Path
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from pydantic import BaseModel

import json
import libvirt
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import yaml

VMS_LIMIT = 5
MIN_MEMORY = 512
MAX_MEMORY = 4096
MIN_VCPUS = 1
MAX_VCPUS = 4
TOTAL_MEMORY_LIMIT = 8192
TOTAL_VCPUS_LIMIT = 8

PROJECT_DIR = Path(__file__).resolve().parent.parent
IMAGES_FILE = PROJECT_DIR / "images.json"
DEFAULT_IMAGE = PROJECT_DIR / "noble-server-cloudimg-amd64.img"

app = FastAPI()


class VirtualMachine(BaseModel):
    name: str
    memory: int = 2048
    vcpus: int = 2
    hostname: str | None = None
    ssh_key: str | None = None
    user_data: str | None = None
    image: str = "default"


class Image(BaseModel):
    name: str
    path: str


@app.get("/images")
def get_images():
    if not IMAGES_FILE.exists():
        return {"default": str(DEFAULT_IMAGE)}
    with open(IMAGES_FILE) as f:
        images = json.load(f)

    images["default"] = str(DEFAULT_IMAGE)
    return images


@app.post("/images")
def register_image(image: Image):
    if not image.name or not all(c.isalnum() or c in "-_" for c in image.name):
        raise HTTPException(status_code=400, detail="Invalid image name")

    if image.name == "default":
        raise HTTPException(status_code=409, detail="Image already registered")

    image_path = Path(image.path).expanduser().resolve()

    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")

    if not image_path.suffix.lower() in (".img", ".qcow2"):
        raise HTTPException(status_code=400, detail="Unsupported image format")

    images = {}
    if IMAGES_FILE.exists():
        with open(IMAGES_FILE) as f:
            images = json.load(f)

    if image.name in images:
        raise HTTPException(status_code=409, detail="Image already registered")

    images[image.name] = str(image_path)

    with open(IMAGES_FILE, "w") as f:
        json.dump(images, f, indent=4)

    return {"name": image.name, "path": str(image_path)}


@app.get("/vms")
def get_virtual_machines():
    try:
        connection = libvirt.open("qemu:///system")
    except libvirt.libvirtError:
        raise HTTPException(status_code=503, detail="Failed to connect to libvirt")

    if connection is None:
        raise HTTPException(status_code=503, detail="Failed to connect to libvirt")

    try:
        vms = []
        for domain in connection.listAllDomains():
            if domain.isActive():
                vms.append({"name": domain.name(), "state": "running"})
            else:
                vms.append({"name": domain.name(), "state": "stopped"})

        return vms

    finally:
        connection.close()


@app.post("/vms")
def create_virtual_machine(vm: VirtualMachine):
    try:
        connection = libvirt.open("qemu:///system")
    except libvirt.libvirtError:
        raise HTTPException(status_code=503, detail="Failed to connect to libvirt")

    if connection is None:
        raise HTTPException(status_code=503, detail="Failed to connect to libvirt")

    try:
        if not vm.name or not all(c.isalnum() or c in "-_" for c in vm.name):
            raise HTTPException(status_code=400, detail="Invalid virtual machine name")

        if not MIN_MEMORY <= vm.memory <= MAX_MEMORY:
            raise HTTPException(status_code=400, detail="Memory limit exceeded")

        if not MIN_VCPUS <= vm.vcpus <= MAX_VCPUS:
            raise HTTPException(status_code=400, detail="VCPU limit exceeded")

        try:
            connection.lookupByName(vm.name)
        except libvirt.libvirtError as e:
            if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
                raise
        else:
            raise HTTPException(
                status_code=409, detail="Virtual machine already exists"
            )

        domains = connection.listAllDomains()

        if len(domains) >= VMS_LIMIT:
            raise HTTPException(
                status_code=409, detail="Virtual machine limit exceeded"
            )

        total_memory = 0
        total_vcpus = 0

        for domain in domains:
            total_memory += domain.maxMemory() // 1024

            xml = ET.fromstring(domain.XMLDesc())
            total_vcpus += int(xml.findtext("vcpu"))

        if total_memory + vm.memory > TOTAL_MEMORY_LIMIT:
            raise HTTPException(status_code=409, detail="Total memory limit exceeded")

        if total_vcpus + vm.vcpus > TOTAL_VCPUS_LIMIT:
            raise HTTPException(status_code=409, detail="Total VCPU limit exceeded")

        images = get_images()
        if vm.image not in images:
            raise HTTPException(status_code=404, detail="Image not registered")

        base_image = Path(images[vm.image])
        if not base_image.is_file():
            raise HTTPException(status_code=404, detail="Image file not found")

        project_dir = PROJECT_DIR
        disk_dir = Path("/var/lib/libvirt/images/cloud-maker")
        disk_dir.mkdir(parents=True, exist_ok=True)
        disk = disk_dir / f"{vm.name}.qcow2"
        seed = disk_dir / f"{vm.name}-seed.iso"

        if disk.exists() or seed.exists():
            raise HTTPException(
                status_code=409, detail="Virtual machine files already exist"
            )

        network = connection.networkLookupByName("default")

        if not network.isActive():
            network.create()

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            meta = tmp / "meta-data"
            user = tmp / "user_data"
            iso = tmp / "seed.iso"
            hostname = vm.hostname or vm.name
            
            meta.write_text(f"instance-id: {vm.name}\nlocal-hostname: {hostname}\n")
            if vm.user_data:
                config = yaml.safe_load(vm.user_data.removeprefix("#cloud-config"))
            else:
                config = {}

            if config is None:
                config = {}

            if not isinstance(config, dict):
                raise HTTPException(
                    status_code=400, detail="Invalid cloud-init configuration"
                )

            config["hostname"] = hostname
            if vm.ssh_key:
                config["ssh_authorized_keys"] = [vm.ssh_key]
            user.write_text("#cloud-config\n" + yaml.safe_dump(config))

            subprocess.run(
                [
                    "cloud-localds",
                    str(iso),
                    str(user),
                    str(meta),
                ],
                check=True,
            )
            subprocess.run(["cp", str(base_image), str(disk)], check=True)
            subprocess.run(["qemu-img", "resize", str(disk), "10G"], check=True)
            subprocess.run(["cp", str(iso), str(seed)], check=True)

            subprocess.run(
                [
                    "virt-install",
                    "--connect",
                    "qemu:///system",
                    "--name",
                    vm.name,
                    "--memory",
                    str(vm.memory),
                    "--vcpus",
                    str(vm.vcpus),
                    "--import",
                    "--disk",
                    f"path={disk},format=qcow2",
                    "--disk",
                    f"path={seed},device=cdrom",
                    "--os-variant",
                    "ubuntu24.04",
                    "--network",
                    "network=default",
                    "--graphics",
                    "none",
                    "--console",
                    "pty,target_type=serial",
                    "--noautoconsole",
                ],
                check=True,
                timeout=180,
            )

        return {"name": vm.name, "state": "running"}

    finally:
        connection.close()


@app.post("/vms/{name}/stop")
def stop_virtual_machine(name: str):
    try:
        connection = libvirt.open("qemu:///system")
    except libvirt.libvirtError:
        raise HTTPException(status_code=503, detail="Failed to connect to libvirt")

    if connection is None:
        raise HTTPException(status_code=503, detail="Failed to connect to libvirt")

    try:
        try:
            domain = connection.lookupByName(name)

        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                raise HTTPException(status_code=404, detail="Virtual machine not found")
            raise

        if not domain.isActive():
            raise HTTPException(
                status_code=409, detail="Virtual machine is already stopped"
            )

        domain.shutdown()

        for _ in range(5):
            if not domain.isActive():
                break
            time.sleep(1)

        if domain.isActive():
            domain.destroy()

        return {"name": name, "state": "stopped"}

    finally:
        connection.close()


@app.delete("/vms/{name}")
def delete_virtual_machine(name: str):
    try:
        connection = libvirt.open("qemu:///system")
    except libvirt.libvirtError:
        raise HTTPException(status_code=503, detail="Failed to connect to libvirt")

    if connection is None:
        raise HTTPException(status_code=503, detail="Failed to connect to libvirt")

    try:
        try:
            domain = connection.lookupByName(name)
        except libvirt.libvirtError as e:
            if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                raise HTTPException(status_code=404, detail="Virtual machine not found")
            raise

        if domain.isActive():
            raise HTTPException(
                status_code=409,
                detail="Virtual machine must be stopped before deletion",
            )

        disk_dir = Path("/var/lib/libvirt/images/cloud-maker")
        disk = disk_dir / f"{name}.qcow2"
        seed = disk_dir / f"{name}-seed.iso"

        if not disk.is_file() or not seed.is_file():
            raise HTTPException(
                status_code=404, detail="Virtual machine files not found"
            )

        domain.undefine()
        disk.unlink()
        seed.unlink()

        return {"name": name, "state": "deleted"}

    finally:
        connection.close()


@app.get("/metrics")
def get_metrics():
    registry = CollectorRegistry()

    vm_memory = Gauge(
        "cloudmaker_vm_memory_bytes",
        "Allocated memory of virtual machines in bytes",
        ["vm_name"],
        registry=registry,
    )

    vm_cpu = Gauge(
        "cloudmaker_vm_cpu_time_seconds",
        "Total CPU time used by virtual machines in seconds",
        ["vm_name"],
        registry=registry,
    )

    vm_disk_read = Gauge(
        "cloudmaker_vm_disk_read_bytes_total",
        "Total bytes read from virtual machine disks",
        ["vm_name"],
        registry=registry,
    )

    vm_disk_write = Gauge(
        "cloudmaker_vm_disk_write_bytes_total",
        "Total bytes written to virtual machine disks",
        ["vm_name"],
        registry=registry,
    )

    vm_network_received = Gauge(
        "cloudmaker_vm_network_received_bytes_total",
        "Total network bytes received by virtual machines",
        ["vm_name"],
        registry=registry,
    )

    vm_network_transmitted = Gauge(
        "cloudmaker_vm_network_transmitted_bytes_total",
        "Total network bytes transmitted by virtual machines",
        ["vm_name"],
        registry=registry,
    )

    try:
        connection = libvirt.open("qemu:///system")
    except libvirt.libvirtError:
        raise HTTPException(status_code=503, detail="Failed to connect to libvirt")
    if connection is None:
        raise HTTPException(status_code=503, detail="Failed to connect to libvirt")

    try:
        for domain in connection.listAllDomains():
            if not domain.isActive():
                continue

            name = domain.name()

            vm_memory.labels(vm_name=name).set(domain.maxMemory() * 1024)
            cpu_time_ns = domain.info()[4]
            vm_cpu.labels(vm_name=name).set(cpu_time_ns / 1000000000)
            xml = ET.fromstring(domain.XMLDesc())

            total_read = 0
            total_write = 0

            for disk in xml.findall("./devices/disk"):
                target = disk.find("target")

                if target is None:
                    continue

                device = target.get("dev")

                if not device:
                    continue

                try:
                    stats = domain.blockStats(device)

                    total_read += stats[1]
                    total_write += stats[3]

                except libvirt.libvirtError:
                    continue

            vm_disk_read.labels(vm_name=name).set(total_read)
            vm_disk_write.labels(vm_name=name).set(total_write)

            total_received = 0
            total_transmitted = 0

            for interface in xml.findall("./devices/interface"):
                target = interface.find("target")

                if target is None:
                    continue

                device = target.get("dev")

                if not device:
                    continue

                try:
                    stats = domain.interfaceStats(device)

                    total_received += stats[0]
                    total_transmitted += stats[4]

                except libvirt.libvirtError:
                    continue

            vm_network_received.labels(vm_name=name).set(total_received)
            vm_network_transmitted.labels(vm_name=name).set(total_transmitted)

    finally:
        connection.close()

    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
