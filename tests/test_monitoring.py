import time
import uuid
import pytest
import requests

from prometheus_client.parser import text_string_to_metric_families

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


# получение метрик Prometheus
def get_metrics(api):
    return api.get(f"{BASE_URL}/metrics", timeout=20)


# поиск метрики виртуальной машины
def find_metric(api, metric_name, vm_name):
    response = get_metrics(api)

    assert response.status_code == 200, response.text

    for family in text_string_to_metric_families(response.text):
        for sample in family.samples:
            if sample.name == metric_name and sample.labels.get("vm_name") == vm_name:
                return sample.value

    return None


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


# фикстура 3: создание виртуальной машины перед тестами и удаление после
@pytest.fixture(scope="module")
def created_virtual_machine():
    session = requests.Session()
    name = f"pytest-{uuid.uuid4().hex}"

    try:
        response = create_virtual_machine(session, name)

        assert response.status_code == 200, response.text

        yield name

    finally:
        try:
            delete_virtual_machine(session, name)
        finally:
            session.close()


# ТЕСТ 1: доступность эндпоинта Prometheus
def test_metrics_endpoint(api):
    response = get_metrics(api)

    assert response.status_code == 200, response.text


# ТЕСТ 2: формат ответа Prometheus
def test_metrics_content_type(api):
    response = get_metrics(api)

    assert response.status_code == 200, response.text
    assert "text/plain" in response.headers["Content-Type"]


# ТЕСТ 3: наличие всех шести метрик
def test_metrics_names(api):
    response = get_metrics(api)

    assert response.status_code == 200, response.text

    metrics = [
        "cloudmaker_vm_memory_bytes",
        "cloudmaker_vm_cpu_time_seconds",
        "cloudmaker_vm_disk_read_bytes_total",
        "cloudmaker_vm_disk_write_bytes_total",
        "cloudmaker_vm_network_received_bytes_total",
        "cloudmaker_vm_network_transmitted_bytes_total"
    ]

    for metric in metrics:
        assert metric in response.text


# ТЕСТ 4: корректность формата метрик
def test_metrics_format(api):
    response = get_metrics(api)

    assert response.status_code == 200, response.text

    families = list(text_string_to_metric_families(response.text))

    assert len(families) > 0


# ТЕСТ 5: метрики работающей виртуальной машины
def test_running_vm_metrics(api, created_virtual_machine):
    response = get_metrics(api)

    assert response.status_code == 200, response.text

    assert f'vm_name="{created_virtual_machine}"' in response.text


# ТЕСТ 6: выделенная память виртуальной машины
def test_vm_memory_metric(api, created_virtual_machine):
    memory = find_metric(
        api,
        "cloudmaker_vm_memory_bytes",
        created_virtual_machine,
    )

    assert memory is not None
    assert isinstance(memory, (int, float))
    assert memory == 1024 * 1024 * 1024


# ТЕСТ 7: время использования CPU
def test_vm_cpu_metric(api, created_virtual_machine):
    cpu = find_metric(
        api,
        "cloudmaker_vm_cpu_time_seconds",
        created_virtual_machine,
    )

    assert cpu is not None
    assert isinstance(cpu, (int, float))
    assert cpu >= 0


# ТЕСТ 8: количество прочитанных байтов
def test_vm_disk_read_metric(api, created_virtual_machine):
    disk_read = find_metric(
        api,
        "cloudmaker_vm_disk_read_bytes_total",
        created_virtual_machine,
    )

    assert disk_read is not None
    assert isinstance(disk_read, (int, float))
    assert disk_read >= 0


# ТЕСТ 9: количество записанных байтов
def test_vm_disk_write_metric(api, created_virtual_machine):
    disk_write = find_metric(
        api,
        "cloudmaker_vm_disk_write_bytes_total",
        created_virtual_machine,
    )

    assert disk_write is not None
    assert isinstance(disk_write, (int, float))
    assert disk_write >= 0


# ТЕСТ 10: количество полученных байтов
def test_vm_network_received_metric(api, created_virtual_machine):
    received = find_metric(
        api,
        "cloudmaker_vm_network_received_bytes_total",
        created_virtual_machine,
    )

    assert received is not None
    assert received >= 0


# ТЕСТ 11: количество отправленных байтов
def test_vm_network_transmitted_metric(api, created_virtual_machine):
    transmitted = find_metric(
        api,
        "cloudmaker_vm_network_transmitted_bytes_total",
        created_virtual_machine,
    )

    assert transmitted is not None
    assert transmitted >= 0


# ТЕСТ 12: увеличение времени использования CPU
def test_vm_cpu_time_increases(api, created_virtual_machine):
    cpu_time1 = find_metric(
        api,
        "cloudmaker_vm_cpu_time_seconds",
        created_virtual_machine,
    )

    assert cpu_time1 is not None

    time.sleep(2)

    cpu_time2 = find_metric(
        api,
        "cloudmaker_vm_cpu_time_seconds",
        created_virtual_machine,
    )

    assert cpu_time2 is not None
    assert cpu_time2 >= cpu_time1


# ТЕСТ 13: остановленная виртуальная машина не экспортируется
def test_stopped_vm_metrics(api, created_virtual_machine):
    stop_virtual_machine(api, created_virtual_machine)

    response = get_metrics(api)

    assert response.status_code == 200, response.text
    assert f'vm_name="{created_virtual_machine}"' not in response.text


# ТЕСТ 14: несуществующая виртуальная машина не экспортируется
def test_nonexistent_vm_metrics(api, vm_name):
    response = get_metrics(api)

    assert response.status_code == 200, response.text
    assert f'vm_name="{vm_name}"' not in response.text
