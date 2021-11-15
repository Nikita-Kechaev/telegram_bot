import logging
import os
import sys
import time
from logging import StreamHandler

import requests
from dotenv import load_dotenv
from telegram import Bot

from exceptions import (BadRequest, HomeworkStatusNotChange, TokenValueError,
                        WrongTypeAnsewr, NoHomeworkToRewiev)

load_dotenv()
logger = logging.getLogger('homework_logger')
handler = StreamHandler(stream=sys.stdout)
logger.addHandler(handler)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s, %(levelname)s, %(message)s'
)
HOMEWORK_STATUSES = [
    'reviewing',
    'approved',
    'rejected'
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
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
        status_code = response.status_code
        if status_code != 200:
            error_message = 'Нет возможности получить информацию с сервера, '\
                            f'status_code запроса: {status_code}.'
            logging.error(error_message)
            raise BadRequest(error_message)
        response = response.json()
        return response
    except ConnectionError as error:
        raise ConnectionError(error)


def check_response(response):
    """
    Проверяет тип полученных данных. Если не список - вызывает исключение.
    Возвращает список.
    """
    try:
        homeworks = response['homeworks']
        if not isinstance(homeworks, list):
            logging.error(
                'Ответ c сервера содержит некорректный тип данных!'
            )
            raise WrongTypeAnsewr(
                'Ответ c сервера содержит некорректный тип данных!'
            )
        homework_status = homeworks[0].get('status')
        if homework_status not in HOMEWORK_STATUSES:
            logging.error('Недокументированный статус домашней работы.')
        return homeworks
    except IndexError:
        logging.error(
            'Нет домашних заданий на проверку.'
        )
        raise NoHomeworkToRewiev(
            'Нет домашних заданий на проверку.'
        )


def parse_status(homework):
    """Проверяет ключи. Возвращает сообщение об изменении status."""
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


def main():
    """Основная логика работы бота."""
    run = check_tokens()
    if not run:
        raise TokenValueError('Отсутствует обязательная переменная окружения')
    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    old_message = None
    old_homework_status = None
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            message = parse_status(homeworks[0])
            if old_homework_status == homeworks[0].get('status'):
                raise HomeworkStatusNotChange
            old_homework_status = homeworks[0].get('status')
            current_timestamp = current_timestamp
        except HomeworkStatusNotChange:
            logging.debug('Отсутствие в ответе новых статусов')
        except Exception as error:
            logging.error(f'Сбой в работе программы: {error}')
            message = f'Сбой в работе программы: {error}'

        if old_message != message:
            old_message = message
            send_message(bot, message)
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
