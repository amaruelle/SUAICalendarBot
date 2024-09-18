import io
import logging
import os
from datetime import datetime, timedelta

import pytz
import requests
from icalendar import Calendar, Event
from telegram import ForceReply, Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TOKEN', None)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! Просто отправь мне номер своей группы, например: 4428",
        reply_markup=ForceReply(selective=True),
    )
    
async def handle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message.text
    group_id = get_group_id(message)
    schedule = generate_ics_schedule(group_id)
    await update.message.reply_document(
        document=InputFile(schedule, "Schedule.ics"),
        caption=f"Расписание для группы {message}"
    )
    
def get_group_id(group_number):
    url = 'http://api.guap.ru/rasp/custom/get-sem-groups'
    response = requests.get(url)
    try:
        groups = response.json()
    except ValueError:
        return None  # Некорректный ответ от API

    for group in groups:
        if group['Name'] == group_number:
            return group['ItemId']
    return None  # Если группа не найдена
    
def generate_ics_schedule(group_id):
    start_date_str = os.getenv('START_DATE', f'{datetime.now().year}-09-02')
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    
    lesson_times = {
    1: ('09:30', '11:00'),
    2: ('11:10', '12:40'),
    3: ('13:00', '14:30'),
    4: ('15:00', '16:30'),
    5: ('16:40', '18:10'),
    6: ('18:30', '20:00'),
    }
    
    # Указываем часовой пояс
    timezone = pytz.timezone('Europe/Moscow')
    
    # Шаг 2: Получаем данные из API
    url = f'https://api.guap.ru/rasp/custom/get-sem-rasp/group{group_id}'
    response = requests.get(url)
    data = response.json()
    
    # Шаг 3: Создаем новый календарь
    cal = Calendar()
    cal.add('prodid', '-//GUAP Schedule//RU')
    cal.add('version', '2.0')
    
    # Шаг 4: Проходим по всем занятиям и добавляем их в календарь
    for item in data:
    
        if item["Day"] == 0:
            continue
        # Получаем информацию из полей
        week = item['Week']  # 0 - каждую неделю, 1 - нечётные, 2 - чётные
        day = item['Day']    # День недели (1 - Понедельник, ..., 6 - Суббота)
        lesson_number = item['Less']  # Номер пары
        subject = item['Disc']
        lesson_type = item['Type']    # Тип занятия (Л, ПР, ЛР)
        location = f"{item.get('Build', '')}, аудитория {item.get('Rooms', '')}"
        teacher = item.get('PrepsText', '')
        description = f"{lesson_type}. Преподаватель: {teacher}"
        print(subject)
        # Цикл по неделям семестра (например, 17 недель)
        current_date = start_date
        week_number = 1  # Счётчик недель
        for week_offset in range(17):
            # Проверяем, нужно ли добавлять занятие на этой неделе
            add_event = False
            if week == 0:
                add_event = True
            elif week == 1 and week_number % 2 == 1:
                add_event = True
            elif week == 2 and week_number % 2 == 0:
                add_event = True
            
            if add_event:
                # Вычисляем дату занятия
                lesson_date = current_date + timedelta(days=(day - 1))
                
                # Проверяем, не прошло ли занятие
                if lesson_date < datetime.now():
                    # Переходим к следующей неделе
                    current_date += timedelta(weeks=1)
                    week_number += 1
                    continue
                
                # Получаем время начала и окончания занятия
                start_time_str, end_time_str = lesson_times.get(lesson_number, ('00:00', '00:00'))
                start_datetime_str = f"{lesson_date.strftime('%Y-%m-%d')} {start_time_str}"
                end_datetime_str = f"{lesson_date.strftime('%Y-%m-%d')} {end_time_str}"
                
                # Преобразуем строки в datetime с учётом часового пояса
                start_datetime = timezone.localize(datetime.strptime(start_datetime_str, '%Y-%m-%d %H:%M'))
                end_datetime = timezone.localize(datetime.strptime(end_datetime_str, '%Y-%m-%d %H:%M'))
                
                # Добавляем информацию о событии
                event = Event()
                event.add('summary', subject)
                event.add('dtstart', start_datetime)
                event.add('dtend', end_datetime)
                event.add('location', location)
                event.add('description', description)
                cal.add_component(event)
            
            # Переходим к следующей неделе
            current_date += timedelta(weeks=1)
            week_number += 1
    
    ics_content = cal.to_ical()
    ics_file = io.BytesIO(ics_content)
    ics_file.seek(0)
    return ics_file
    
    
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
