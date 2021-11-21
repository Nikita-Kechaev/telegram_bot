import logging
import os
import sys
import time
from logging import StreamHandler

import requests
from dotenv import load_dotenv
from telegram import Bot

from exceptions import (BadRequest, HomeworkStatusNotChange, TokenValueError,
                        WrongTypeAnswer)

load_dotenv()
logger = logging.getLogger('homework_logger')
handler = StreamHandler(stream=sys.stdout)
logger.addHandler(handler)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s, %(levelname)s, %(message)s'
)

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
    except requests.exceptions.RequestException as error:
        error_message = ('Нет возможности получить информацию с сервера. '
                         f'Ошибка: {error}.')
        raise BadRequest(error_message)
    status_code = response.status_code
    if status_code != 200:
        error_message = ('Нет возможности получить информацию с сервера, '
                         f'status_code запроса: {status_code}.')
        raise BadRequest(error_message)
    response = response.json()
    return response


def check_response(response):
    """
    Проверяет тип полученных данных. Если не список - вызывает исключение.
    Возвращает список.
    """
    try:
        homeworks = response['homeworks']
        if not homeworks:
            raise HomeworkStatusNotChange('Нет домашних заданий на проверку.')
        if not isinstance(homeworks, list):
            raise WrongTypeAnswer(
                'Ответ c сервера содержит некорректный тип данных!'
            )
        return homeworks
    except KeyError as error:
        error_message = ('Ответ API содержит некорректную переменную. '
                         f'Ошибка: {error}.')
        raise WrongTypeAnswer(error_message)


def parse_status(homework):
    """Возвращает сообщение об изменении status."""
    homework_status = homework['status']
    homework_name = homework['homework_name']
    if homework_status not in HOMEWORK_STATUSES:
        raise WrongTypeAnswer(
            'Недокументированный статус домашней работы.'
        )
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
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            message = parse_status(homeworks[0])
            old_message = None
            current_timestamp = response['current_date']
        except HomeworkStatusNotChange as error:
            logging.debug(
                'Отсутствие нового статуса домашней работы.'
                f'Ошибка: {error}'
            )
            message = f'Отсутствие нового статуса домашней работы: {error}'
        except Exception as error:
            logging.error(
                f'Сбой в работе программы: {error}'
            )
            message = f'Сбой в работе программы: {error}'
        if old_message != message:
            old_message = message
            send_message(bot, message)
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
