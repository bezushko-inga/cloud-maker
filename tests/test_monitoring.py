import time
import uuid
import pytest
import requests

BASE_URL = "http://127.0.0.1:8000"


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
def create_virtual_machine(api, name, memory=1024, vcpus=1):
    return api.post(
        f"{BASE_URL}/vms",
        json={"name": name, "memory": memory, "vcpus": vcpus},
        timeout=240,
    )


# получение статистики виртуальной машины
def get_virtual_machine_stats(api, name):
    return api.get(f"{BASE_URL}/vms/{name}/stats", timeout=20)


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


# фикстура 4: создание и остановка виртуальной машины перед тестом
@pytest.fixture
def stopped_virtual_machine(api, created_virtual_machine):
    stop_virtual_machine(api, created_virtual_machine)

    return created_virtual_machine


# ТЕСТ 1: получение статистики работающей виртуальной машины
def test_get_running_vm_stats(api, created_virtual_machine):
    response = get_virtual_machine_stats(api, created_virtual_machine)

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)

    stats = response.json()

    assert "name" in stats
    assert "state" in stats
    assert "memory_mb" in stats
    assert "vcpus" in stats
    assert "cpu_time_ns" in stats
    assert "cpu_usage_percent" in stats
    assert "disk" in stats
    assert "network" in stats


# ТЕСТ 2: проверка имени виртуальной машины в статистике
def test_vm_stats_name(api, created_virtual_machine):
    response = get_virtual_machine_stats(api, created_virtual_machine)

    assert response.status_code == 200, response.text
    assert response.json()["name"] == created_virtual_machine


# ТЕСТ 3: проверка состояния работающей виртуальной машины
def test_running_vm_state(api, created_virtual_machine):
    response = get_virtual_machine_stats(api, created_virtual_machine)

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "running"


# ТЕСТ 4: проверка выделенной памяти
def test_vm_memory(api, created_virtual_machine):
    response = get_virtual_machine_stats(api, created_virtual_machine)

    assert response.status_code == 200, response.text

    stats = response.json()

    assert isinstance(stats["memory_mb"], (int, float))
    assert stats["memory_mb"] == 1024


# ТЕСТ 5: проверка количества vCPU
def test_vm_vcpus(api, created_virtual_machine):
    response = get_virtual_machine_stats(api, created_virtual_machine)

    assert response.status_code == 200, response.text

    stats = response.json()

    assert isinstance(stats["vcpus"], int)
    assert stats["vcpus"] == 1


# ТЕСТ 6: проверка времени работы CPU
def test_vm_cpu_time(api, created_virtual_machine):
    response = get_virtual_machine_stats(api, created_virtual_machine)

    assert response.status_code == 200, response.text

    stats = response.json()

    assert isinstance(stats["cpu_time_ns"], int)
    assert stats["cpu_time_ns"] >= 0


# ТЕСТ 7: проверка загрузки CPU
def test_vm_cpu_usage(api, created_virtual_machine):
    response = get_virtual_machine_stats(api, created_virtual_machine)

    assert response.status_code == 200, response.text

    stats = response.json()

    assert isinstance(stats["cpu_usage_percent"], (int, float))
    assert 0 <= stats["cpu_usage_percent"] <= 100


# ТЕСТ 8: проверка дисковой статистики
def test_vm_disk_stats(api, created_virtual_machine):
    response = get_virtual_machine_stats(api, created_virtual_machine)

    assert response.status_code == 200, response.text

    disk = response.json()["disk"]

    assert isinstance(disk, dict)

    for value in disk.values():
        assert isinstance(value, (int, float))
        assert value >= 0


# ТЕСТ 9: проверка сетевой статистики
def test_vm_network_stats(api, created_virtual_machine):
    response = get_virtual_machine_stats(api, created_virtual_machine)

    assert response.status_code == 200, response.text

    network = response.json()["network"]

    assert isinstance(network, dict)

    for value in network.values():
        assert isinstance(value, (int, float))
        assert value >= 0


# ТЕСТ 10: проверка изменения времени CPU
def test_vm_cpu_time_increases(api, created_virtual_machine):
    response1 = get_virtual_machine_stats(api, created_virtual_machine)

    assert response1.status_code == 200, response1.text

    cpu_time1 = response1.json()["cpu_time_ns"]

    time.sleep(2)

    response2 = get_virtual_machine_stats(api, created_virtual_machine)

    assert response2.status_code == 200, response2.text

    cpu_time2 = response2.json()["cpu_time_ns"]

    assert cpu_time2 >= cpu_time1


# ТЕСТ 11: получение статистики остановленной виртуальной машины
def test_get_stopped_vm_stats(api, stopped_virtual_machine):
    response = get_virtual_machine_stats(api, stopped_virtual_machine)

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)

    stats = response.json()

    assert stats["name"] == stopped_virtual_machine
    assert stats["state"] == "stopped"


# ТЕСТ 12: загрузка CPU остановленной виртуальной машины
def test_stopped_vm_cpu_usage(api, stopped_virtual_machine):
    response = get_virtual_machine_stats(api, stopped_virtual_machine)

    assert response.status_code == 200, response.text
    assert response.json()["cpu_usage_percent"] == 0


# ТЕСТ 13: дисковая статистика остановленной виртуальной машины
def test_stopped_vm_disk_stats(api, stopped_virtual_machine):
    response = get_virtual_machine_stats(api, stopped_virtual_machine)

    assert response.status_code == 200, response.text
    assert response.json()["disk"] is None


# ТЕСТ 14: сетевая статистика остановленной виртуальной машины
def test_stopped_vm_network_stats(api, stopped_virtual_machine):
    response = get_virtual_machine_stats(api, stopped_virtual_machine)

    assert response.status_code == 200, response.text
    assert response.json()["network"] is None


# ТЕСТ 15: ресурсы остановленной виртуальной машины
def test_stopped_vm_resources(api, stopped_virtual_machine):
    response = get_virtual_machine_stats(api, stopped_virtual_machine)

    assert response.status_code == 200, response.text

    stats = response.json()

    assert stats["memory_mb"] == 1024
    assert stats["vcpus"] == 1


# ТЕСТ 16: мониторинг несуществующей виртуальной машины
def test_nonexistent_vm_stats(api, vm_name):
    response = get_virtual_machine_stats(api, vm_name)

    assert response.status_code == 404


# ТЕСТ 17: мониторинг удалённой виртуальной машины
def test_deleted_vm_stats(api, created_virtual_machine):
    stop_virtual_machine(api, created_virtual_machine)

    response = api.delete(f"{BASE_URL}/vms/{created_virtual_machine}", timeout=10)

    assert response.status_code == 200, response.text

    response = get_virtual_machine_stats(api, created_virtual_machine)

    assert response.status_code == 404


# ТЕСТ 18: мониторинг виртуальной машины с заданными ресурсами
def test_custom_vm_resources_stats(api, vm_name):
    try:
        response = create_virtual_machine(api, vm_name, memory=2048, vcpus=2)

        assert response.status_code == 200, response.text

        response = get_virtual_machine_stats(api, vm_name)

        assert response.status_code == 200, response.text

        stats = response.json()

        assert stats["memory_mb"] == 2048
        assert stats["vcpus"] == 2

    finally:
        delete_virtual_machine(api, vm_name)
