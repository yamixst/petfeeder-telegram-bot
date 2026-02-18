#!/usr/bin/env python3

import tinytuya

# Данные вашей кормушки
DEVICE_ID = ''
IP_ADDRESS = '' # статический IP кормушки
LOCAL_KEY = ''

# Подключаемся к кормушке (версия 3.3 чаще всего в новых устройствах)
d = tinytuya.OutletDevice(DEVICE_ID, IP_ADDRESS, LOCAL_KEY)
d.set_version(3.5)

# Получаем текущее состояние, чтобы проверить связь
status = d.status()
print("Текущий статус:", status)

# Команда на выдачу 1 порции (DP 101 — пример для многих кормушек)
# Значение — количество порций
payload = d.generate_payload(tinytuya.CONTROL, {'3': 1})
d.send(payload)

print("Команда на кормление отправлена!")
