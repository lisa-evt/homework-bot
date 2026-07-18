"""Телеграм-бот для отслеживания статусов проверки ДЗ на Яндекс.Практикуме."""

import logging
import os
import sys
import time
from http import HTTPStatus
from json import JSONDecodeError

import requests
from dotenv import load_dotenv
from requests.exceptions import RequestException
from telebot import TeleBot
from telebot.apihelper import ApiException

from exceptions import APIConnectionError, APIResponseError

load_dotenv()


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - [%(name)s] - [%(levelname)s] - %(message)s",
    handlers=(logging.StreamHandler(sys.stdout),),
)

logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RETRY_PERIOD_IN_SECONDS = 600
RETRY_PERIOD = RETRY_PERIOD_IN_SECONDS

ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}

HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}


def check_tokens():
    """Проверяет доступность переменных окружения, необходимых для работы бота.

    Возвращает:
        bool: True, если все обязательные переменные окружения найдены,
        иначе False.
    """
    tokens = {
        "PRACTICUM_TOKEN": PRACTICUM_TOKEN,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }

    valid_tokens = True

    for token_name, token_value in tokens.items():
        if not token_value:
            logger.critical(
                'Отсутствует обязательная переменная окружения: "%s"',
                token_name,
            )
            valid_tokens = False

    return valid_tokens


def send_message(bot, message):
    """Отправляет текстовое сообщение в Telegram-чат.

    Аргументы:
        bot (TeleBot): Экземпляр класса TeleBot для отправки сообщения.
        message (str): Текст отправляемого сообщения.

    Возвращает:
        bool: True, если сообщение было отправлено, иначе False.
    """
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except (ApiException, RequestException) as error:
        logger.exception('Сбой при отправке сообщения в Telegram: "%s"', error)
        return False

    logger.debug('Удачная отправка сообщения в Telegram: "%s"', message)
    return True


def get_api_answer(timestamp):
    """Запрашивает данные у API за указанный период времени.

    Args:
        timestamp (int/str): Временная метка для фильтрации данных
            (параметр 'from_date').

    Returns:
        dict: Ответ API в формате JSON (десериализованный в словарь).

    Raises:
        APIConnectionError: Если API вернул статус-код, отличный от 200.
        requests.exceptions.RequestException: При проблемах с сетью.
    """
    payload = {"from_date": timestamp}
    try:
        response = requests.get(
            ENDPOINT, headers=HEADERS, params=payload, timeout=10
        )
    except RequestException as error:
        error_msg = f"Сбой при запросе к эндпоинту: {error}"
        raise APIConnectionError(error_msg) from error

    if response.status_code != HTTPStatus.OK:
        raise APIConnectionError(
            f"Эндпоинт {ENDPOINT} вернул статус-код "
            f"{response.status_code}. Параметры: {payload}"
        )

    try:
        return response.json()
    except JSONDecodeError as json_error:
        raise APIResponseError(
            f"Ответ API не преобразуется в JSON: {json_error}"
        ) from json_error


def check_response(response):
    """Проверяет ответ API на соответствие документации.

    Аргументы:
        response (dict): Ответ API Яндекс.Практикума в виде словаря.

    Исключения:
        APIResponseError: Если структура ответа не соответствует ожиданиям.

    Возвращает:
        list: Список домашних работ (может быть пустым).
    """
    if not isinstance(response, dict):
        response_type = type(response).__name__
        raise TypeError(
            f'Объект response не является словарем (dict), '
            f'получен тип: {response_type}'
        )

    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ожидаемый ключ "homeworks"')

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        homeworks_type = type(homeworks).__name__
        raise TypeError(
            '"homeworks" не является списком (list), '
            f'получен тип: {homeworks_type}'
        )

    return homeworks


def parse_status(homework):
    """Извлекает из информации о домашней работе её статус и готовит вердикт.

    Аргументы:
        homework (dict): Словарь с данными о конкретной домашней работе.

    Исключения:
        KeyError: Если в словаре отсутствуют обязательные ключи.
        ValueError: Если обнаружен неизвестный статус домашней работы.

    Возвращает:
        str: Подготовленная строка с вердиктом для отправки пользователю.
    """
    if "homework_name" not in homework:
        raise KeyError(
            "В ответе API отсутствует обязательное имя "
            "домашней работы 'homework_name'. "
            f"Полученные данные: {homework}"
        )
    homework_name = homework["homework_name"]

    if "status" not in homework:
        raise KeyError(
            "В ответе API отсутствует обязательный статус "
            f"работы 'status' для '{homework_name}'"
        )

    homework_status = homework["status"]

    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            "Неожиданный статус домашней работы "
            f"в ответе API: '{homework_status}'"
        )

    verdict = HOMEWORK_VERDICTS[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота.

    Последовательно выполняет шаги:
        1. Проверяет наличие токенов.
        2. Опрашивает API Яндекс.Практикума.
        3. Проверяет корректность ответа.
        4. Отправляет уведомления в Telegram при изменении статусов.
        5. Переходит в режим ожидания на установленный интервал RETRY_PERIOD.
    """
    if not check_tokens():
        raise SystemExit("Работа программы остановлена отсутствием токенов")

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = ""

    while True:
        try:
            api_answer = get_api_answer(timestamp)
            homeworks = check_response(api_answer)

            if not homeworks:
                logger.debug("Нет новых статусов домашних работ.")
                continue

            for homework in homeworks:
                message = parse_status(homework)
                send_message(bot, message)

            timestamp = api_answer["current_date"]
            last_error_message = ""

        except Exception as error:
            error_msg = f"Сбой в работе программы: {error}"
            logger.error(error_msg)

            if error_msg != last_error_message:
                if send_message(bot, error_msg):
                    last_error_message = error_msg

        finally:
            time.sleep(RETRY_PERIOD_IN_SECONDS)


if __name__ == "__main__":
    main()
