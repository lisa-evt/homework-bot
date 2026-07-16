import logging
import os
import time

import requests
from dotenv import load_dotenv
from telebot import TeleBot, types

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


def get_api_answer(timestamp):
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except
    return response.json()


def check_response(response):
    if not isinstance(response, dict):
        raise TypeError('Объект response не является словарем (dict)')
    if 'homeworks' not in response:
        raise KeyError("В ответе API отсутствует ожидаемый ключ 'homeworks'")
    if not isinstance(response['homeworks'], list):
        raise TypeError("Значение ключа 'homeworks' не является списком (list)")

    return response['homeworks']


def parse_status(homework):
    if 'homework_name' not in homework:
        raise KeyError(
        f"В ответе API отсутствует обязательное имя домашней работы 'homework_name'. "
        f"Полученные данные: {homework}"
        )

    homework_name = homework['homework_name']

    if 'status' not in homework:
        raise KeyError(
            f"В ответе API отсутствует обязательный статус работы 'status' для '{homework_name}'"
        )

    homework_status = homework['status']

    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            f"Получен неожиданный статус домашней работы '{homework_name}': '{homework_status}'"
        )

    verdict = HOMEWORK_VERDICTS[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""

    if not check_tokens():
        raise SystemExit('Критическая ошибка: отсутствуют обязательные переменные окружения!')

    # Создаем объект класса бота
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = 0 #int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                for homework in homeworks:
                    message = parse_status(homework)
                    send_message(bot, message)
            else:
                logger.debug("Нет новых статусов домашних работ для отправки.")

            timestamp = response['current_date']

        except Exception as error:
            message = f'Сбой в работе программы: {error}'

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
