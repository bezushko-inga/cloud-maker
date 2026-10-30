import time
import uuid
import pytest
import requests

BASE_URL = "http://127.0.0.1:8000"

VMS_LIMIT = 5
MEMORY_LIMIT = 4096
VCPUS_LIMIT = 4
TOTAL_MEMORY_LIMIT = 8192
TOTAL_VCPUS_LIMIT = 8


# фикстура 1: новая сессия
@pytest.fixture
def api():
    session = requests.Session()
    yield session
    session.close()


# фикстура 2: индивидуальное имя виртуальной машины
@pytest.fixture
def vm_name():
    return f"pytest-{uuid.uuid4().hex}"


# список виртуальных машин
def get_virtual_machines(api):
    response = api.get(f"{BASE_URL}/vms", timeout=10)

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)

    return response.json()


# поиск виртуальной машины по имени
def find_virtual_machine(api, name):
    for vm in get_virtual_machines(api):
        if vm["name"] == name:
            return vm

    return None


# создание виртуальной машины
def create_virtual_machine(api, name, memory=1024, vcpus=1, **kwargs):
    return api.post(
        f"{BASE_URL}/vms",
        json={"name": name, "memory": memory, "vcpus": vcpus, **kwargs},
        timeout=240,
    )


# ожидание остановки виртуальной машины до таймаута
def wait_for_stop(api, name, timeout=120):
    start = time.monotonic()

    while time.monotonic() - start < timeout:
        vm = find_virtual_machine(api, name)

        if vm is not None and vm["state"] == "stopped":
            return True

        time.sleep(2)

    return False


# остановка виртуальной машины
def stop_virtual_machine(api, name):
    vm = find_virtual_machine(api, name)

    if vm is None or vm["state"] == "stopped":
        return

    response = api.post(f"{BASE_URL}/vms/{name}/stop", timeout=10)

    assert response.status_code == 200, response.text
    assert wait_for_stop(api, name)


# удаление виртуальной машины
def delete_virtual_machine(api, name):
    vm = find_virtual_machine(api, name)

    if vm is None:
        return

    stop_virtual_machine(api, name)

    response = api.delete(f"{BASE_URL}/vms/{name}", timeout=10)

    assert response.status_code == 200, response.text
    assert find_virtual_machine(api, name) is None


# фикстура 3: создание виртуальной машины перед тестом и удаление после
@pytest.fixture
def created_virtual_machine(api, vm_name):
    try:
        response = create_virtual_machine(api, vm_name)

        assert response.status_code == 200, response.text

        yield vm_name

    finally:
        delete_virtual_machine(api, vm_name)


# ТЕСТ 1: получение списка виртуальных машин
def test_get_virtual_machines(api):
    vms = get_virtual_machines(api)

    for vm in vms:
        assert "name" in vm
        assert "state" in vm
        assert vm["state"] in ("running", "stopped")


# ТЕСТ 2: создание виртуальной машины
def test_create_virtual_machine(api, created_virtual_machine):
    vm = find_virtual_machine(api, created_virtual_machine)

    assert vm is not None
    assert vm["name"] == created_virtual_machine
    assert vm["state"] == "running"


# ТЕСТ 3: создание ВМ с заданными ресурсами
def test_create_vm_with_custom_resources(api, vm_name):
    try:
        response = create_virtual_machine(api, vm_name, memory=2048, vcpus=2)

        assert response.status_code == 200, response.text

        vm = find_virtual_machine(api, vm_name)

        assert vm is not None
        assert vm["name"] == vm_name
        assert vm["state"] == "running"

    finally:
        delete_virtual_machine(api, vm_name)


# ТЕСТ 4: создание ВМ с заданным hostname
def test_create_vm_with_hostname(api, vm_name):
    try:
        response = create_virtual_machine(api, vm_name, hostname="pytest-host")

        assert response.status_code == 200, response.text
        assert find_virtual_machine(api, vm_name) is not None

    finally:
        delete_virtual_machine(api, vm_name)


# ТЕСТ 5: создание ВМ с заданным SSH-ключом
def test_create_vm_with_ssh_key(api, vm_name):
    try:
        response = create_virtual_machine(
            api, vm_name, ssh_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGExampleTestKey"
        )

        assert response.status_code == 200, response.text
        assert find_virtual_machine(api, vm_name) is not None

    finally:
        delete_virtual_machine(api, vm_name)


# ТЕСТ 6: создание ВМ с заданным user_data
def test_create_vm_with_user_data(api, vm_name):
    try:
        response = create_virtual_machine(
            api, vm_name, user_data="#cloud-config\npackages:\n  - curl\n"
        )

        assert response.status_code == 200, response.text
        assert find_virtual_machine(api, vm_name) is not None

    finally:
        delete_virtual_machine(api, vm_name)


# ТЕСТ 7: создание дубликата ВМ
def test_duplicate_vm(api, created_virtual_machine):
    response = create_virtual_machine(api, created_virtual_machine)

    assert response.status_code == 409
    assert find_virtual_machine(api, created_virtual_machine) is not None


# ТЕСТ 8: создание ВМ с некорректным именем
@pytest.mark.parametrize(
    "name", ["", "invalid name", "invalid/name", "invalid.name", "invalid@name"]
)
def test_invalid_name(api, name):
    response = create_virtual_machine(api, name)

    assert response.status_code == 400


# ТЕСТ 9: создание ВМ с некорректным объёмом памяти
@pytest.mark.parametrize("memory", [0, 128, 511, MEMORY_LIMIT + 1, 99999])
def test_invalid_memory(api, vm_name, memory):
    response = create_virtual_machine(api, vm_name, memory=memory)

    assert response.status_code == 400
    assert find_virtual_machine(api, vm_name) is None


# ТЕСТ 10: создание ВМ с некорректным количеством vCPU
@pytest.mark.parametrize("vcpus", [0, -1, VCPUS_LIMIT + 1, 999])
def test_invalid_vcpus(api, vm_name, vcpus):
    response = create_virtual_machine(api, vm_name, vcpus=vcpus)

    assert response.status_code == 400
    assert find_virtual_machine(api, vm_name) is None


# ТЕСТ 11: создание ВМ с минимальными допустимыми ресурсами
def test_minimum_resources(api, vm_name):
    try:
        response = create_virtual_machine(api, vm_name, memory=512, vcpus=1)

        assert response.status_code == 200, response.text
        assert find_virtual_machine(api, vm_name) is not None

    finally:
        delete_virtual_machine(api, vm_name)


# ТЕСТ 12: создание ВМ с максимальными допустимыми ресурсами
@pytest.mark.slow
def test_maximum_resources(api, vm_name):
    try:
        response = create_virtual_machine(
            api, vm_name, memory=MEMORY_LIMIT, vcpus=VCPUS_LIMIT
        )

        assert response.status_code == 200, response.text
        assert find_virtual_machine(api, vm_name) is not None

    finally:
        delete_virtual_machine(api, vm_name)


# ТЕСТ 13: остановка работающей ВМ
def test_stop_vm(api, created_virtual_machine):
    response = api.post(f"{BASE_URL}/vms/{created_virtual_machine}/stop", timeout=10)

    assert response.status_code == 200, response.text
    assert wait_for_stop(api, created_virtual_machine)


# ТЕСТ 14: повторная остановка ВМ
def test_stop_already_stopped_vm(api, created_virtual_machine):
    stop_virtual_machine(api, created_virtual_machine)

    response = api.post(f"{BASE_URL}/vms/{created_virtual_machine}/stop", timeout=10)

    assert response.status_code == 409


# ТЕСТ 15: остановка несуществующей ВМ
def test_stop_nonexistent_vm(api, vm_name):
    response = api.post(f"{BASE_URL}/vms/{vm_name}/stop", timeout=10)

    assert response.status_code == 404


# ТЕСТ 16: попытка удаления работающей ВМ
def test_delete_running_vm(api, created_virtual_machine):
    response = api.delete(f"{BASE_URL}/vms/{created_virtual_machine}", timeout=10)

    assert response.status_code == 409
    assert find_virtual_machine(api, created_virtual_machine) is not None


# ТЕСТ 17: удаление остановленной ВМ
def test_delete_stopped_vm(api, created_virtual_machine):
    stop_virtual_machine(api, created_virtual_machine)

    response = api.delete(f"{BASE_URL}/vms/{created_virtual_machine}", timeout=10)

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "deleted"
    assert find_virtual_machine(api, created_virtual_machine) is None


# ТЕСТ 18: удаление несуществующей ВМ
def test_delete_nonexistent_vm(api, vm_name):
    response = api.delete(f"{BASE_URL}/vms/{vm_name}", timeout=10)

    assert response.status_code == 404


# ТЕСТ 19: полный жизненный цикл ВМ
def test_vm_lifecycle(api, created_virtual_machine):
    vm = find_virtual_machine(api, created_virtual_machine)

    assert vm is not None
    assert vm["state"] == "running"

    stop_virtual_machine(api, created_virtual_machine)

    vm = find_virtual_machine(api, created_virtual_machine)

    assert vm is not None
    assert vm["state"] == "stopped"

    response = api.delete(f"{BASE_URL}/vms/{created_virtual_machine}", timeout=10)

    assert response.status_code == 200
    assert find_virtual_machine(api, created_virtual_machine) is None


# ТЕСТ 20: ограничение количества виртуальных машин
@pytest.mark.slow
def test_vm_count_limit(api):
    names = [f"pytest-limit-{uuid.uuid4().hex[:8]}" for _ in range(VMS_LIMIT + 1)]

    if get_virtual_machines(api):
        pytest.skip("Test requires an empty libvirt environment")

    try:
        for name in names[:VMS_LIMIT]:
            response = create_virtual_machine(api, name, memory=512, vcpus=1)

            assert response.status_code == 200, response.text

        assert len(get_virtual_machines(api)) == VMS_LIMIT

        response = create_virtual_machine(api, names[VMS_LIMIT], memory=512, vcpus=1)

        assert response.status_code == 409
        assert find_virtual_machine(api, names[VMS_LIMIT]) is None

    finally:
        for name in names:
            delete_virtual_machine(api, name)


# ТЕСТ 21: ограничение общего объёма памяти
@pytest.mark.slow
def test_total_memory_limit(api):
    names = [f"pytest-memory-{uuid.uuid4().hex[:8]}" for _ in range(3)]

    if get_virtual_machines(api):
        pytest.skip("Test requires an empty libvirt environment")

    try:
        for name in names[:2]:
            response = create_virtual_machine(api, name, memory=MEMORY_LIMIT, vcpus=1)

            assert response.status_code == 200, response.text

        response = create_virtual_machine(api, names[2], memory=512, vcpus=1)

        assert response.status_code == 409
        assert find_virtual_machine(api, names[2]) is None

    finally:
        for name in names:
            delete_virtual_machine(api, name)


# ТЕСТ 22: ограничение общего количества vCPU
@pytest.mark.slow
def test_total_vcpus_limit(api):
    names = [f"pytest-cpu-{uuid.uuid4().hex[:8]}" for _ in range(3)]

    if get_virtual_machines(api):
        pytest.skip("Test requires an empty libvirt environment")

    try:
        for name in names[:2]:
            response = create_virtual_machine(api, name, memory=512, vcpus=VCPUS_LIMIT)

            assert response.status_code == 200, response.text

        response = create_virtual_machine(api, names[2], memory=512, vcpus=1)

        assert response.status_code == 409
        assert find_virtual_machine(api, names[2]) is None

    finally:
        for name in names:
            delete_virtual_machine(api, name)
