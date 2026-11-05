# Cloud Maker

Cloud Maker - приложение HTTP API, разработанное в рамках курса "Современные Облачные Технологии", для создания, удаления и управления виртуальными машинами на Linux-хосте с QEMU/KVM.

Условие задания сформулировано в файле `CloudMaker.pdf`. В решении реализованы следующие дополнительные фичи:

### [ 1 ] Приложение, обрабатывающее запросы
Реализация приложения HTTP API, с помощью которого можно управлять виртуальными машинами, а именно создавать, останавливать и удалять их.

Код задания в файле `request-handler-app/main.py`. Реализованы четыре основные функции:

- получение списка виртуальных машин: `get_virtual_machines()`;
- создание виртуальной машины: `create_virtual_machine(vm: VirtualMachine)`;
- остановка виртуальный машины: `stop_virtual_machine(name: str)`;
- удаление виртуальной машины: `delete_virtual_machine(name: str)`.

### [ 2 ] cloud-init при запуске ВМ

Добавлена возможность при создании виртуальный машины задавать `hostname`, `ssh-key`, `user_data`. Реализация в файле `request-handler-app/main.py` в функции `create_virtual_machine(vm: VirtualMachine)`.

### [ 6 ] Восстановление состояния

После перезапуска приложения виртуальные машины должны сохраняться. Для этого при каждом запросе открывается соединение с `libvirt`, получается все зарегистрированные виртуальные машины и определяются их состояние. Реализация в файле `request-handler-app/main.py`.

### [ 7 ] Возможность добавлять образы

Добавлена возможность регистрации новых образов виртуальных машин. Реализовано в файле `request-handler-app/main.py`. Имеются две функции:

- получение списка зарегистрированных образов: `get_images()`;
- регистрация нового образа: `register_image(image: Image)`.

### [ 8 ] Мониторинг ресурсов 

Реализован мониторинг использования ресурсов виртуальных машин с помощью libvirt, Prometheus и Grafana.

В файле `request-handler-app/main.py` реализована функция `get_metrics()`: предоставление метрик всех работающих виртуальных машин в формате Prometheus.

Собираются следующие метрики:

* время использования CPU;
* объем выделенной оперативной памяти;
* количество прочитанных и записанных байтов на диске;
* количество полученных и отправленных байтов по сети.

Конфигурационные файлы Prometheus и Grafana, а также готовый `dashboard` находятся в директории `monitoring-files/`.

### [ 9 ] Ограничение ресурсов (квоты)

Добавлено ограничение ресурсов, которые могут выделяться виртуальным машинам. В файле `request-handler-app/main.py` проверяются следующие ограничения:

- выделенная память одной виртуальной машине от 512 Мб до 4096 Мб;
- выделенное количество процессоров от 1 до 4;
- количество виртуальных машин до 5;
- суммарное количество выданной памяти до 8192 Мб;
- суммарное количество процессоров до 8.
  
### [ 11 ] Скрипт для проверки

Существует единый скрипт `scripts/run-all-tests.sh`, позволяющий протестировать Cloud Maker. 

### [ 12 ] Скрипт очистки результатов тестирования

Существует скрипт `scripts/resource-cleanup.py` для удаления ресурсов, оставшихся после тестирования.
  
## Структура проекта

```text
cloud-maker/
├── request-handler-app/
│   └── main.py                 # FastAPI-приложение
├── monitoring-files/
│   ├── prometheus-config.yml   # Конфигурация Prometheus
│   ├── grafana-datasource.yml  # Подключение Grafana к Prometheus
│   └── grafana-dashboard.json  # Dashboard с шестью графиками
├── tests/
│   ├── test_vms.py             # Тест управления вирт. машинами 
│   ├── test_images.py          # Тест регистрации образов
│   └── test_monitoring.py      # Тест мониторинга
├── scripts/
│   ├── run-all-tests.sh        # Скрипт запуска тестов
│   ├── setup-environment.sh    # Скрипт настройки окружения 
│   ├── vm-setup-example.sh     # Скрипт создания вирт. машины
│   └── resource-cleanup.py     # Скрипт очистки ресурсов
├── README.md
├── CloudMaker.pdf              # Формулировка задания
└── .gitignore
```

## Установка и запуск

1. Клонирование репозитория и перемещение в папку проекта:
   
```bash
git clone https://github.com/bezushko-inga/cloud-maker.git
cd cloud-maker
```

2. Запуск скрипта для настройки окружения. В нем скачиваются все необходимые зависимости и создается окружение:
   
```bash
bash scripts/setup-environment.sh
```

3. Активация окружения:
   
```bash
source .venv/bin/activate
```

## Подготовка образа по умолчанию и настройка прав доступа

1. Скачать базовый образ Ubuntu 24.04 LTS для создания виртуальных машин:

```bash
wget -O noble-server-cloudimg-amd64.img https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
```

2. Добавление текущего пользователя в группы libvirt и kvm для управления виртуальными машинами:

```bash
sudo usermod -aG libvirt,kvm "$USER"
```

3. Создание директории для хранения виртуальных дисков и файлов cloud-init:

```bash
sudo mkdir -p /var/lib/libvirt/images/cloud-maker
```

4. Предоставление текущего пользователя права на запись в директорию:

```bash
sudo chown "$USER":"$(id -gn)" /var/lib/libvirt/images/cloud-maker
```

## Тестирование обязательного задания

В рамках обязательного задания был написан скрипт для создания и настройки экспериментальной виртуальный машины.

1. Запуск скрипта:

```bash
bash scripts/vm-setup-example.sh example-vm 2048 2 15G
```

`scripts/vm-setup-example.sh` получает на вход четыре параметра: имя виртуальной машины, объем оперативной памяти в Мб, количество виртуальных процессоров и размер виртуального диска.

2. Очистка ресурсов после тестирования:

```bash
python scripts/resource-cleanup.py
```

## Тестирование Cloud Maker

1. Запуск приложения (вручную можно посмотреть по адресу `http://127.0.0.1:8000/docs`):

```bash
uvicorn main:app --app-dir request-handler-app --host 127.0.0.1 --port 8000
```

2. Активация виртуального окружения и запуск скрипта автоматического тестирования во втором терминале:

```bash
source .venv/bin/activate
bash scripts/run-all-tests.sh
```

3. Очистка ресурсов после тестирования:

```bash
python scripts/resource-cleanup.py
```

## Запуск мониторинга метрик

Для мониторинга ресурсов виртуальных машин используются Prometheus и Grafana. FastAPI, Prometheus и Grafana при этом запускаются одновременно на одном Linux-хосте.

1. Настройка Prometheus. Копирование конфигурационного файла:

```bash
sudo cp monitoring-files/prometheus-config.yml /etc/prometheus/prometheus.yml
```

2. Настройка Prometheus. Проверка конфигурации:

```bash
promtool check config /etc/prometheus/prometheus.yml
```

3. Настройка Prometheus. Запуск Prometheus:

```bash
sudo systemctl enable --now prometheus
sudo systemctl restart prometheus
```

Веб-интерфейс Prometheus доступен по адресу `http://127.0.0.1:9090`. В разделе Status -> Targets можно проверить, что приложение cloud-maker имеет статус UP.

4. Настройка Grafana. Копирование конфигурации:

```bash
sudo cp monitoring-files/grafana-datasource.yml /etc/grafana/provisioning/datasources/cloud-maker.yml
```

5. Настройка Grafana. Запуск Grafana:

```bash
sudo systemctl enable --now grafana-server
sudo systemctl restart grafana-server
```

6. Импорт дашборда:

Открываем Grafana по адресу `http://127.0.0.1:3000`. Переходим в Dashboards -> New -> Import и загружаем файл `monitoring-files/grafana-dashboard.json`. После создания виртуальной машины её метрики должны появиться в Prometheus и на графиках Grafana.
