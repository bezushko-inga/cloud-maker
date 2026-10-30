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


# фикстура 2: индивидуальное имя образа
@pytest.fixture
def image_name():
    return f"pytest-image-{uuid.uuid4().hex}"


# фикстура 3: временный файл образа
@pytest.fixture
def image_file(tmp_path):
    path = tmp_path / "test-image.qcow2"
    path.touch()

    return path


# список зарегистрированных образов
def get_images(api):
    response = api.get(f"{BASE_URL}/images", timeout=10)

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), dict)

    return response.json()


# поиск образа по имени
def find_image(api, name):
    return get_images(api).get(name)


# регистрация образа
def register_image(api, name, path):
    return api.post(
        f"{BASE_URL}/images", json={"name": name, "path": str(path)}, timeout=10
    )


# ТЕСТ 1: получение списка зарегистрированных образов
def test_get_images(api):
    images = get_images(api)

    assert isinstance(images, dict)

    for name, path in images.items():
        assert isinstance(name, str)
        assert isinstance(path, str)


# ТЕСТ 2: наличие образа по умолчанию
def test_default_image(api):
    images = get_images(api)

    assert "default" in images
    assert isinstance(images["default"], str)
    assert images["default"]


# ТЕСТ 3: регистрация образа в формате qcow2
def test_register_qcow2_image(api, image_name, image_file):
    response = register_image(api, image_name, image_file)

    assert response.status_code == 200, response.text
    assert find_image(api, image_name) == str(image_file)


# ТЕСТ 4: регистрация образа в формате img
def test_register_img_image(api, image_name, tmp_path):
    path = tmp_path / "test-image.img"
    path.touch()

    response = register_image(api, image_name, path)

    assert response.status_code == 200, response.text
    assert find_image(api, image_name) == str(path)


# ТЕСТ 5: регистрация образа с дефисом в имени
def test_image_name_with_hyphen(api, image_file):
    name = f"pytest-image-{uuid.uuid4().hex}"

    response = register_image(api, name, image_file)

    assert response.status_code == 200, response.text
    assert find_image(api, name) == str(image_file)


# ТЕСТ 6: регистрация образа с подчёркиванием в имени
def test_image_name_with_underscore(api, image_file):
    name = f"pytest_image_{uuid.uuid4().hex}"

    response = register_image(api, name, image_file)

    assert response.status_code == 200, response.text
    assert find_image(api, name) == str(image_file)


# ТЕСТ 7: повторная регистрация образа
def test_duplicate_image(api, image_name, image_file):
    response = register_image(api, image_name, image_file)

    assert response.status_code == 200, response.text

    response = register_image(api, image_name, image_file)

    assert response.status_code == 409
    assert find_image(api, image_name) == str(image_file)


# ТЕСТ 8: попытка регистрации образа с зарезервированным именем
def test_reserved_image_name(api, image_file):
    response = register_image(api, "default", image_file)

    assert response.status_code == 409


# ТЕСТ 9: регистрация образа с некорректным именем
@pytest.mark.parametrize(
    "name", ["", "invalid name", "invalid/name", "invalid.name", "invalid@name"]
)
def test_invalid_image_name(api, name, image_file):
    response = register_image(api, name, image_file)

    assert response.status_code == 400


# ТЕСТ 10: регистрация несуществующего образа
def test_nonexistent_image_file(api, image_name, tmp_path):
    path = tmp_path / "nonexistent.qcow2"

    response = register_image(api, image_name, path)

    assert response.status_code == 404
    assert find_image(api, image_name) is None


# ТЕСТ 11: регистрация образа с неподдерживаемым расширением
@pytest.mark.parametrize("extension", [".txt", ".iso", ".zip", ".json", ".pdf"])
def test_invalid_image_extension(api, image_name, tmp_path, extension):
    path = tmp_path / f"test-image{extension}"
    path.touch()

    response = register_image(api, image_name, path)

    assert response.status_code == 400
    assert find_image(api, image_name) is None


# ТЕСТ 12: регистрация образа без расширения
def test_image_without_extension(api, image_name, tmp_path):
    path = tmp_path / "test-image"
    path.touch()

    response = register_image(api, image_name, path)

    assert response.status_code == 400
    assert find_image(api, image_name) is None


# ТЕСТ 13: проверка сохранения зарегистрированного образа
def test_registered_image_in_list(api, image_name, image_file):
    response = register_image(api, image_name, image_file)

    assert response.status_code == 200, response.text

    images = get_images(api)

    assert image_name in images
    assert images[image_name] == str(image_file)


# ТЕСТ 14: регистрация нескольких образов
def test_register_multiple_images(api, tmp_path):
    names = [f"pytest-image-{uuid.uuid4().hex}" for _ in range(3)]

    paths = [tmp_path / f"test-image-{i}.qcow2" for i in range(3)]

    for path in paths:
        path.touch()

    for name, path in zip(names, paths):
        response = register_image(api, name, path)

        assert response.status_code == 200, response.text

    images = get_images(api)

    for name, path in zip(names, paths):
        assert name in images
        assert images[name] == str(path)


# ТЕСТ 15: регистрация образов с разными расширениями
def test_register_different_formats(api, tmp_path):
    name_img = f"pytest-img-{uuid.uuid4().hex}"
    name_qcow2 = f"pytest-qcow2-{uuid.uuid4().hex}"

    path_img = tmp_path / "test-image.img"
    path_qcow2 = tmp_path / "test-image.qcow2"

    path_img.touch()
    path_qcow2.touch()

    response_img = register_image(api, name_img, path_img)
    response_qcow2 = register_image(api, name_qcow2, path_qcow2)

    assert response_img.status_code == 200, response_img.text
    assert response_qcow2.status_code == 200, response_qcow2.text

    images = get_images(api)

    assert images[name_img] == str(path_img)
    assert images[name_qcow2] == str(path_qcow2)
