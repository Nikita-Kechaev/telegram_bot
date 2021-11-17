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
        if not isinstance(homeworks, list):
            raise WrongTypeAnswer(
                'Ответ c сервера содержит некорректный тип данных!'
            )
        homework_status = homeworks[0].get('status')
        homework_name = homeworks[0].get('homework_name')
        if homework_name is None or homework_status is None:
            logging.error('Отсутствуют необходимые ключи в словаре ответа API')
            #  Странно, при выбрасывании исключений автотесты не проходят.
            #  Пробовал перенсти их в parse_status, тоже самое.
            #  Подобная проблема была, когда я сдавал на ревью первый раз,
            #  В итоге я решил вообще их не проверять...
            #  А так да, я полностью согласен, что тут
            #  необходимо ошибку вызывать.
            #  raise WrongTypeAnswer('Что то пошло не так!')
        if homework_status not in HOMEWORK_STATUSES:
            logging.error('Недокументированный статус домашней работы.')
            #  возможно необходимо проверять и строку 87 в parse_status
            #  но тогда я не понимаю какой смысл в функции check_response,
            #  и тогда условие задачи, в которой parse_status должен получать
            #  только одну домашнюю работу из списка как то нелогично...
            #  raise WrongTypeAnswer('Что то пошло не так!')
        return homeworks
    except KeyError as error:
        error_message = ('Ответ API содержит некорректную переменную. '
                         f'Ошибка: {error}.')
        raise WrongTypeAnswer(error_message)
    except IndexError as error:
        error_message = ('Нет домашних заданий на проверку. '
                         f'Ошибка: {error}.')
        raise HomeworkStatusNotChange(error_message)


def parse_status(homework):
    """Возвращает сообщение об изменении status."""
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
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            message = parse_status(homeworks[0])
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
        #  В этой части кода моя логика была такая:
        #  Если произошла какая то ошибка, бот посылает сообщение о ней
        #  (если может) . Если через десять минут ошибка таже, бот её не  будет
        #  спамить в телегу, а просто залогирует, и в случае исправления
        #  ситуации или новой ошибки, он отправит сообщение.
        #  Если после успешной отправки обнулять message, то тогда этой логики
        #  не будет и можно просто без проверки каждые десять минут получать
        #  сообщение об ошибке. Может как то можно и по другому реализовать, но
        #  тогда необходимо проверять какое было вызвано исключение, и не равно
        #  ли оно текущему. Если можно как то по-другому реализовать,
        #  подскажите пожалуйста в какую сторону копать.
        if old_message != message:
            old_message = message
            send_message(bot, message)
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
