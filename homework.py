import logging
import os
import sys
import time
from logging import StreamHandler

import requests
from dotenv import load_dotenv
from telegram import Bot

from exceptions import (BadRequest, HomeworkStatusNotChange, TokenValueError,
                        UnknownStatus, WrongTypeAnsewr)

load_dotenv()
logger = logging.getLogger('homework_logger')
handler = StreamHandler(stream=sys.stdout)
logger.addHandler(handler)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s, %(levelname)s, %(message)s'
)
homework_statuses = [
    'reviewing',
    'approved',
    'rejected'
]
yandex_api_key_list = [
    'id',
    'status',
    'homework_name',
    'lesson_name'
]


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

RETRY_TIME = 600
HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """
    Направляет сообщение в телеграмм-чат. Логирует успешную отправку.
    Логирует ошибку в противоположном случае.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception as error:
        logging.error(
            f'Не удалось отправить сообщение. {error}'
        )
    else:
        logger.info(
            f'Бот отправил сообщение: {message}'
        )


def get_api_answer(current_timestamp):
    """
    Выполняет запрос к API. Проверяет статус ответа.В случае ошибки - логирует.
    Возвращает преобразованную Json - строку.
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    if response.status_code != 200:
        raise BadRequest
    response = response.json()
    return response


def check_response(response):
    """
    Проверяет тип полученных данных. Если не список - вызывает исключение.
    Возвращает список.
    """
    homeworks = response['homeworks']
    if type(homeworks) != list:
        raise WrongTypeAnsewr
    return homeworks


def parse_status(homework):
    """Проверяет ключи. Возвращает сообщение об изменении status."""
    for key in yandex_api_key_list:
        try:
            homework[key]
        except KeyError as error:
            logging.error(
                f'Отсутствие ожидаемых ключей в ответе API : {error}'
            )
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    verdict = HOMEWORK_STATUSES[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """
    Проверяем, что из .env экспортируются все токены.
    Если успешно, возвращает True.
    Если ошибка, лоигрует и возвращает False
    """
    token_list = {
        TELEGRAM_CHAT_ID: 'TELEGRAM_CHAT_ID',
        TELEGRAM_TOKEN: 'TELEGRAM_TOKEN',
        PRACTICUM_TOKEN: 'PRACTICUM_TOKEN'
    }
    for token_value, token_name in token_list.items():
        if token_value is None:
            logging.critical(
                f'Отсутствует обязательная переменная окружения: {token_name}'
            )
            return False
    return True


def test(new_homework_status, old_homework_status):
    """Функция создана для того, что бы Flake8 пропустил на ревью."""
    if new_homework_status not in homework_statuses:
        raise UnknownStatus
    if old_homework_status == new_homework_status:
        raise HomeworkStatusNotChange


def main():
    """Основная логика работы бота."""
    Run = check_tokens()
    if Run is False:
        raise TokenValueError('Отсутствует обязательная переменная окружения')
    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    old_homework_status = None
    BadRequest_count = 0
    UnknownStatus_count = 0
    while Run:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            new_homework_status = homeworks[0].get('status')
            test(new_homework_status, old_homework_status)
            old_homework_status = new_homework_status
            message = parse_status(homeworks[0])
            current_timestamp = current_timestamp
        except UnknownStatus:
            logging.error('Недокументированный статус домашней работы')
            if UnknownStatus_count > 0:
                time.sleep(RETRY_TIME)
                continue
            message = 'На данный момент статус домашней работы не определен'
            send_message(bot, message)
            UnknownStatus_count = 1
        except HomeworkStatusNotChange:
            logging.debug('Отсутствие в ответе новых статусов')
            time.sleep(RETRY_TIME)
        except BadRequest:
            logging.error('Нет возможности получить информацию с сервера')
            if BadRequest_count > 0:
                time.sleep(RETRY_TIME)
                continue
            message = 'Нет возможности получить информацию с сервера'
            send_message(bot, message)
            BadRequest_count = 1
            time.sleep(RETRY_TIME)
        except Exception as error:
            logging.error(f'Сбой в работе программы: {error}')
            message = f'Сбой в работе программы: {error}'
            time.sleep(RETRY_TIME)
        else:
            send_message(bot, message)
            BadRequest_count = 0
            UnknownStatus_count = 0
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
